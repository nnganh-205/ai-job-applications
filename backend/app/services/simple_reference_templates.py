"""Four simple layouts reconstructed from the user's supplied TopCV PDFs."""
import base64
from functools import lru_cache
from html import escape
from backend.app.core.config import PROJECT_ROOT

REFERENCES = {
    'simple': ('Đơn giản 01 · Avatar tròn', '45629', '#b54848', 'one-column'),
    'clean': ('Đơn giản 02 · Ba cột thông tin', '45601', '#c52435', 'three-column'),
    'minimal': ('Đơn giản 03 · Tiêu đề nền xám', '45546', '#263e52', 'one-column'),
    'compact': ('Đơn giản 04 · Đen trắng', '45138', '#111111', 'one-column'),
}

AVATAR = '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 200 200"><rect width="200" height="200" fill="#f4f5f5"/><circle cx="100" cy="65" r="41" fill="#a7aeb3"/><path d="M0 200c3-56 43-88 100-88s97 32 100 88" fill="#a7aeb3"/></svg>'''
ICON_PATHS = {
 'email':'M2 4h20v16H2z M2 4l10 9L22 4',
 'phone':'M6 2l4 5-3 3c2 4 3 5 7 7l3-3 5 4c-2 8-10 2-14-2S-2 4 6 2z',
 'location':'M12 22S4 13 4 8a8 8 0 1 1 16 0c0 5-8 14-8 14z M12 5a3 3 0 1 0 0 6 3 3 0 0 0 0-6',
 'date_of_birth':'M3 5h18v17H3z M3 10h18 M7 2v6 M17 2v6',
 'gender':'M4 22c0-10 16-10 16 0z M12 2a5 5 0 1 0 0 10 5 5 0 0 0 0-10',
 'website':'M10 14l4-4 M8 16l-2 2a4 4 0 0 1-6-6l5-5a4 4 0 0 1 6 0 M16 8l2-2a4 4 0 0 1 6 6l-5 5a4 4 0 0 1-6 0',
}


@lru_cache(maxsize=4)
def reference_font(weight):
    filename = {400:'Regular',500:'Medium',600:'SemiBold',700:'Bold'}[weight]
    return base64.b64encode((PROJECT_ROOT/'frontend/public/fonts'/('BeVietnamPro-'+filename+'.ttf')).read_bytes()).decode()


def _icon(key):
    return '<svg class="contact-icon" viewBox="0 0 24 24" aria-hidden="true"><path d="'+ICON_PATHS[key]+'"/></svg>'


def _contacts(contact, variant):
    website=' · '.join(dict.fromkeys(v for v in [contact.website,contact.linkedin,contact.github,contact.portfolio_url] if v))
    address=', '.join(dict.fromkeys(v for v in [contact.location,contact.city,contact.state_or_province,contact.country] if v))
    values=dict(date_of_birth=contact.date_of_birth,gender=contact.gender,phone=contact.phone,email=contact.email,location=address,website=website)
    if variant=='compact':
        labels=dict(phone='Số điện thoại',email='Email',location='Địa chỉ',date_of_birth='Ngày sinh',gender='Giới tính',website='Website')
        return ''.join('<p><strong>'+labels[k]+':</strong> '+escape(v)+'</p>' for k in ('phone','email','location','date_of_birth','gender','website') if (v:=values[k]))
    order = ('email','phone','website','location','date_of_birth','gender') if variant=='clean' else ('date_of_birth','gender','phone','email','location','website') if variant=='simple' else ('date_of_birth','phone','email','gender','location','website')
    return ''.join('<div class="contact-item">'+_icon(k)+'<span>'+escape(values[k] or '')+'</span></div>' for k in order if values[k] or variant in {'simple','minimal'})


def _bullet_list(entry):
    return '<ul>'+''.join('<li>'+escape(('GPA: ' if any(ref.endswith('/gpa') for ref in b.source_refs) and not b.text.lower().startswith('gpa') else '')+b.text)+'</li>' for b in entry.bullets)+'</ul>' if entry.bullets else ''


