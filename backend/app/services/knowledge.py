"""Shared, versioned RAG sources. Draft and archived sources never enter retrieval."""
import hashlib
import json
import time
from datetime import date
from urllib.parse import urlsplit
from uuid import uuid4
from backend.app.db import auth_repository as repository
from backend.app.services.administration import AdminConflict, audit


def encode(value):
    return json.dumps(value, ensure_ascii=False, separators=(',', ':'))


def builtin_id(filename):
    return 'source_' + hashlib.sha256(filename.encode()).hexdigest()[:24]


def initialize_sources():
    from ai.rag.labor_law import load_index
    groups = {}
    for chunk in load_index():
        groups.setdefault(chunk['file'], []).append(chunk)
    with repository.transaction() as store:
        for filename, chunks in groups.items():
            first = chunks[0]
            value = dict(document_id=builtin_id(filename), title=first['title'], url=first['url'], effective=first['effective'],
                         file=filename, origin='builtin', status='published', version=1, chunks=chunks,
                         created_at=time.time(), updated_at=time.time())
            store.execute('INSERT INTO admin_documents(document_id,payload,updated_at) VALUES (?,?,?) ON CONFLICT(document_id) DO NOTHING',
                          (value['document_id'], encode(value), value['updated_at']))


def all_documents():
    with repository.transaction() as store:
        rows = store.execute('SELECT payload FROM admin_documents ORDER BY updated_at DESC').fetchall()
    return [json.loads(row['payload']) for row in rows]


def summary(value):
    return {**{k: v for k, v in value.items() if k not in {'chunks', 'text'}}, 'chunk_count': len(value['chunks'])}


def list_documents():
    return [summary(value) for value in all_documents()]


def detail(document_id):
    with repository.transaction() as store:
        row = store.execute('SELECT payload FROM admin_documents WHERE document_id=?', (document_id,)).fetchone()
    if row is None: raise LookupError('Không tìm thấy tài liệu.')
    value = json.loads(row['payload'])
    # Existing page/article boundaries remain intact unless the administrator edits the text.
    return {**summary(value), 'text': value.get('text', '\n\n'.join(chunk['text'] for chunk in value['chunks']))}


def validate(payload):
    title = payload['title'].strip()
    text = payload['text'].strip()
    url = payload.get('url', '').strip()
    effective = payload.get('effective', '').strip()
    if not 3 <= len(title) <= 200: raise ValueError('Tên tài liệu cần từ 3 đến 200 ký tự.')
    if not 80 <= len(text) <= 500000: raise ValueError('Nội dung cần từ 80 đến 500.000 ký tự.')
    if url:
        try:
            parsed = urlsplit(url)
            if parsed.scheme not in {'https', 'http'} or not parsed.hostname or parsed.username or parsed.password or any(c.isspace() for c in url):
                raise ValueError()
        except ValueError:
            raise ValueError('Đường dẫn nguồn cần là URL http hoặc https hợp lệ.')
    if effective:
        try: date.fromisoformat(effective)
        except ValueError: raise ValueError('Ngày hiệu lực cần có dạng YYYY-MM-DD.')
    return title, text, url, effective


def split_text(text, document):
    from ai.rag.labor_law import ARTICLE
    rows = []
    matches = list(ARTICLE.finditer(text))
    sections = [(None, text[:matches[0].start()])] if matches else [(None, text)]
    sections.extend(('Điều ' + match.group(1), text[match.start():matches[i+1].start() if i+1 < len(matches) else len(text)])
                    for i, match in enumerate(matches))
    for article, section in sections:
        for start in range(0, len(section), 1200):
            chunk = section[start:start + 1350].strip()
            if len(chunk) < 40: continue
            rows.append(dict(id=f"{document['document_id']}:{document['version']}:{len(rows)+1}",
                             file=document['file'], title=document['title'], url=document['url'], effective=document['effective'],
                             article=article, page=None, text=chunk))
    return rows


