from io import BytesIO
from pathlib import Path

import pymupdf
from docx import Document


MAX_FILE_SIZE = 5 * 1024 * 1024
SUPPORTED_EXTENSIONS = {".pdf", ".docx"}


class DocumentReadError(ValueError):
    """Lỗi file CV không thể xử lý ở phiên bản hiện tại."""


def validate_cv_file(filename: str, file_bytes: bytes) -> str:
    extension = Path(filename).suffix.lower()
    if extension not in SUPPORTED_EXTENSIONS:
        raise DocumentReadError("Chỉ hỗ trợ file PDF hoặc DOCX")
    if not file_bytes:
        raise DocumentReadError("File CV đang rỗng")
    if len(file_bytes) > MAX_FILE_SIZE:
        raise DocumentReadError("File CV vượt quá giới hạn 5 MB")
    return extension


def read_pdf(file_bytes: bytes) -> str:
    try:
        document = pymupdf.open(stream=file_bytes, filetype="pdf")
    except Exception as error:
        raise DocumentReadError("Không thể đọc file PDF") from error

    pages = []
    for page in document:
        # Dùng tọa độ block để giữ thứ tự đọc tốt hơn với CV nhiều cột.
        blocks = sorted(page.get_text("blocks"), key=lambda block: (block[1], block[0]))
        page_text = "\n".join(block[4].strip() for block in blocks if block[4].strip())
        pages.append(page_text)
    document.close()

    text = "\n\n".join(page for page in pages if page).strip()
    if not text:
        raise DocumentReadError("PDF không có lớp văn bản; file này cần OCR")
    return text


def read_docx(file_bytes: bytes) -> str:
    try:
        document = Document(BytesIO(file_bytes))
    except Exception as error:
        raise DocumentReadError("Không thể đọc file DOCX") from error

    lines = [paragraph.text.strip() for paragraph in document.paragraphs]
    for table in document.tables:
        for row in table.rows:
            values = [cell.text.strip() for cell in row.cells if cell.text.strip()]
            if values:
                lines.append(" | ".join(values))
    text = "\n".join(line for line in lines if line).strip()
    if not text:
        raise DocumentReadError("DOCX không có nội dung văn bản")
    return text


def read_cv(filename: str, file_bytes: bytes) -> str:
    extension = validate_cv_file(filename, file_bytes)
    if extension == ".pdf":
        return read_pdf(file_bytes)
    return read_docx(file_bytes)

