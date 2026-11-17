"""Private, content-addressed raster photos; decoded/re-encoded without EXIF."""
import base64
import hashlib
import io
import os
import re
import tempfile
import warnings
from pathlib import Path
from PIL import Image,ImageOps,UnidentifiedImageError
from backend.app.core.config import PROJECT_ROOT
from backend.app.db import workflow_repository as records
from backend.app.db.job_posting_repository import utc_now

MAX_UPLOAD=5*1024*1024
OWNER_ID=os.getenv('WORKSPACE_OWNER_ID','local-demo')


def storage():return Path(os.getenv('KLTN_ASSET_STORAGE',str(PROJECT_ROOT/'backend/storage/assets')))


def save_photo(content):
    if len(content)>MAX_UPLOAD:raise ValueError('Ảnh vượt quá giới hạn 5 MB')
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error',Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(content)) as source:
                if source.format not in {'JPEG','PNG','WEBP'}:raise ValueError('Chỉ nhận ảnh JPEG, PNG hoặc WebP')
                if source.width*source.height>16_000_000 or min(source.size)<64:raise ValueError('Ảnh cần từ 64px mỗi chiều và không vượt 16 megapixel')
                image=ImageOps.exif_transpose(source).convert('RGBA')
                image.thumbnail((640,800),Image.Resampling.LANCZOS)
                result=Image.new('RGB',image.size,'white');result.paste(image,mask=image.getchannel('A'))
                output=io.BytesIO();result.save(output,format='PNG',optimize=True)
    except (UnidentifiedImageError,OSError,Image.DecompressionBombError,Image.DecompressionBombWarning) as error:
        raise ValueError('Không đọc được ảnh an toàn. Hãy chọn JPEG, PNG hoặc WebP khác.') from error
    data=output.getvalue();checksum=hashlib.sha256(data).hexdigest();asset_id='asset_'+checksum
    root=storage();root.mkdir(parents=True,exist_ok=True);path=root/(asset_id+'.png')
    with tempfile.NamedTemporaryFile(dir=root,delete=False) as f:
        temporary=Path(f.name);f.write(data);f.flush();os.fsync(f.fileno())
    try:
        try:os.link(temporary,path)
        except FileExistsError:pass
    finally:temporary.unlink(missing_ok=True)
    meta={'asset_id':asset_id,'checksum':checksum,'width':result.width,'height':result.height,'mime':'image/png','owner_id':OWNER_ID,'created_at':utc_now()}
    records.put('assets',asset_id,meta)
    return meta


def read_photo(asset_id):
    if not re.fullmatch(r'asset_[a-f0-9]{64}',asset_id):raise ValueError('ID ảnh không hợp lệ')
    meta=records.get('assets',asset_id)
    if meta is None or meta.get('owner_id')!=OWNER_ID:raise LookupError('Không tìm thấy ảnh của workspace')
    path=storage()/(asset_id+'.png')
    if not path.is_file():raise LookupError('File ảnh không còn trong storage')
    data=path.read_bytes()
    if hashlib.sha256(data).hexdigest()!=meta['checksum']:raise ValueError('Ảnh không khớp checksum đã lưu')
    return data


def photo_data(asset_id):return 'data:image/png;base64,'+base64.b64encode(read_photo(asset_id)).decode('ascii')
