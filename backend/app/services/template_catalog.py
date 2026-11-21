"""Shared, editable template catalog. Tombstones retain renderers for saved CVs."""
from copy import deepcopy
import json
import time
from uuid import uuid4

from backend.app.db import auth_repository as accounts
from backend.app.services.administration import AdminConflict, audit
from backend.app.schemas.template_design import TemplateDesign, SECTION_KEYS


def _builtins():
    from backend.app.services.cv_templates import TEMPLATES
    return {item['id']: {**deepcopy(item), 'base_template': item['id'],
                         'enabled': item.get('available', True), 'revision': 0,
                         'deleted': False, 'origin': 'builtin'} for item in TEMPLATES}


def _catalog(store):
    result = _builtins()
    for row in store.execute('SELECT template_id,payload FROM admin_templates').fetchall():
        result[row['template_id']] = json.loads(row['payload'])
    return result


def list_templates(*, admin=False):
    with accounts.transaction() as store:
        items = list(_catalog(store).values())
    return [item for item in items if item.get('available', True) and not item['deleted']
            and (admin or item['enabled'])]


def base_templates():
    return [item for item in _builtins().values() if item.get('available', True)]


def _design_metadata(values):
    from backend.app.schemas.profile import Contact
    base = next(iter(base_templates()))
    design = TemplateDesign.model_validate(values['design']).model_dump()
    base.update(base_template=None, renderer='designed', design=design,
                layout=design['layout'], has_photo=design['show_photo'], available=True,
                page_width=794, page_height=1123, version=3, font_size=10, line_height=1.4,
                form_sections=['contact'] + [key for key in SECTION_KEYS if key != 'summary'] + ['summary'],
                contact_fields=list(Contact.model_fields), source='admin_design', source_url=None)
    for key in ('reference_file', 'source_template'):
        base.pop(key, None)
    return base


def preview(values):
    from backend.app.services.cv_templates import synthetic_document
    from backend.app.services.designed_templates import render_designed
    from backend.app.schemas.resume import Presentation
    if not values.get('design'):
        raise ValueError('Cần cấu hình bố cục để xem trước mẫu mới.')
    meta = _design_metadata(values)
    meta.update({key:values[key] for key in ('name', 'font', 'color')})
    return {'html': render_designed(synthetic_document(), meta, Presentation(template='simple', font=values['font'], color=values['color']))}


def get_metadata(template_id):
    with accounts.transaction() as store:
        item = _catalog(store).get(template_id)
    if item is None:
        raise ValueError('Mẫu CV không tồn tại.')
    return item


def _write(store, item):
    store.execute('INSERT INTO admin_templates(template_id,payload,updated_at) VALUES (?,?,?) '
                  'ON CONFLICT(template_id) DO UPDATE SET payload=excluded.payload,updated_at=excluded.updated_at',
                  (item['id'], json.dumps(item, ensure_ascii=False), time.time()))


def save(actor, values, template_id=None):
    with accounts.transaction() as store:
        if store.postgres:
            store.execute("SELECT pg_advisory_xact_lock(hashtext('kltn_template_catalog'))")
        items = _catalog(store)
        designed = bool(values.get('design'))
        base = _design_metadata(values) if designed else _builtins().get(values.get('base_template'))
        if base is None or not base.get('available', True):
            raise ValueError('Thiết kế bố cục mới hoặc chọn một bố cục CV được hỗ trợ.')
        if template_id:
            item = items.get(template_id)
            if item is None or item['deleted'] or not item.get('available', True):
                raise LookupError('Không tìm thấy mẫu CV.')
            if values.get('expected_revision') != item['revision']:
                raise AdminConflict('Mẫu CV đã thay đổi. Tải lại danh sách trước khi sửa.')
            if values.get('base_template') != item['base_template']:
                raise ValueError('Không đổi bố cục gốc của mẫu đã tạo. Hãy thêm mẫu mới.')
            item = deepcopy(item)
            if item.get('renderer') == 'designed' and not designed:
                raise ValueError('Mẫu thiết kế cần giữ cấu hình bố cục.')
            if designed:
                item.update({key:base[key] for key in ('design', 'layout', 'has_photo')})
        else:
            item = {**deepcopy(base), 'id': 'custom_' + uuid4().hex, 'origin': 'custom', 'revision': 0}
        for key in ('name', 'category', 'color', 'font', 'enabled'):
            item[key] = values[key].strip() if isinstance(values[key], str) else values[key]
        item['description'] = values.get('description', '').strip()
        if len(item['name']) < 3:
            raise ValueError('Điền tên mẫu CV từ 3 ký tự.')
        if designed:
            item['thumbnail'] = '/api/cv/templates/' + item['id'] + '/thumbnail'
        if not item['enabled'] and not any(t['id'] != item['id'] and t['enabled'] and not t['deleted'] and t.get('available', True) for t in items.values()):
            raise AdminConflict('Cần giữ ít nhất một mẫu CV đang hiển thị.')
        item['deleted'] = False
        item['revision'] += 1
        item['updated_at'] = time.time()
        _write(store, item)
        audit(store, actor, 'template.update' if template_id else 'template.create', item['id'], item['name'])
    return item


def delete(actor, template_id, expected_revision):
    with accounts.transaction() as store:
        if store.postgres:
            store.execute("SELECT pg_advisory_xact_lock(hashtext('kltn_template_catalog'))")
        items = _catalog(store)
        item = items.get(template_id)
        if item is None or item['deleted'] or not item.get('available', True):
            raise LookupError('Không tìm thấy mẫu CV.')
        if expected_revision != item['revision']:
            raise AdminConflict('Mẫu CV đã thay đổi. Tải lại danh sách trước khi xóa.')
        if item['enabled'] and sum(t['enabled'] and not t['deleted'] and t.get('available', True) for t in items.values()) <= 1:
            raise AdminConflict('Cần giữ ít nhất một mẫu CV đang hiển thị.')
        item.update(deleted=True, enabled=False, revision=item['revision'] + 1, updated_at=time.time())
        _write(store, item)
        audit(store, actor, 'template.delete', template_id, item['name'])
    return {'deleted': True}
