from io import BytesIO
import re
from pathlib import Path
from zipfile import ZipFile
from urllib.parse import urlsplit

import pymupdf
from docx import Document
from docx.table import Table


MAX_FILE_SIZE = 5 * 1024 * 1024
SUPPORTED_EXTENSIONS = {".pdf", ".docx"}


class DocumentReadError(ValueError):
    """Lỗi file CV không thể xử lý ở phiên bản hiện tại."""


def _safe_link(value: str) -> bool:
    # Preserve document metadata as text only; never request these URLs.
    try:
        parsed = urlsplit(value)
        return parsed.scheme.lower() in {"https", "http", "mailto", "tel"} and not any(char in value for char in "\n\r")
    except ValueError:
        return False


def _paragraph_text(paragraph) -> str:
    text = paragraph.text.strip()
    links = []
    for link in paragraph.hyperlinks:
        if link.url and _safe_link(link.url) and link.url not in text and link.url not in links:
            links.append(link.url)
    return " ".join([text, *links]).strip()


def validate_cv_file(filename: str, file_bytes: bytes) -> str:
    extension = Path(filename).suffix.lower()
    if extension not in SUPPORTED_EXTENSIONS:
        raise DocumentReadError("Chỉ hỗ trợ file PDF hoặc DOCX")
    if not file_bytes:
        raise DocumentReadError("File CV đang rỗng")
    if len(file_bytes) > MAX_FILE_SIZE:
        raise DocumentReadError("File CV vượt quá giới hạn 5 MB")
    return extension


def _reading_order(blocks, width, height):
    blocks = [block for block in blocks if block[4].strip() and (len(block) < 7 or block[6] == 0)]
    headers = [b for b in blocks if b[2] - b[0] > width * .55 and b[3] < height * .22]
    footers = [b for b in blocks if b[1] > height * .94 and b[3] - b[1] < 30
               and re.search(r'©|copyright|^(?:page|trang)\s+\d|^\s*\d+\s*(?:/|of)\s*\d+\s*$', b[4], re.I)]
    body = [b for b in blocks if b not in headers and b not in footers]
    intervals = []
    for block in sorted(body, key=lambda b: b[0]):
        if intervals and block[0] <= intervals[-1][1]:
            intervals[-1][1] = max(intervals[-1][1], block[2])
        else:
            intervals.append([block[0], block[2]])
    cuts = []
    for left, right in zip(intervals, intervals[1:]):
        if right[0] - left[1] < max(12, width * .02):
            continue
        cut = (left[1] + right[0]) / 2
        before = [b for b in body if b[2] < cut]
        after = [b for b in body if b[0] > cut]
        if len(before) >= 3 and len(after) >= 3:
            overlap = min(max(b[3] for b in before), max(b[3] for b in after)) - max(min(b[1] for b in before), min(b[1] for b in after))
            if overlap >= height * .15:
                cuts.append(cut)
    if not cuts:
        return sorted(blocks, key=lambda b: (b[1], b[0]))
    columns = [[] for _ in range(len(cuts) + 1)]
    for block in body:
        columns[sum(block[0] > cut for cut in cuts)].append(block)
    order = lambda values: sorted(values, key=lambda b: (b[1], b[0]))
    return order(headers) + [b for column in columns for b in order(column)] + order(footers)


def read_pdf(file_bytes: bytes) -> str:
    try:
        with pymupdf.open(stream=file_bytes, filetype="pdf") as document:
            if document.needs_pass:
                raise DocumentReadError("PDF có mật khẩu; cần bỏ mật khẩu trước khi upload")
            pages = []
            for page in document:
                textpage = page.get_textpage()
                blocks = _reading_order(page.get_text("blocks", textpage=textpage), page.rect.width, page.rect.height)
                links = page.get_links()
                lines = []
                for block in blocks:
                    text = block[4].strip()
                    if not text:
                        continue
                    lines.append(text)
                    for link in links:
                        uri = link.get("uri", "")
                        if uri and _safe_link(uri) and pymupdf.Rect(block[:4]).intersects(link["from"]) and uri not in text:
                            label = page.get_textbox(link["from"], textpage=textpage).strip().replace("\n", " ")
                            lines.append(f"{label}: {uri}" if label else uri)
                pages.append("\n\n".join(lines))
    except DocumentReadError:
        raise
    except Exception as error:
        raise DocumentReadError("Không thể đọc file PDF") from error

    text = "\n\n".join(page for page in pages if page).strip()
    if not text:
        raise DocumentReadError("PDF không có lớp văn bản; file này cần OCR")
    return text


def read_docx(file_bytes: bytes) -> str:
    try:
        with ZipFile(BytesIO(file_bytes)) as archive:
            if len(archive.infolist()) > 1000 or sum(item.file_size for item in archive.infolist()) > 25 * 1024 * 1024:
                raise DocumentReadError("DOCX vượt giới hạn nội dung giải nén 25 MB hoặc 1000 thành phần")
        document = Document(BytesIO(file_bytes))
    except DocumentReadError:
        raise
    except Exception as error:
        raise DocumentReadError("Không thể đọc file DOCX") from error

    lines = []
    seen_headers = set()
    for section in document.sections:
        header = "\n".join(filter(None, (_paragraph_text(p) for p in section.header.paragraphs)))
        if header and header not in seen_headers:
            lines.append(header)
            seen_headers.add(header)
    # Preserve interleaved body paragraph/table order, rather than appending all tables last.
    for block in document.iter_inner_content():
        if isinstance(block, Table):
            for row in block.rows:
                values = ["\n".join(filter(None, (_paragraph_text(p) for p in cell.paragraphs))) for cell in row.cells]
                values = [value for value in values if value]
                if values:
                    lines.append(" | ".join(values))
        else:
            text = _paragraph_text(block)
            if text:
                lines.append(text)
    seen_footers = set()
    for section in document.sections:
        footer = "\n".join(filter(None, (_paragraph_text(p) for p in section.footer.paragraphs)))
        if footer and footer not in seen_footers:
            lines.append(footer)
            seen_footers.add(footer)
    text = "\n".join(line for line in lines if line).strip()
    if not text:
        raise DocumentReadError("DOCX không có nội dung văn bản")
    return text


def read_cv(filename: str, file_bytes: bytes) -> str:
    extension = validate_cv_file(filename, file_bytes)
    if extension == ".pdf":
        return read_pdf(file_bytes)
    return read_docx(file_bytes)

