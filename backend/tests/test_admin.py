"""Admin permissions, revocation, provision-once and the real RAG source lifecycle."""
import json
import os
import stat
import unittest
from pathlib import Path
from unittest.mock import patch
from backend.tests import test_auth as auth_fixtures
from backend.app.api.admin import router
from backend.app.services import administration as admin, auth, knowledge
from backend.app.db import auth_repository


class AdministrationTests(unittest.TestCase):
    register = auth_fixtures.AccountTests.register

    def setUp(self):
        auth_fixtures.AccountTests.setUp(self)
        self.a.app.include_router(router)
        from backend.app.api.cv import router as cv_router
        self.a.app.include_router(cv_router)
        self.credential_path = Path(self.tmp.name)/'admin-bootstrap.json'
        patcher = patch.dict(os.environ, {'ADMIN_BOOTSTRAP_PATH': str(self.credential_path), 'ADMIN_EMAIL': 'admin@example.test', 'ADMIN_PASSWORD': ''})
        patcher.start(); self.addCleanup(patcher.stop)
        admin.bootstrap_admin()
        credentials = json.loads(self.credential_path.read_text())
        response = self.a.post('/api/auth/login', json={'email': credentials['email'], 'password': credentials['password']})
        self.assertEqual(response.status_code, 200, response.text)
        self.a.headers['X-KLTN-CSRF'] = response.json()['csrf_token']
        self.admin_id = response.json()['user']['user_id']

    def document(self, **changes):
        return {'title': 'Tài liệu kiểm thử RAG', 'text': 'Điều 99. Hướng dẫn kiểm thử. Mã hiệu zirconium token riêng cho kiểm thử kho tri thức. ' * 3,
                'url': 'https://example.test/law', 'effective': '2026-01-01', 'status': 'draft', **changes}

    def test_bootstrap_is_private_idempotent_and_never_resets_password(self):
        first = self.credential_path.read_text()
        self.assertEqual(stat.S_IMODE(self.credential_path.stat().st_mode), 0o600)
        with auth_repository.transaction() as store:
            store.execute('UPDATE auth_users SET password_hash=? WHERE user_id=?', (auth.hash_password('New-admin-password-123'), self.admin_id))
        admin.bootstrap_admin()
        self.assertEqual(self.credential_path.read_text(), first)
        data, _ = auth.login('admin@example.test', 'New-admin-password-123')
        self.assertEqual(data['user']['role'], 'admin')
        self.assertEqual(len(admin.users()), 1)

    def test_registration_cannot_assign_admin_and_admin_api_is_server_protected(self):
        from fastapi.testclient import TestClient
        with TestClient(self.a.app) as guest:
            self.assertEqual(guest.get('/api/admin/users').status_code, 401)
            response = guest.post('/api/auth/register', json={'full_name':'Fake Admin','email':'fake@example.test','password':'Long-password-123','role':'admin'})
            self.assertEqual(response.status_code, 422)
        member = self.register(self.b)
        for path in ('overview', 'users', 'knowledge', 'templates', 'templates/bases', 'tasks', 'activity'):
            self.assertEqual(self.b.get('/api/admin/' + path).status_code, 403)
        self.assertEqual(self.b.post('/api/admin/knowledge', json=self.document()).status_code, 403)
        self.assertEqual(self.b.patch('/api/admin/users/' + member['user_id'], json={'role':'admin'}).status_code, 403)
        self.assertEqual(self.a.get('/api/admin/overview').status_code, 200)
        users = self.a.get('/api/admin/users').json()
        self.assertNotIn('password_hash', json.dumps(users))
        self.assertNotIn('csrf_token', json.dumps(users))

    def test_lock_revokes_session_rejects_login_and_unlock_does_not_restore_session(self):
        member = self.register(self.b)
        old_token = self.b.cookies.get(auth.COOKIE_NAME)
        self.assertEqual(self.a.patch('/api/admin/users/' + member['user_id'], json={'is_active':False}).status_code, 200)
        self.assertIsNone(auth.resolve_session(old_token))
        self.assertEqual(self.b.get('/api/profile-drafts/profiles').status_code, 401)
        self.assertEqual(self.b.post('/api/auth/login', json={'email':member['email'],'password':'Test-password-123'}).status_code, 401)
        self.a.patch('/api/admin/users/' + member['user_id'], json={'is_active':True})
        self.assertIsNone(auth.resolve_session(old_token))
        self.assertEqual(self.b.post('/api/auth/login', json={'email':member['email'],'password':'Test-password-123'}).status_code, 200)

    def test_self_protection_and_password_reset_revocation_audit_contains_no_secret(self):
        self.assertEqual(self.a.patch('/api/admin/users/' + self.admin_id, json={'role':'user'}).status_code, 409)
        self.assertEqual(self.a.patch('/api/admin/users/' + self.admin_id, json={'is_active':False}).status_code, 409)
        member = self.register(self.b)
        password = 'Reset-password-very-private'
        result = self.a.patch('/api/admin/users/' + member['user_id'], json={'password':password})
        self.assertEqual(result.status_code, 200)
        self.assertIsNone(self.b.get('/api/auth/me').json()['user'])
        self.assertEqual(self.b.post('/api/auth/login', json={'email':member['email'],'password':'Test-password-123'}).status_code, 401)
        self.assertEqual(self.b.post('/api/auth/login', json={'email':member['email'],'password':password}).status_code, 200)
        activity = self.a.get('/api/admin/activity').text
        self.assertIn('account.update', activity)
        self.assertNotIn(password, activity)

    def test_role_changes_invalidate_sessions_and_last_admin_is_preserved(self):
        member = self.register(self.b)
        self.a.patch('/api/admin/users/' + member['user_id'], json={'role':'admin'})
        self.assertIsNone(self.b.get('/api/auth/me').json()['user'])
        response = self.b.post('/api/auth/login', json={'email':member['email'],'password':'Test-password-123'})
        self.b.headers['X-KLTN-CSRF'] = response.json()['csrf_token']
        self.assertEqual(self.b.get('/api/admin/users').status_code, 200)
        self.assertEqual(self.b.patch('/api/admin/users/' + self.admin_id, json={'role':'user'}).status_code, 200)
        self.assertEqual(self.a.get('/api/admin/users').status_code, 401)
        with self.assertRaises(admin.AdminConflict):
            admin.update_user('another-actor', member['user_id'], {'is_active':False})

    def test_knowledge_versions_and_publication_directly_control_retrieval(self):
        from ai.rag.labor_law import retrieve
        created = self.a.post('/api/admin/knowledge', json=self.document())
        self.assertEqual(created.status_code, 201, created.text)
        source = created.json()
        with patch('ai.rag.labor_law.load_index', return_value=[]):
            self.assertEqual(retrieve('zirconium token'), [])
            publish = self.a.patch('/api/admin/knowledge/' + source['document_id'] + '/status', json={'status':'published','expected_version':1})
            self.assertEqual(publish.status_code, 200)
            self.assertTrue(retrieve('zirconium token'))
            self.assertEqual(self.a.patch('/api/admin/knowledge/' + source['document_id'] + '/status', json={'status':'archived','expected_version':1}).status_code, 409)
            self.assertEqual(self.a.patch('/api/admin/knowledge/' + source['document_id'] + '/status', json={'status':'archived','expected_version':2}).status_code, 200)
            self.assertEqual(retrieve('zirconium token'), [])
        revised = self.document(text='Nội dung đã chỉnh sửa cho mã krypton token trong tài liệu kiểm thử. ' * 3, status='published', expected_version=3)
        self.assertEqual(self.a.put('/api/admin/knowledge/' + source['document_id'], json=revised).status_code, 200)
        with patch('ai.rag.labor_law.load_index', return_value=[]):
            self.assertTrue(retrieve('krypton token'))
            self.assertFalse(retrieve('zirconium token'))
        self.assertTrue(self.a.post('/api/admin/knowledge/search', json={'query':'krypton token'}).json()['hits'])
        self.assertEqual(self.a.get('/api/admin/knowledge/' + source['document_id']).json()['version'], 4)

    def test_builtin_import_keeps_pages_and_state_after_restart(self):
        from ai.rag.labor_law import retrieve
        row = dict(id='45.signed.pdf:1:1',title='Bộ luật kiểm thử',url='https://example.test/law',effective='2026-01-01',file='45.signed.pdf',page=4,article='Điều 99',text='Mã zirconium token trong văn bản quy phạm kiểm thử. '*4)
        with patch('ai.rag.labor_law.load_index', return_value=[row]):
            knowledge.initialize_sources(); knowledge.initialize_sources()
            source = knowledge.list_documents()[0]
            self.assertEqual(source['chunk_count'], 1)
            self.assertEqual(retrieve('zirconium token')[0]['page'], 4)
            self.a.patch('/api/admin/knowledge/' + source['document_id'] + '/status', json={'status':'archived','expected_version':1})
            knowledge.initialize_sources()
            self.assertEqual(retrieve('zirconium token'), [])
            self.assertEqual(knowledge.list_documents()[0]['status'], 'archived')

    def test_pdf_upload_indexes_text_as_draft_and_rejects_invalid_inputs(self):
        import pymupdf
        with pymupdf.open() as pdf:
            page = pdf.new_page()
            page.insert_text((50, 60), 'zirconium token searchable knowledge base. '*4)
            content = pdf.tobytes()
        result = self.a.post('/api/admin/knowledge/upload', data={'title':'PDF kiểm thử'}, files={'file':('fixture.pdf',content,'application/pdf')})
        self.assertEqual(result.status_code, 201, result.text)
        self.assertEqual(result.json()['status'], 'draft')
        value = knowledge.detail(result.json()['document_id'])
        self.assertIn('zirconium token', value['text'])
        self.assertEqual(self.a.post('/api/admin/knowledge/upload', data={'title':'Invalid PDF'}, files={'file':('bad.pdf',b'not pdf','application/pdf')}).status_code, 422)
        self.assertEqual(self.a.post('/api/admin/knowledge', json=self.document(url='javascript:alert(1)')).status_code, 422)
        self.assertEqual(self.a.post('/api/admin/knowledge', json=self.document(effective='2026-99-99')).status_code, 422)
        self.assertEqual(self.a.post('/api/admin/knowledge', json=self.document(status='unknown')).status_code, 422)

    def test_admin_mutations_require_csrf(self):
        self.a.headers.pop('X-KLTN-CSRF')
        self.assertEqual(self.a.post('/api/admin/knowledge', json=self.document()).status_code, 403)

    def test_manual_index_preserves_article_boundaries(self):
        text = 'Điều 10. Mục đầu\n' + 'Nội dung kiểm thử điều đầu. ' * 6 + '\nĐiều 11. Mục sau\n' + 'Nội dung kiểm thử điều sau. ' * 6
        document = knowledge.save(self.admin_id, self.document(text=text))
        with auth_repository.transaction() as store:
            value = json.loads(store.execute('SELECT payload FROM admin_documents WHERE document_id=?', (document['document_id'],)).fetchone()['payload'])
        self.assertEqual([chunk['article'] for chunk in value['chunks']], ['Điều 10', 'Điều 11'])
        self.assertNotIn('Điều 11', value['chunks'][0]['text'])

    def template(self, **changes):
        return {**dict(name='Mẫu CV kiểm thử', description='Bố cục dành cho hồ sơ chuyên nghiệp.',
                    base_template='simple', category='professional', color='#6543ab', font='sans', enabled=True), **changes}

    def test_template_crud_updates_public_catalog_and_preserves_saved_rendering(self):
        from backend.app.services.cv_templates import metadata, synthetic_document
        from backend.app.services.cv_renderer import render_html
        from backend.app.schemas.resume import Presentation
        initial = self.b.get('/api/cv/templates').json()
        response = self.a.post('/api/admin/templates', json=self.template())
        self.assertEqual(response.status_code, 201, response.text)
        item = response.json()
        self.assertTrue(item['id'].startswith('custom_'))
        self.assertEqual(len(self.b.get('/api/cv/templates').json()), len(initial) + 1)
        presentation = Presentation(template=item['id'], color=item['color'], font=item['font'])
        document = synthetic_document()
        before = render_html(document, item['id'], presentation.model_dump())
        self.assertIn('Nguyễn Minh An', before)
        self.assertIn('font-family:CatalogFont,sans-serif!important', before)
        self.assertIn('--accent:#6543ab', before)
        hidden = {**self.template(), 'name':'Mẫu đã sửa', 'enabled':False, 'expected_revision':1}
        response = self.a.put('/api/admin/templates/' + item['id'], json=hidden)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()['revision'], 2)
        self.assertEqual(len(self.b.get('/api/cv/templates').json()), len(initial))
        self.assertEqual(metadata(item['id'])['name'], 'Mẫu đã sửa')
        self.assertEqual(self.a.put('/api/admin/templates/' + item['id'], json=hidden).status_code, 409)
        self.assertEqual(self.a.request('DELETE', '/api/admin/templates/' + item['id'], json={'expected_revision':1}).status_code, 409)
        removed = self.a.request('DELETE', '/api/admin/templates/' + item['id'], json={'expected_revision':2})
        self.assertEqual(removed.status_code, 200, removed.text)
        self.assertFalse(any(t['id']==item['id'] for t in self.a.get('/api/admin/templates').json()))
        self.assertEqual(before, render_html(document, item['id'], presentation.model_dump()))
        self.assertTrue(metadata(item['id'])['deleted'])
        activity = self.a.get('/api/admin/activity').text
        for action in ('template.create','template.update','template.delete'):
            self.assertIn(action, activity)

    def test_template_permissions_validation_and_base_edits(self):
        self.register(self.b)
        self.assertEqual(self.b.post('/api/admin/templates', json=self.template()).status_code, 403)
        self.assertEqual(self.b.put('/api/admin/templates/simple', json={**self.template(), 'expected_revision':0}).status_code, 403)
        self.assertEqual(self.b.request('DELETE', '/api/admin/templates/simple', json={'expected_revision':0}).status_code, 403)
        self.a.headers.pop('X-KLTN-CSRF')
        self.assertEqual(self.a.post('/api/admin/templates', json=self.template()).status_code, 403)
        response = self.a.post('/api/auth/login', json={'email':'admin@example.test','password':json.loads(self.credential_path.read_text())['password']})
        self.a.headers['X-KLTN-CSRF'] = response.json()['csrf_token']
        for changes in ({'base_template':'not-a-layout'},{'color':'red'},{'category':'unknown'},{'name':'   '}):
            self.assertEqual(self.a.post('/api/admin/templates', json={**self.template(),**changes}).status_code, 422)
        updated = self.a.put('/api/admin/templates/simple', json={**self.template(), 'name':'Mẫu hệ thống đã sửa', 'expected_revision':0})
        self.assertEqual(updated.status_code, 200, updated.text)
        self.assertEqual(next(t for t in self.b.get('/api/cv/templates').json() if t['id']=='simple')['name'], 'Mẫu hệ thống đã sửa')
        self.assertEqual(self.a.put('/api/admin/templates/simple', json={**self.template(), 'base_template':'modern', 'expected_revision':1}).status_code, 422)
        self.assertEqual(self.a.request('DELETE', '/api/admin/templates/simple', json={'expected_revision':1}).status_code, 200)
        self.assertTrue(any(t['id']=='simple' for t in self.a.get('/api/admin/templates/bases').json()))

    def test_last_visible_template_cannot_be_hidden_or_deleted(self):
        items = self.a.get('/api/admin/templates').json()
        for item in items[1:]:
            result = self.a.request('DELETE', '/api/admin/templates/' + item['id'], json={'expected_revision':item['revision']})
            self.assertEqual(result.status_code, 200, result.text)
        last = items[0]
        self.assertEqual(self.a.request('DELETE', '/api/admin/templates/' + last['id'], json={'expected_revision':last['revision']}).status_code, 409)
        payload = {key:last[key] for key in ('name','description','base_template','category','color','font')}
        self.assertEqual(self.a.put('/api/admin/templates/' + last['id'], json={**payload,'enabled':False,'expected_revision':last['revision']}).status_code, 409)

    def test_custom_templates_use_every_supported_layout_and_export_after_removal(self):
        from backend.app.services import template_catalog
        from backend.app.services.cv_templates import synthetic_document
        from backend.app.services.cv_renderer import render_html, render_pdf
        from backend.app.schemas.resume import Presentation
        import pymupdf
        document = synthetic_document()
        for base in template_catalog.base_templates():
            with self.subTest(base=base['id']):
                item = template_catalog.save(self.admin_id, self.template(base_template=base['id'], font='serif'))
                presentation = Presentation(template=item['id'], template_version=3, font='serif', color=item['color'])
                html = render_html(document, item['id'], presentation.model_dump())
                self.assertIn('Nguyễn Minh An', html)
                self.assertIn('font-family:CatalogFont,serif!important', html)
                self.assertEqual(item['has_photo'], base['has_photo'])
                template_catalog.delete(self.admin_id, item['id'], 1)
                if base['id'] == 'simple':
                    with pymupdf.open(stream=render_pdf(document, item['id'], presentation.model_dump()), filetype='pdf') as pdf:
                        text = ' '.join(page.get_text() for page in pdf)
                        self.assertIn('Nguyễn Minh An', text)


if __name__ == '__main__': unittest.main()
