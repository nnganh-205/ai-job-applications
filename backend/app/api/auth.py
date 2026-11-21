import os
import threading
import time
from collections import OrderedDict, deque
from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field
from backend.app.services import auth

router = APIRouter(prefix='/api/auth', tags=['Accounts'])
_attempts = OrderedDict()
_attempt_lock = threading.Lock()


class Credentials(BaseModel):
    model_config = ConfigDict(extra='forbid')
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=128, repr=False)


class Registration(Credentials):
    full_name: str = Field(min_length=2, max_length=100)


def limit(request):
    key = request.client.host if request.client else 'unknown'
    now = time.monotonic()
    with _attempt_lock:
        attempts = _attempts.setdefault(key, deque())
        while attempts and attempts[0] < now - 300:
            attempts.popleft()
        if len(attempts) >= 20:
            raise HTTPException(429, 'Bạn đã thử nhiều lần. Vui lòng thử lại sau ít phút.', headers={'Retry-After': '300'})
        attempts.append(now)
        _attempts.move_to_end(key)
        while len(_attempts) > 2048:
            _attempts.popitem(last=False)


def session_response(response, request, result):
    data, token = result
    secure = request.url.scheme == 'https' or os.getenv('AUTH_COOKIE_SECURE', '0') == '1'
    options = dict(max_age=auth.SESSION_SECONDS, secure=secure, samesite='lax', path='/')
    response.set_cookie(auth.COOKIE_NAME, token, httponly=True, **options)
    response.set_cookie(auth.CSRF_COOKIE, data['csrf_token'], httponly=False, **options)
    response.headers['Cache-Control'] = 'no-store'
    return data


@router.post('/register', status_code=201)
def register(payload: Registration, request: Request, response: Response):
    limit(request)
    try:
        result = auth.register(payload.full_name, payload.email, payload.password)
    except auth.EmailTaken as error:
        raise HTTPException(409, str(error)) from error
    except ValueError as error:
        raise HTTPException(422, str(error)) from error
    return session_response(response, request, result)


@router.post('/login')
def login(payload: Credentials, request: Request, response: Response):
    limit(request)
    try:
        result = auth.login(payload.email, payload.password)
    except (ValueError, PermissionError) as error:
        raise HTTPException(401, 'Email hoặc mật khẩu chưa đúng.') from error
    return session_response(response, request, result)


@router.get('/me')
def me(request: Request):
    return getattr(request.state, 'auth', None) or {'user': None, 'csrf_token': None}


@router.post('/logout')
def logout(request: Request, response: Response):
    auth.logout(request.cookies.get(auth.COOKIE_NAME))
    response.delete_cookie(auth.COOKIE_NAME, path='/')
    response.delete_cookie(auth.CSRF_COOKIE, path='/')
    return {'signed_out': True}
