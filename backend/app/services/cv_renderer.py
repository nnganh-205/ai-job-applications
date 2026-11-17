"""Shared HTML/CSS for six CV previews and A4 PDFs, with isolated Chromium export."""
import base64
import functools
import os
from html import escape
from pathlib import Path
from threading import BoundedSemaphore

import pymupdf as fitz
from backend.app.core.config import PROJECT_ROOT
from backend.app.schemas.cv import CVDocument
from backend.app.services.cv_templates import TEMPLATES, metadata

_render_slots=BoundedSemaphore(2)


@functools.lru_cache(maxsize=2)
def font_data(font):
    name='NotoSerif' if font=='serif' else 'NotoSans'
    path=PROJECT_ROOT/'frontend/public/fonts'/f'{name}.ttf'
    if not path.is_file():raise ValueError('Thiếu font CV. Cần tải Noto Sans/Serif theo runbook.')
    return base64.b64encode(path.read_bytes()).decode('ascii')


def _section(section):
    e=lambda value:escape(str(value),quote=True)
    body=f'<section class="cv-section"><h2>{e(section.heading)}</h2>'
    for entry in section.entries:
        body+=f'<article class="entry"><h3>{e(entry.title)}</h3>'
        if entry.subtitle:body+=f'<p class="subtitle">{e(entry.subtitle)}</p>'
        if entry.period:body+=f'<p class="period">{e(entry.period)}</p>'
        if entry.bullets:body+='<ul>'+''.join(f'<li>{e(b.text)}</li>' for b in entry.bullets)+'</ul>'
        body+='</article>'
    return body+'</section>'