def save(actor, payload, document_id=None, *, original_chunks=None):
    title, text, url, effective = validate(payload)
    with repository.transaction() as store:
        if document_id:
            suffix = ' FOR UPDATE' if store.postgres else ''
            row = store.execute('SELECT payload FROM admin_documents WHERE document_id=?' + suffix, (document_id,)).fetchone()
            if row is None: raise LookupError('Không tìm thấy tài liệu.')
            value = json.loads(row['payload'])
            if value['version'] != payload.get('expected_version'): raise AdminConflict('Tài liệu đã thay đổi. Tải lại trước khi lưu.')
            old_text = value.get('text', '\n\n'.join(c['text'] for c in value['chunks']))
            preserve_chunks = old_text.strip() == text
            value['version'] += 1
        else:
            document_id = 'source_' + uuid4().hex
            value = dict(document_id=document_id, file=document_id + '.txt', origin='uploaded' if original_chunks else 'manual', version=1, created_at=time.time())
            preserve_chunks = False
        value.update(title=title, text=text, url=url, effective=effective, status=payload.get('status', 'draft'), updated_at=time.time())
        if preserve_chunks:
            value['chunks'] = [{**chunk, 'title': title, 'url': url, 'effective': effective} for chunk in value['chunks']]
        elif original_chunks:
            value['chunks'] = [{**chunk, 'id': f'{document_id}:1:{i}', 'file': value['file'], 'title': title, 'url': url, 'effective': effective} for i, chunk in enumerate(original_chunks, 1)]
        else:
            value['chunks'] = split_text(text, value)
        store.execute('INSERT INTO admin_documents(document_id,payload,updated_at) VALUES (?,?,?) ON CONFLICT(document_id) DO UPDATE SET payload=excluded.payload,updated_at=excluded.updated_at',
                      (document_id, encode(value), value['updated_at']))
        audit(store, actor, 'knowledge.update' if value['version'] > 1 else 'knowledge.create', document_id, title + ' · ' + value['status'])
    return summary(value)


def change_status(actor, document_id, status, expected_version):
    # State-only edits do not concatenate/rechunk the original PDF source.
    with repository.transaction() as store:
        suffix = ' FOR UPDATE' if store.postgres else ''
        row = store.execute('SELECT payload FROM admin_documents WHERE document_id=?' + suffix, (document_id,)).fetchone()
        if row is None: raise LookupError('Không tìm thấy tài liệu.')
        value = json.loads(row['payload'])
        if value['version'] != expected_version: raise AdminConflict('Tài liệu đã thay đổi. Tải lại trước khi lưu.')
        value.update(status=status, version=value['version'] + 1, updated_at=time.time())
        store.execute('UPDATE admin_documents SET payload=?,updated_at=? WHERE document_id=?', (encode(value), value['updated_at'], document_id))
        audit(store, actor, 'knowledge.status', document_id, value['title'] + ' · ' + status)
    return summary(value)


def upload_pdf(actor, content, payload):
    import pymupdf
    if not content.startswith(b'%PDF-'): raise ValueError('Tệp tải lên cần là PDF hợp lệ.')
    try:
        with pymupdf.open(stream=content, filetype='pdf') as pdf:
            if pdf.is_encrypted: raise ValueError('PDF đang được bảo vệ bằng mật khẩu.')
            if pdf.page_count > 300: raise ValueError('Mỗi PDF tối đa 300 trang.')
            chunks, texts = [], []
            for page_no, page in enumerate(pdf, 1):
                text = page.get_text(sort=True).strip()
                texts.append(text)
                if sum(map(len, texts)) > 500000: raise ValueError('Nội dung PDF vượt quá 500.000 ký tự.')
                for start in range(0, len(text), 1200):
                    chunk = text[start:start + 1350].strip()
                    if len(chunk) >= 40: chunks.append(dict(text=chunk, page=page_no, article=None))
    except (pymupdf.FileDataError, RuntimeError) as error:
        raise ValueError('Không đọc được nội dung PDF.') from error
    if not chunks: raise ValueError('PDF chưa có lớp văn bản. Hãy OCR trước khi tải lên.')
    return save(actor, {**payload, 'text': '\n\n'.join(texts)}, original_chunks=chunks)


def retrieval_rows(fallback):
    documents = all_documents()
    if not documents:
        return fallback
    return [chunk for document in documents if document['status'] == 'published' for chunk in document['chunks']]
