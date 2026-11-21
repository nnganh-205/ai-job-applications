"""Render newly designed layouts directly from structured, grounded CV data."""
from html import escape
from backend.app.schemas.template_design import TemplateDesign

LABELS = {'summary':'Giới thiệu', 'education':'Học vấn', 'experience':'Kinh nghiệm',
          'project':'Dự án', 'skills':'Kỹ năng', 'certifications':'Chứng chỉ',
          'awards':'Giải thưởng', 'references':'Người giới thiệu', 'involvement':'Hoạt động'}


def render_designed(document, meta, options):
    from backend.app.services.cv_renderer import font_data
    from backend.app.schemas.profile import Contact
    design = TemplateDesign.model_validate(meta['design'])
    sections = {section.kind: section for section in document.sections}

    def section(key):
        if key == 'summary':
            if not document.summary:
                return ''
            title = 'Giới thiệu' if document.language == 'vi' else 'Summary'
            content = '<p>' + escape(document.summary.text) + '</p>'
        else:
            data = sections.get(key)
            if data is None or not data.entries:
                return ''
            title = data.heading
            content = ''
            for entry in data.entries:
                content += '<article class="designed-entry"><div class="entry-top"><h3>' + escape(entry.title) + '</h3>'
                if entry.period:
                    content += '<span class="period">' + escape(entry.period) + '</span>'
                content += '</div>'
                if entry.subtitle:
                    content += '<p class="entry-subtitle">' + escape(entry.subtitle) + '</p>'
                if entry.bullets:
                    content += '<ul>' + ''.join('<li>' + escape(b.text) + '</li>' for b in entry.bullets) + '</ul>'
                content += '</article>'
        return '<section class="designed-section section-' + key + '"><h2>' + escape(title) + '</h2>' + content + '</section>'

    photo = ''
    if design.show_photo:
        from backend.app.services.simple_reference_templates import AVATAR
        import base64
        source = 'data:image/svg+xml;base64,' + base64.b64encode(AVATAR.encode()).decode()
        if options.photo_asset_id:
            from backend.app.services.assets import photo_data
            source = photo_data(options.photo_asset_id)
        photo = '<img class="designed-photo" src="' + source + '" alt="Ảnh đại diện">'
    contact = document.contact
    contacts = []
    # Preserve every supplied contact field, rather than dropping data for a layout.
    for key in Contact.model_fields:
        value = getattr(contact, key)
        if value and key not in {'full_name', 'headline'}:
            contacts.append('<span>' + escape(str(value)) + '</span>')
    header = '<header class="designed-header">' + photo + '<div><h1>' + escape(contact.full_name or ('Họ và tên' if document.language == 'vi' else 'Full name')) + '</h1>'
    if contact.headline:
        header += '<p class="designed-headline">' + escape(contact.headline) + '</p>'
    header += '<div class="designed-contacts">' + ''.join(contacts) + '</div></div></header>'
    main = '<main class="designed-main">' + ''.join(section(key) for key in design.main_sections) + '</main>'
    side = '<aside class="designed-sidebar">' + ''.join(section(key) for key in design.sidebar_sections) + '</aside>' if design.layout == 'two-column' else ''
    content = (side + main if design.sidebar_position == 'left' else main + side)
    columns = (f'{design.sidebar_width}% minmax(0,1fr)' if design.sidebar_position == 'left' else f'minmax(0,1fr) {design.sidebar_width}%') if side else 'minmax(0,1fr)'
    heading_css = {'line':'border-bottom:1.5px solid var(--accent);padding-bottom:5pt',
                   'filled':'background:var(--accent);color:#fff;padding:5pt 7pt',
                   'plain':'border:0;padding-bottom:3pt'}[design.heading_style]
    css = f'''@font-face{{font-family:DesignedFont;src:url(data:font/ttf;base64,{font_data(options.font)})}}
@page{{size:A4;margin:{design.margin_mm}mm}}*{{box-sizing:border-box}}
:root{{--accent:{options.color}}}html,body{{margin:0;padding:0;background:white}}
body{{font-family:DesignedFont,{'serif' if options.font=='serif' else 'sans-serif'};font-size:{options.font_size}pt;line-height:{options.line_height};color:#202630;overflow-wrap:anywhere;-webkit-print-color-adjust:exact;print-color-adjust:exact}}
h1,h2,h3,p{{margin:0}}h1{{font-size:24pt;line-height:1.3;color:var(--accent)}}
.designed-header{{display:flex;gap:16pt;align-items:center;{'justify-content:center;text-align:center;flex-direction:column' if design.header_align=='center' else ''};padding-bottom:16pt;margin-bottom:14pt;border-bottom:2px solid var(--accent);break-inside:avoid}}
.designed-header>div{{min-width:0}}.designed-headline{{font-size:12pt;margin:5pt 0}}
.designed-contacts{{display:flex;flex-wrap:wrap;gap:3pt 12pt;margin-top:7pt;{'justify-content:center' if design.header_align=='center' else ''}}}
.designed-photo{{width:72pt;height:72pt;object-fit:cover;flex-shrink:0;border-radius:{'50%' if design.photo_shape=='circle' else '5pt'}}}
.designed-columns{{display:grid;grid-template-columns:{columns};gap:20pt;align-items:start}}
.designed-main,.designed-sidebar{{min-width:0}}.designed-sidebar{{background:#f5f6f8;padding:12pt}}
.designed-section{{margin-bottom:{design.section_gap}pt}}.designed-section h2{{font-size:11.5pt;line-height:1.4;margin-bottom:8pt;color:var(--accent);break-after:avoid;{heading_css}}}
.designed-entry{{margin:0 0 10pt}}.entry-top{{display:flex;gap:8pt;align-items:baseline;justify-content:space-between;break-after:avoid}}
h3{{font-size:10.5pt;line-height:1.4;font-weight:700}}.period{{font-size:9pt;max-width:38%;flex-shrink:0}}
.entry-subtitle{{font-weight:600;margin:3pt 0;break-after:avoid}}ul{{padding-left:14pt;margin:4pt 0 0}}li{{margin:2pt 0;break-inside:avoid}}'''
    return '<!doctype html><html lang="' + document.language + '"><head><meta charset="utf-8"><meta http-equiv="Content-Security-Policy" content="default-src \'none\'; style-src \'unsafe-inline\'; img-src data:; font-src data:; base-uri \'none\'"><style>' + css + '</style></head><body>' + header + '<div class="designed-columns">' + content + '</div></body></html>'


