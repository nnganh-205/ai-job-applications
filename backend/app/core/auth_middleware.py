"""Protect private APIs and bind workspace identity before threadpool dispatch."""
import hmac
import re
from urllib.parse import urlsplit
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.concurrency import run_in_threadpool
from backend.app.core.workspace import workspace
from backend.app.db.database import DatabaseUnavailable
from backend.app.services import auth


def is_public(method, path):
    if path in {'/api/auth/me', '/api/auth/login', '/api/auth/register'}:
        return True
    return method in {'GET', 'HEAD'} and (
        path in {'/api/dashboard', '/api/cv/templates'}
        or re.fullmatch(r'/api/dashboard/jobs/posting_[a-f0-9]{24}', path)
        or re.fullmatch(r'/api/cv/templates/[A-Za-z0-9_-]+/(?:preview|thumbnail)', path)
    )


class AuthMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http' or not scope['path'].startswith('/api/'):
            return await self.app(scope, receive, send)
        request = Request(scope)
        public = is_public(request.method, scope['path'])
        try:
            session = await run_in_threadpool(auth.resolve_session, request.cookies.get(auth.COOKIE_NAME))
        except DatabaseUnavailable:
            return await JSONResponse({'detail': 'Chưa kết nối được cơ sở dữ liệu tài khoản.'}, 503)(scope, receive, send)
        if not public and session is None:
            return await JSONResponse({'detail': 'Vui lòng đăng nhập để sử dụng không gian cá nhân.'}, 401)(scope, receive, send)
        if request.method not in {'GET', 'HEAD', 'OPTIONS'}:
            origin = request.headers.get('origin')
            try:
                unsafe_origin = origin is not None and (urlsplit(origin).netloc != request.headers.get('host') or urlsplit(origin).scheme not in {'http', 'https'})
            except ValueError:
                unsafe_origin = True
            if unsafe_origin or request.headers.get('sec-fetch-site') == 'cross-site':
                return await JSONResponse({'detail': 'Nguồn gửi yêu cầu không hợp lệ.'}, 403)(scope, receive, send)
            if not public and not hmac.compare_digest(request.headers.get('x-kltn-csrf', ''), session['csrf_token']):
                return await JSONResponse({'detail': 'Phiên xác thực đã thay đổi. Tải lại trang và thử lại.'}, 403)(scope, receive, send)
        scope.setdefault('state', {})['auth'] = session
        async def send_private(message):
            if message['type'] == 'http.response.start' and (session or not public or scope['path'].startswith('/api/auth/')):
                message['headers'] = [(k,v) for k,v in message['headers'] if k.lower() != b'cache-control'] + [(b'cache-control', b'no-store')]
            await send(message)
        with workspace(session['user']['user_id'] if session else 'public'):
            await self.app(scope, receive, send_private)