def render_html(document:CVDocument,template='ats',presentation=None):
    from backend.app.schemas.resume import Presentation
    if (presentation or {}).get('template_version')==1:
        from backend.app.services.cv_renderer_legacy import render_html as legacy_html
        return legacy_html(document,template,presentation)
    meta=metadata(template)
    options=Presentation.model_validate(presentation or {'template':template,'font':meta['font'],'color':meta['color']})
    e=lambda value:escape(str(value),quote=True)
    contact=document.contact
    details=[getattr(contact,k) for k in ('email','phone','location','city','state_or_province','country','linkedin','github','website','portfolio_url') if getattr(contact,k)]
    header=f'<header class="cv-header"><h1>{e(contact.full_name or "CV")}</h1><p class="contact">{e(" · ".join(dict.fromkeys(details)))}</p></header>'
    if options.photo_asset_id:
        from backend.app.services.assets import photo_data
        header=header.replace('<header class="cv-header">','<header class="cv-header has-photo"><img class="cv-photo" alt="Ảnh hồ sơ" src="'+photo_data(options.photo_asset_id)+'">')
    summary=f'<section class="cv-section"><h2>{"Tóm tắt" if document.language=="vi" else "Summary"}</h2><p>{e(document.summary.text)}</p></section>' if document.summary else ''
    if meta['layout']=='two-column':
        side=''.join(_section(s) for s in document.sections if s.kind in {'skills','education'})
        main=summary+''.join(_section(s) for s in document.sections if s.kind not in {'skills','education'})
        # Empty regions never hide or discard source content.
        body=header+f'<div class="columns"><aside>{side}</aside><div class="primary">{main}</div></div>' if side and main else header+summary+''.join(_section(s) for s in document.sections)
    else:body=header+summary+''.join(_section(s) for s in document.sections)
    css=f'''
    @font-face{{font-family:CVFont;src:url(data:font/ttf;base64,{font_data(options.font)}) format('truetype');font-weight:100 900;font-style:normal}}
    @page{{size:A4;margin:14mm}}
    *{{box-sizing:border-box}} html{{background:white}} body{{margin:0;color:#1e293b;font-family:CVFont,{'serif' if options.font=='serif' else 'sans-serif'};font-size:{options.font_size}pt;line-height:{options.line_height};overflow-wrap:anywhere;-webkit-print-color-adjust:exact;print-color-adjust:exact}}
    .cv-photo{{float:right;width:65pt;height:80pt;object-fit:cover;margin:0 0 10pt 16pt;border-radius:5pt}}.cv-header{{display:flow-root}}
    .sheet{{max-width:182mm;margin:0 auto}} h1{{font-size:27pt;line-height:1.15;letter-spacing:-.025em;margin:0 0 9pt;font-weight:700;color:{options.color}}} h2{{font-size:11pt;letter-spacing:.06em;text-transform:uppercase;color:{options.color};margin:17pt 0 8pt;padding-bottom:5pt;border-bottom:1px solid #dbe3ee;break-after:avoid}} h3{{font-size:10.5pt;margin:10pt 0 3pt;break-after:avoid}} p{{margin:4pt 0}} .contact{{font-size:8.5pt;color:#526277;line-height:1.6;overflow-wrap:anywhere}} .cv-header{{padding-bottom:12pt;border-bottom:2px solid {options.color};break-inside:avoid}} .subtitle{{font-weight:600}} .period{{font-size:8.5pt;color:#64748b}} ul{{padding-left:14pt;margin:5pt 0 9pt}} li{{margin:3pt 0;white-space:pre-wrap}} .columns{{display:grid;grid-template-columns:minmax(0,31%) minmax(0,1fr);gap:20pt;align-items:start}} aside{{font-size:.94em}} .cv-section{{margin:0}} .entry{{margin-bottom:10pt}} .template-classic .cv-header{{text-align:center;border-bottom:1px solid #334155}} .template-academic h1{{font-size:24pt;color:#202c3b}} .template-academic h2{{text-transform:none;letter-spacing:0;font-size:12pt;color:#202c3b;border-color:#64748b}} .template-creative .cv-header{{border-left:7pt solid {options.color};border-bottom:0;padding:12pt 16pt;background:#f7f4fb}} .template-sidebar aside{{background:#f1f6f6;padding:0 10pt 10pt;border-top:4pt solid {options.color}}} .template-modern aside{{border-right:1px solid #dce4f0;padding-right:12pt}} @media screen{{body{{padding:20px}}}} @media print{{body{{padding:0}}.sheet{{max-width:none}}}}
    '''
    return f'<!doctype html><html lang="{document.language}"><head><meta charset="utf-8"><meta http-equiv="Content-Security-Policy" content="default-src \'none\'; style-src \'unsafe-inline\'; font-src data:; img-src data:; base-uri \'none\'"><style>{css}</style></head><body><div class="sheet template-{template}">{body}</div></body></html>'


def render_pdf(document:CVDocument,template='ats',presentation=None):
    if (presentation or {}).get('template_version')==1:
        from backend.app.services.cv_renderer_legacy import render_pdf as legacy_pdf
        return legacy_pdf(document,template,presentation)
    # This is an application PDF renderer, isolated from the user's browser profile.
    from playwright.sync_api import sync_playwright, Error as PlaywrightError
    html=render_html(document,template,presentation)
    try:
        with _render_slots,sync_playwright() as engine:
            browser=engine.chromium.launch(headless=True,executable_path=os.getenv('CV_CHROME_BINARY') or None,timeout=20000)
            try:
                context=browser.new_context(offline=True,java_script_enabled=False)
                page=context.new_page();page.set_default_timeout(20000)
                page.set_content(html,wait_until='load')
                page.evaluate('document.fonts.ready')
                content=page.pdf(format='A4',print_background=True,prefer_css_page_size=True,display_header_footer=False)
            finally:browser.close()
    except PlaywrightError as error:
        raise ValueError('Không xuất được PDF. Kiểm tra Chromium bằng python -m playwright install chromium --only-shell; nội dung CV được giữ nguyên.') from error
    with fitz.open(stream=content,filetype='pdf') as pdf:
        if not 1<=len(pdf)<=12:raise ValueError('CV vượt giới hạn 12 trang; hãy rút gọn nội dung.')
    return content