def thumbnail(meta):
    """Small SVG wireframe reflects the actual saved layout, without sample PII."""
    design = TemplateDesign.model_validate(meta['design'])
    color = meta['color']
    parts = ['<svg xmlns="http://www.w3.org/2000/svg" width="420" height="594" viewBox="0 0 420 594"><rect width="420" height="594" fill="white"/>']
    center = design.header_align == 'center'
    x = 210 if center else 30
    if design.show_photo:
        parts.append(f'<rect x="{184 if center else 30}" y="22" width="52" height="52" rx="{26 if design.photo_shape=="circle" else 3}" fill="#e4e7ed"/>')
    y = 96 if center and design.show_photo else 42
    tx = x if center else (96 if design.show_photo else x)
    parts.append(f'<text x="{tx}" y="{y}" text-anchor="{"middle" if center else "start"}" font-family="Arial,sans-serif" font-size="19" font-weight="bold" fill="{color}">{escape(meta["name"])}</text>')
    top = max(114, y + 45)
    parts.append(f'<path d="M30 {top-20}H390" stroke="{color}" stroke-width="2"/>')
    side_width = 360 * design.sidebar_width / 100
    def blocks(keys, left, width):
        nonlocal parts
        by = top
        for key in keys:
            if by > 550:
                break
            if design.heading_style == 'filled':
                parts.append(f'<rect x="{left}" y="{by}" width="{width}" height="19" fill="{color}"/>')
            parts.append(f'<text x="{left+4}" y="{by+13}" font-family="Arial,sans-serif" font-size="10" fill="{"white" if design.heading_style=="filled" else color}">{LABELS[key]}</text>')
            if design.heading_style == 'line':
                parts.append(f'<path d="M{left} {by+19}h{width}" stroke="{color}"/>')
            for i, ratio in enumerate([.94,.85,.7]):
                parts.append(f'<rect x="{left+4}" y="{by+29+i*8}" width="{max(20,(width-8)*ratio)}" height="3" rx="1" fill="#d8dce4"/>')
            by += 67
    if design.layout == 'two-column':
        sx = 30 if design.sidebar_position == 'left' else 390-side_width
        mx = 30+side_width+16 if design.sidebar_position == 'left' else 30
        parts.append(f'<rect x="{sx-5}" y="{top-5}" width="{side_width+10}" height="{570-top}" fill="#f5f6f8"/>')
        blocks(design.sidebar_sections,sx,side_width)
        blocks(design.main_sections,mx,360-side_width-16)
    else:
        blocks(design.main_sections,30,360)
    return ''.join(parts) + '</svg>'