def _section(section, variant):
    if not section or not section.entries:return ''
    kind=section.kind
    headings={'education':'Học vấn','experience':'Kinh nghiệm làm việc','skills':'Kỹ năng','project':'Dự án','involvement':'Hoạt động','certifications':'Chứng chỉ','awards':'Danh hiệu và giải thưởng','references':'Người giới thiệu'}
    heading=headings.get(kind,section.heading) if variant=='simple' else section.heading
    if section.heading in {'Kinh nghiệm','Experience'}:heading='Kinh nghiệm làm việc' if section.heading=='Kinh nghiệm' else 'Experience'
    body='<section class="reference-section section-'+kind+'"><h2>'+escape(heading)+'</h2><div class="section-content">'
    for entry in section.entries:
        title,sub,period=map(lambda s:escape(s or ''),(entry.title,entry.subtitle,entry.period))
        if kind=='skills':
            body+='<p class="skills-line"><strong>'+title+':</strong> '+', '.join(escape(b.text) for b in entry.bullets)+'</p>'
        elif kind=='references':
            body+='<article class="reference-person"><strong>'+title+'</strong>'+(('<p>'+sub+'</p>') if sub else '')
            for b in entry.bullets:
                field=b.source_refs[0].split('/')[3] if b.source_refs and len(b.source_refs[0].split('/'))>3 else ''
                label={'email':'Email: ','phone':'SĐT: ','relationship':'Quan hệ: '}.get(field,'')
                body+='<p>'+label+escape(b.text)+'</p>'
            body+='</article>'
        elif kind in {'certifications','awards'}:
            body+='<article class="reference-entry entry supplementary"><div class="entry-aside period">'+period+'</div><div class="entry-main"><h3>'+title+'</h3>'+(('<p>'+sub+'</p>') if sub else '')+_bullet_list(entry)+'</div></article>'
        else:
            if variant=='simple':
                left=(sub if kind=='education' else title)
                right=(title if kind=='education' else sub)
                aside='<h3>'+left+'</h3><p class="period">'+period+'</p>'
                main='<h3>'+right+'</h3>'+_bullet_list(entry)
            elif variant=='clean' and kind=='education':
                aside=''
                main='<h3>'+title+'</h3>'+(('<p>'+sub+'</p>') if sub else '')+'<p class="period">'+period+'</p>'+_bullet_list(entry)
            elif variant=='clean':
                aside='<p class="period">'+period+'</p><h3>'+sub+'</h3>'
                main='<h3>'+title+'</h3>'+_bullet_list(entry)
            elif variant=='minimal':
                aside='<p class="period">'+period+'</p>'
                main='<h3>'+(title if kind=='education' else sub or title)+((' <span class="entry-divider">|</span> '+(sub if kind=='education' else title)) if sub else '')+'</h3>'+_bullet_list(entry)
            else:
                aside='<p class="period">'+period+'</p>'
                main='<h3>'+(title if kind=='education' else sub or title)+'</h3>'+(('<p class="entry-subtitle">'+(sub if kind=='education' else title)+'</p>') if sub else '')+_bullet_list(entry)
            body+='<article class="reference-entry entry"><div class="entry-aside">'+aside+'</div><div class="entry-main">'+main+'</div></article>'
    return body+'</div></section>'


