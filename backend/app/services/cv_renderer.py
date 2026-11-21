"""Shared HTML/CSS for CV previews and A4 PDFs, with isolated Chromium export."""
import base64
import functools
import os
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


def render_html(document:CVDocument,template='ats',presentation=None):
    from backend.app.services.project_headers import decorate_projects
    from backend.app.schemas.resume import Presentation
    if (presentation or {}).get('template_version')==1:
        from backend.app.services.cv_renderer_legacy import render_html as legacy_html
        return legacy_html(document,template,presentation)
    meta=metadata(template)
    defaults={'template':template,'font':meta['font'],'color':meta['color'],'font_size':meta.get('font_size',10),'line_height':meta.get('line_height',1.4)}
    options=Presentation.model_validate({**defaults,**(presentation or {})})
    if meta.get('renderer') == 'designed':
        from backend.app.services.designed_templates import render_designed
        return decorate_projects(render_designed(document,meta,options),document)
    # Catalog entries reuse a supported renderer while keeping their own ID/defaults.
    template=meta.get('base_template', template)
    options=options.model_copy(update={'template': template})
    if meta.get('renderer') == 'pdf_reference':
        if template in {'classic','academic','harvard'}:
            from backend.app.services.harvard_reference_templates import render_harvard
            html=render_harvard(document,template,options)
        elif template in {'modern','sidebar','metro','split'}:
            from backend.app.services.modern_reference_templates import render_modern
            html=render_modern(document,template,options)
        elif template in {'executive','corporate','consultant','precision'}:
            from backend.app.services.professional_reference_templates import render_professional
            html=render_professional(document,template,options)
        else:
            from backend.app.services.simple_reference_templates import render_reference
            html=render_reference(document,template,options)
    else:
        from backend.app.services.topcv_renderer import render_topcv
        html=render_topcv(document,template,options)
    if meta.get('origin') == 'custom' or meta.get('revision', 0):
        # Managed templates must honor the font selected by the administrator.
        font_css='@font-face{font-family:CatalogFont;src:url(data:font/ttf;base64,'+font_data(options.font)+')}body{font-family:CatalogFont,'+('serif' if options.font=='serif' else 'sans-serif')+'!important}'
        if template in {'classic','academic','harvard'}:
            font_css+=':root{--accent:'+options.color+'}.harvard-header h1,.harvard-section h2{color:var(--accent)}'
        html=html.replace('</style>',font_css+'</style>',1)
    return decorate_projects(html,document)


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
