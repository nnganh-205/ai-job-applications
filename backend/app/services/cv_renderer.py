"""Two text-first CV layouts. Escaped HTML preview and in-memory PDF, no shell calls."""

import io
import os
from html import escape
from pathlib import Path

import pymupdf as fitz

from backend.app.schemas.cv import CVDocument


TEMPLATES = [
    {'id': 'ats', 'name': 'ATS đơn giản', 'description': 'Một cột, tiêu đề rõ, không bảng hoặc hình ảnh.'},
    {'id': 'classic', 'name': 'Truyền thống', 'description': 'Một cột, tên căn giữa và đường phân cách từng phần.'},
]


def render_html(document: CVDocument, template='ats') -> str:
    if template not in {'ats', 'classic'}:
        raise ValueError('Mẫu CV không tồn tại.')
    e = lambda value: escape(str(value), quote=True)
    contact = document.contact
    details = [getattr(contact, field) for field in ('email', 'phone', 'location', 'city', 'state_or_province', 'country', 'linkedin', 'github', 'website', 'portfolio_url') if getattr(contact, field)]
    body = f'<header><h1>{e(contact.full_name or "CV")}</h1><p>{e(" · ".join(dict.fromkeys(details)))}</p></header>'
    if document.summary:
        body += f'<h2>{"Tóm tắt" if document.language == "vi" else "Summary"}</h2><p>{e(document.summary.text)}</p>'
    for section in document.sections:
        body += f'<section><h2>{e(section.heading)}</h2>'
        for entry in section.entries:
            body += f'<div class="entry"><h3>{e(entry.title)}</h3>'
            if entry.subtitle:
                body += f'<p class="subtitle">{e(entry.subtitle)}</p>'
            if entry.period:
                body += f'<p class="period">{e(entry.period)}</p>'
            if entry.bullets:
                body += '<ul>' + ''.join(f'<li>{e(bullet.text)}</li>' for bullet in entry.bullets) + '</ul>'
            body += '</div>'
        body += '</section>'
    classic = 'header{text-align:center} h2{border-bottom:1px solid #333;padding-bottom:4px} h1{font-family:serif}' if template == 'classic' else 'h2{color:#172b4d} header{text-align:left}'
    css = 'body{font-family:CVFont,Arial,sans-serif;font-size:10pt;color:#17212b;line-height:1.4;margin:0} h1{font-size:22pt;margin:0 0 8px} h2{font-size:12pt;margin:16px 0 7px} h3{font-size:10.5pt;margin:8px 0 2px} p{margin:3px 0} ul{margin:5px 0 10px;padding-left:18px} li{margin:3px 0;white-space:pre-wrap} .period{color:#495463} .subtitle{font-weight:bold} ' + classic
    return f'<!doctype html><html lang="{document.language}"><head><meta charset="utf-8"><style>{css}</style></head><body>{body}</body></html>'


def render_pdf(document: CVDocument, template='ats') -> bytes:
    candidates = [os.environ.get('CV_FONT_PATH'), '/System/Library/Fonts/Supplemental/Arial.ttf', '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf']
    font = next((Path(path) for path in candidates if path and Path(path).is_file()), None)
    if font is None:
        raise ValueError('Thiếu font Unicode. Cấu hình CV_FONT_PATH tới font TTF hỗ trợ tiếng Việt.')
    # Font names/paths are server configuration, never input from the CV.
    story = fitz.Story(html=render_html(document, template), user_css=f'@font-face{{font-family:CVFont;src:url("{font.name}")}}', archive=fitz.Archive(str(font.parent)))
    output = io.BytesIO()
    writer = fitz.DocumentWriter(output)
    page = fitz.paper_rect('a4')
    content = fitz.Rect(40, 36, page.width - 40, page.height - 36)
    try:
        for _ in range(12):
            device = writer.begin_page(page)
            more, _ = story.place(content)
            story.draw(device)
            writer.end_page()
            if not more:
                break
        else:
            raise ValueError('CV vượt giới hạn 12 trang; hãy rút gọn nội dung.')
    finally:
        writer.close()
    return output.getvalue()