BASE = '''
@page{size:A4;margin:12pt 15pt 18pt}
*{box-sizing:border-box}html,body{margin:0;padding:0;background:white;color:#111}
body{font-family:ReferenceFont,Arial,sans-serif;font-size:9.5pt;line-height:1.48;overflow-wrap:anywhere;-webkit-print-color-adjust:exact;print-color-adjust:exact}
h1,h2,h3,p{margin:0}h1{font-size:19pt;line-height:1.25;font-weight:700;color:var(--accent)}h2{font-size:12pt;line-height:1.3;font-weight:700;break-after:avoid}h3{font-size:9.5pt;font-weight:700;break-after:avoid}ul{padding-left:13pt;margin:4pt 0 0}li{margin:2pt 0;break-inside:avoid}.period{white-space:normal}
.reference-header{display:grid;grid-template-columns:145pt minmax(0,1fr);gap:8pt;min-height:145pt;margin-bottom:27pt;break-inside:avoid}
.reference-avatar{display:block;width:145pt;height:145pt;object-fit:cover;border-radius:50%;background:#f4f5f5;border:1px solid #e5e5e5}
.reference-header-main{padding-top:32pt}.name-line{display:flex;align-items:baseline;justify-content:space-between;gap:10pt;border-bottom:2px solid var(--accent);padding:8pt 0 5pt}.headline{font-size:11pt;font-weight:400;line-height:1.5}.reference-contacts{display:grid;grid-template-columns:1fr 1fr;gap:4pt 12pt;padding-top:5pt;font-size:9pt}.contact-item{display:flex;align-items:flex-start;gap:8pt;min-width:0}.contact-icon{width:11pt;height:11pt;flex-shrink:0;fill:none;stroke:currentColor;stroke-width:1.8;stroke-linecap:round;stroke-linejoin:round;margin-top:1pt}
.reference-section{margin:22pt 0 0}.reference-section h2{color:var(--accent);padding:0 3pt 3pt;border-bottom:1px solid #bbb;margin-bottom:5pt}.reference-summary p{padding:7pt 3pt 0}.reference-entry{display:grid;grid-template-columns:minmax(0,32%) minmax(0,1fr);gap:14pt;margin-top:6pt;margin-bottom:18pt}.entry-aside h3{color:var(--accent)}.entry-aside .period{margin-top:3pt}.reference-person{margin:8pt 3pt}.reference-person p{margin-top:2pt}.skills-line{margin:5pt 3pt;line-height:1.5}.supplementary{grid-template-columns:95pt minmax(0,1fr)}
'''
BASE += '@media screen{body{width:210mm;min-height:297mm;padding:12pt 15pt 18pt}}'
STYLES = {
'simple': '''@page{margin:12pt 8pt 18pt}@media screen{body{padding:12pt 8pt 18pt}}.reference-section{margin-left:10pt;margin-right:10pt}.reference-avatar{border:2px solid var(--accent);padding:2pt}.reference-header{margin-left:0;grid-template-columns:145pt minmax(0,1fr);gap:8pt}.headline{color:var(--accent)}.reference-section{margin-top:22pt}.section-skills,.section-references,.section-certifications,.section-awards{break-inside:auto}''',
'clean': '''.reference-header{grid-template-columns:180pt minmax(0,1fr);gap:14pt;min-height:197pt;margin-bottom:0}.reference-avatar{width:154pt;height:154pt;border-radius:0;margin:0 auto}.reference-header-main{padding-top:15pt}.name-line{display:block;border:0;padding:0}.headline{margin-top:17pt;border-bottom:1.5px solid #111;padding-bottom:7pt}.header-summary{padding-top:7pt;line-height:1.48}.reference-trio{display:grid;align-items:start;grid-template-columns:1fr 1fr 1fr;gap:14pt;margin-top:36pt;min-height:350pt}.reference-trio .reference-section{margin:0}.reference-section h2{text-transform:uppercase;color:#111;border-top:1.5px solid var(--accent);border-bottom:1.5px solid var(--accent);padding:4pt 3pt;margin-bottom:10pt;font-size:11.5pt}.personal-section .reference-contacts{display:flex;flex-direction:column;gap:6pt;font-size:9pt;padding-top:0}.personal-section .contact-icon{color:var(--accent)}.reference-trio .reference-entry{display:block;margin-top:0;border:0;padding:0}.reference-trio .reference-entry:before{display:none}.reference-trio .entry-aside{display:none}.reference-trio .entry-main>p{margin-top:5pt}.reference-entry{grid-template-columns:minmax(0,34%) minmax(0,1fr);gap:15pt;margin-left:7pt;padding-left:13pt;border-left:1px solid #999;position:relative}.reference-entry:before{content:"";position:absolute;left:-4pt;top:3pt;width:7pt;height:7pt;background:var(--accent);border-radius:50%}.entry-aside h3{color:#111;margin-top:5pt}.entry-main h3{margin-bottom:3pt}.supplementary{border:0;padding-left:0}.supplementary:before{display:none}.reference-trio .skills-line{margin:0 3pt 10pt}.reference-trio .skills-line strong{display:inline}''',
'minimal': '''body{color:#263e52}.reference-header{grid-template-columns:112pt minmax(0,1fr);gap:24pt;margin:0 13pt 20pt;min-height:128pt}.reference-avatar{width:110pt;height:110pt}.reference-header-main{padding-top:0}.name-line{display:block;padding:0;border:0}h1{font-size:24pt;font-weight:600}.headline{font-weight:500;font-size:14pt;display:table;border-bottom:1px solid #111;padding-bottom:3pt;margin-top:3pt}.reference-contacts{grid-template-columns:repeat(3,minmax(0,1fr));font-size:9pt;gap:8pt 12pt;margin-top:5pt}.reference-section{margin-top:25pt}.reference-section h2{text-transform:uppercase;text-align:center;background:#f4f4f4;border:0;font-weight:600;font-size:14pt;letter-spacing:.04em;padding:6pt 12pt;margin:0 -15pt 8pt}.reference-summary p{padding:1pt 3pt 0}.reference-entry{grid-template-columns:120pt minmax(0,1fr);gap:15pt;margin:8pt 14pt 23pt}.entry-aside .period{margin:0}.entry-divider{font-weight:400;margin:0 4pt}.reference-person{margin-left:14pt}''',
'compact': '''body{font-family:Arial,ReferenceFont,sans-serif;font-size:9.5pt;line-height:1.38}.reference-header{grid-template-columns:90pt minmax(0,1fr);gap:18pt;min-height:135pt;margin:6pt 3pt 18pt}.reference-avatar{width:90pt;height:120pt;border-radius:0}.reference-header-main{padding:0}.name-line{display:block;border:0;padding:0}h1{font-size:18pt;color:#000}.headline{font-size:11pt;margin-top:3pt}.reference-contacts{display:block;font-size:9.5pt}.reference-contacts p{margin:3pt 0}.reference-section{margin-top:18pt}.reference-section h2{text-transform:uppercase;color:#111;font-size:11pt;border-color:#777;padding:0 3pt 4pt;margin-bottom:6pt}.reference-summary p{padding-top:6pt}.reference-entry{grid-template-columns:95pt minmax(0,1fr);gap:13pt;margin:7pt 3pt 0;padding-bottom:9pt;border-bottom:1px solid #e6e6e6}.reference-entry:last-child{border-bottom:0}.entry-aside .period{margin:0}.entry-subtitle{margin-top:2pt}ul{margin-top:3pt}li{margin:1pt 0}.reference-person{margin-left:3pt}''',
}


