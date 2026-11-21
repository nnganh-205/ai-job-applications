"""Account flows, request protection and cross-account isolation without live AI calls."""
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from fastapi import FastAPI
from fastapi.testclient import TestClient
from backend.app.api.auth import router as auth_router, _attempts
from backend.app.api.profile import router as profiles_router
from backend.app.api.profile_drafts import router as drafts_router
from backend.app.api.resumes import router as resumes_router
from backend.app.core.auth_middleware import AuthMiddleware
from backend.app.core.workspace import workspace, graph_config, record_kind
from backend.app.db import profile_repository as profiles, workflow_repository as records
from backend.app.services import auth, profile_drafts, resumes
from backend.app.schemas.resume import ResumeStart


class AccountTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        for patcher in [patch.dict(os.environ, {'KLTN_STORAGE': 'json', 'AUTH_SQLITE_PATH': str(root/'accounts.sqlite3')}),
                        patch.object(profiles, 'DEFAULT_STORAGE_DIR', root/'profiles'),
                        patch.object(records, 'DEFAULT_WORKFLOW_STORAGE', root/'workflows')]:
            patcher.start(); self.addCleanup(patcher.stop)
        _attempts.clear()
        app = FastAPI()
        app.add_middleware(AuthMiddleware)
        for router in [auth_router, profiles_router, drafts_router, resumes_router]: app.include_router(router)
        self.a, self.b = TestClient(app), TestClient(app)
        self.addCleanup(self.a.close); self.addCleanup(self.b.close)

    def register(self, client, email='candidate@example.com', name='Nguyễn Minh An'):
        response = client.post('/api/auth/register', json={'full_name': name, 'email': email, 'password': 'Test-password-123'})
        self.assertEqual(response.status_code, 201, response.text)
        client.headers['X-KLTN-CSRF'] = response.json()['csrf_token']
        return response.json()['user']

    def test_registration_session_hash_and_seed_profile(self):
        user = self.register(self.a)
        self.assertEqual(self.a.get('/api/auth/me').json()['user'], user)
        response = self.a.get('/api/profiles/' + user['profile_id'])
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['profile']['contact']['email'], user['email'])
        with sqlite3.connect(Path(self.tmp.name)/'accounts.sqlite3') as c:
            encoded = c.execute('SELECT password_hash FROM auth_users').fetchone()[0]
        self.assertNotIn('Test-password-123', encoded)
        self.assertTrue(auth.verify_password('Test-password-123', encoded))
        self.assertTrue(self.a.cookies.get('kltn_session'))

    def test_duplicate_normalized_email_and_wrong_password(self):
        self.register(self.a)
        duplicate = self.b.post('/api/auth/register', json={'full_name': 'Other Candidate', 'email': ' CANDIDATE@EXAMPLE.COM ', 'password': 'Another-password'})
        self.assertEqual(duplicate.status_code, 409)
        self.assertEqual(self.b.post('/api/auth/login', json={'email':'candidate@example.com','password':'incorrect'}).status_code, 401)
        self.assertEqual(self.b.post('/api/auth/login', json={'email':'candidate@example.com','password':'Test-password-123'}).status_code, 200)

    def test_guests_and_csrf_are_rejected(self):
        self.assertEqual(self.a.get('/api/profile-drafts/profiles').status_code, 401)
        self.assertIsNone(self.a.get('/api/auth/me').json()['user'])
        self.register(self.a)
        self.a.headers.pop('X-KLTN-CSRF')
        self.assertEqual(self.a.post('/api/profile-drafts', json={}).status_code, 403)
        self.assertEqual(self.a.post('/api/auth/login', json={'email':'candidate@example.com','password':'Test-password-123'}, headers={'Origin':'https://attacker.example'}).status_code, 403)

    def test_logout_revokes_old_cookie(self):
        self.register(self.a)
        token = self.a.cookies.get(auth.COOKIE_NAME)
        self.assertEqual(self.a.post('/api/auth/logout').status_code, 200)
        self.assertIsNone(auth.resolve_session(token))
        self.assertIsNone(self.a.get('/api/auth/me').json()['user'])

    def test_expired_and_forged_sessions(self):
        self.register(self.a)
        token = self.a.cookies.get(auth.COOKIE_NAME)
        self.assertIsNone(auth.resolve_session('not-a-real-session-token'))
        with sqlite3.connect(Path(self.tmp.name)/'accounts.sqlite3') as c:
            c.execute('UPDATE auth_sessions SET expires_at=0')
        self.assertIsNone(auth.resolve_session(token))
        self.assertEqual(self.a.get('/api/profile-drafts/profiles').status_code, 401)

    def test_accounts_cannot_read_each_others_profiles_drafts_or_cvs(self):
        a = self.register(self.a)
        b = self.register(self.b, 'second@example.com', 'Trần Bình')
        self.assertEqual(self.b.get('/api/profiles/' + a['profile_id']).status_code, 404)
        self.assertEqual([p['profile_id'] for p in self.b.get('/api/profile-drafts/profiles').json()], [b['profile_id']])
        created = self.a.post('/api/profile-drafts', json={}).json()
        self.assertEqual(created['profile']['contact']['full_name'], a['full_name'])
        self.assertEqual(self.b.get('/api/profile-drafts/' + created['draft_id']).status_code, 404)
        with workspace(a['user_id']):
            from backend.app.schemas.profile import MasterProfile
            profile = MasterProfile(contact={'full_name': a['full_name']}, experience=[], education=[], involvement=[], skills=[],
                                    project=[{'id':'project1','project_name':'Fixture project','description':['Built an API with Python.']}])
            profiles.save_master_profile('completed_candidate', profile, profiles.DEFAULT_STORAGE_DIR)
            cv = resumes.start(ResumeStart(profile_id='completed_candidate'))
        self.assertEqual(self.b.get('/api/resumes/' + cv['resume_id']).status_code, 404)
        self.assertEqual(self.b.get('/api/resumes').json(), [])
        self.assertEqual(len(self.a.get('/api/resumes').json()), 1)

    def test_checkpoint_and_record_namespaces_do_not_collide(self):
        with workspace('user_first'):
            first = graph_config('same-thread')
            records.put('answers', 'same-key', {'private': 'first'})
            first_kind = record_kind('answers')
        with workspace('user_second'):
            self.assertNotEqual(first, graph_config('same-thread'))
            self.assertNotEqual(first_kind, record_kind('answers'))
            self.assertIsNone(records.get('answers', 'same-key'))
        with workspace('user_first'):
            self.assertEqual(records.get('answers', 'same-key'), {'private':'first'})

    def test_cookie_is_http_only_and_private_responses_are_not_cached(self):
        response = self.a.post('/api/auth/register', json={'full_name':'Test Candidate','email':'cookie@example.com','password':'Test-password-123'})
        session_cookie = next(value for value in response.headers.get_list('set-cookie') if value.startswith('kltn_session='))
        self.assertIn('HttpOnly', session_cookie)
        self.assertIn('SameSite=lax', session_cookie)
        self.assertEqual(self.a.get('/api/auth/me').headers['cache-control'], 'no-store')


if __name__ == '__main__': unittest.main()
