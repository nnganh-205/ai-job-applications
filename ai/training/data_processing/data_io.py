"""Đọc/ghi JSON nhiều dòng, dùng chung cho toàn bộ pipeline."""
import hashlib
import json


def read_json(path):
    """Đọc file JSON thành list hoặc dict của Python."""
    with path.open(encoding='utf-8') as file:
        return json.load(file)


def write_json(path, data, immutable=False):
    """Ghi JSON dễ đọc; bảo vệ bản gốc nếu immutable=True."""
    content = json.dumps(data, ensure_ascii=False, indent=2) + '\n'
    if immutable and path.exists():
        if path.read_text(encoding='utf-8') != content:
            raise RuntimeError(f'Refusing to overwrite raw snapshot: {path}')
    else:
        path.write_text(content, encoding='utf-8')
    return hashlib.sha256(content.encode('utf-8')).hexdigest()