def render_reference(document, template, options):
    info = REFERENCES[template]
    sections={section.kind:section for section in document.sections}
    avatar='data:image/svg+xml;base64,'+base64.b64encode(AVATAR.encode()).decode()
    if options.photo_asset_id:
        from backend.app.services.assets import photo_data
        avatar=photo_data(options.photo_asset_id)
    header='<header class="reference-header"><img class="reference-avatar" alt="Ảnh đại diện" src="'+avatar+'"><div class="reference-header-main"><div class="name-line"><h1>'+escape(document.contact.full_name or 'Họ và tên')+'</h1><p class="headline">'+escape(document.contact.headline or '')+'</p></div>'
    summary='<section class="reference-section reference-summary"><h2>'+('Mục tiêu nghề nghiệp' if document.language=='vi' else 'Career objective')+'</h2><p>'+escape(document.summary.text)+'</p></section>' if document.summary else ''
    if template=='clean':
        header+=('<p class="header-summary">'+escape(document.summary.text)+'</p>') if document.summary else ''
        header+='</div></header>'
        body=header+'<div class="reference-trio"><section class="reference-section personal-section"><h2>'+('Thông tin cá nhân' if document.language=='vi' else 'Personal information')+'</h2><div class="reference-contacts">'+_contacts(document.contact,template)+'</div></section>'+_section(sections.get('education'),template)+_section(sections.get('skills'),template)+'</div>'
        order=['experience','project','involvement','certifications','awards','references']
    else:
        header+='<div class="reference-contacts">'+_contacts(document.contact,template)+'</div></div></header>'
        body=header+summary
        order={'simple':['education','experience','skills','references','certifications','awards','project','involvement'], 'minimal':['education','experience','skills','certifications','project','awards','references','involvement'], 'compact':['education','experience','certifications','awards','skills','references','project','involvement']}[template]
    body+=''.join(_section(sections.get(kind),template) for kind in order)
    accent=options.color if options.color!='#000000' else info[2]
    fonts=''.join('@font-face{font-family:ReferenceFont;font-style:normal;font-weight:'+str(w)+';src:url(data:font/ttf;base64,'+reference_font(w)+') format("truetype")}' for w in (400,500,600,700))
    css=fonts+BASE+STYLES[template]+f':root{{--accent:{accent}}}body{{font-size:{options.font_size}pt;line-height:{options.line_height}}}'
    return '<!doctype html><html lang="'+document.language+'"><head><meta charset="utf-8"><meta http-equiv="Content-Security-Policy" content="default-src \'none\'; style-src \'unsafe-inline\'; img-src data:; font-src data:; base-uri \'none\'"><style>'+css+'</style></head><body class="reference-'+template+'">'+body+'</body></html>'
