"""Password hashing and revocable opaque sessions. No credentials in browser storage."""
import hashlib
import hmac
import re
import secrets
import time
from uuid import uuid4
from backend.app.core.workspace import workspace
from backend.app.db import auth_repository as repository

COOKIE_NAME = 'kltn_session'
CSRF_COOKIE = 'kltn_csrf'
SESSION_SECONDS = 7 * 24 * 60 * 60


class EmailTaken(ValueError):
    pass


def normalize_email(value):
    value = value.strip().casefold()
    if not value.isprintable() or len(value) > 254 or not re.fullmatch(r'[^\s@]+@[^\s@.]+(?:\.[^\s@.]+)+', value):
        raise ValueError('Địa chỉ email không hợp lệ.')
    return value


def hash_password(password, salt=None):
    salt = salt or secrets.token_hex(16)
    digest = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=16384, r=8, p=1, dklen=32)
    return f'scrypt${salt}${digest.hex()}'


_DUMMY_HASH = hash_password('not-a-real-account-password')


def verify_password(password, encoded):
    try:
        algorithm, salt, _ = encoded.split('$')
        return algorithm == 'scrypt' and hmac.compare_digest(hash_password(password, salt), encoded)
    except (ValueError, TypeError):
        return False


def token_hash(token):
    return hashlib.sha256(token.encode()).hexdigest()


def public_user(row):
    return {'user_id': row['user_id'], 'full_name': row['full_name'], 'email': row['email'], 'role': dict(row).get('role', 'user'), 'profile_id': 'account_' + row['user_id']}


def new_session(store, user):
    token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
    store.execute('DELETE FROM auth_sessions WHERE expires_at < ?', (time.time(),))
    store.execute('INSERT INTO auth_sessions(token_hash,user_id,csrf_token,expires_at) VALUES (?,?,?,?)',
                  (token_hash(token), user['user_id'], csrf, time.time() + SESSION_SECONDS))
    return {'user': public_user(user), 'csrf_token': csrf}, token


def register(full_name, email, password):
    full_name = ' '.join(full_name.split())
    if not full_name.isprintable() or not 2 <= len(full_name) <= 100:
        raise ValueError('Họ và tên cần từ 2 đến 100 ký tự.')
    if not 8 <= len(password) <= 128:
        raise ValueError('Mật khẩu cần từ 8 đến 128 ký tự.')
    email = normalize_email(email)
    user = dict(user_id='user_' + uuid4().hex, email=email, full_name=full_name, password_hash=hash_password(password), created_at=time.time())
    try:
        with repository.transaction() as store:
            store.execute('INSERT INTO auth_users(user_id,email,full_name,password_hash,created_at) VALUES (?,?,?,?,?)', tuple(user.values()))
            # Registration confirms only the name/email the candidate just supplied.
            from backend.app.db import profile_repository
            from backend.app.schemas.profile import MasterProfile
            with workspace(user['user_id']):
                profile_repository.save_master_profile('account_' + user['user_id'], MasterProfile(contact={'full_name': full_name, 'email': email}, experience=[], project=[], education=[], involvement=[], skills=[]),
                                    profile_repository.DEFAULT_STORAGE_DIR, connection=store.connection if store.postgres else None)
            return new_session(store, user)
    except Exception as error:
        if repository.duplicate_email(error):
            raise EmailTaken('Email này đã có tài khoản. Bạn có thể đăng nhập.') from error
        raise


def login(email, password):
    email = normalize_email(email)
    with repository.transaction() as store:
        row = store.execute('SELECT * FROM auth_users WHERE email=?', (email,)).fetchone()
        valid = verify_password(password, row['password_hash'] if row else _DUMMY_HASH)
        if not row or not valid or not row['is_active']:
            raise PermissionError('Email hoặc mật khẩu chưa đúng.')
        return new_session(store, row)


def resolve_session(token):
    if not token or not 20 <= len(token) <= 128:
        return None
    with repository.transaction() as store:
        row = store.execute('SELECT u.*,s.csrf_token FROM auth_sessions s JOIN auth_users u ON u.user_id=s.user_id WHERE s.token_hash=? AND s.expires_at>? AND u.is_active=1',
                            (token_hash(token), time.time())).fetchone()
    return {'user': public_user(row), 'csrf_token': row['csrf_token']} if row else None


def logout(token):
    if token:
        with repository.transaction() as store:
            store.execute('DELETE FROM auth_sessions WHERE token_hash=?', (token_hash(token),))
