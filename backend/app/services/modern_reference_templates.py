"""Modern layouts reconstructed from the four user-supplied PDF references."""
import base64
from html import escape
from backend.app.services.simple_reference_templates import AVATAR, reference_font, _icon

REFERENCES={
 'modern':('Hiện đại 01 · Dải xanh','51131','#38a16b','one-column'),
 'sidebar':('Hiện đại 02 · Khối xanh đậm','51106','#203040','two-column'),
 'metro':('Hiện đại 03 · Cột xanh nhạt','51052','#0088bb','two-column'),
 'split':('Hiện đại 04 · Hồng nhạt','51040','#e96b9b','one-column'),
}


def _section(section,template):
    if not section or not section.entries:return ''
    kind=section.kind
    heading='Kinh nghiệm làm việc' if section.heading=='Kinh nghiệm' else section.heading
    out='<section class="modern-section section-'+kind+'"><h2>'+escape(heading)+'</h2><div class="section-content">'
    for entry in section.entries:
        title,sub,period=map(lambda value:escape(value or ''),(entry.title,entry.subtitle,entry.period))
        if kind=='skills':
            out+='<p class="skills-line"><strong>'+title+':</strong> '+', '.join(escape(b.text) for b in entry.bullets)+'</p>';continue
        if kind=='references':
            out+='<article class="modern-person"><h3>'+title+'</h3>'+('<p>'+sub+'</p>' if sub else '')
            for bullet in entry.bullets:
                field=bullet.source_refs[0].split('/')[3] if bullet.source_refs and len(bullet.source_refs[0].split('/'))>3 else ''
                out+='<p>'+{'email':'Email: ','phone':'SĐT: ','relationship':'Quan hệ: '}.get(field,'')+escape(bullet.text)+'</p>'
            out+='</article>';continue
        if kind in {'certifications','awards'}:
            out+='<article class="modern-entry supplementary"><div class="entry-aside period">'+period+'</div><div class="entry-main"><h3>'+title+'</h3>'+('<p>'+sub+'</p>' if sub else '')
        elif template=='modern':
            left=title if kind=='education' else sub or title
            right=sub if kind=='education' else title
            out+='<article class="modern-entry"><div class="entry-aside"><h3>'+left+'</h3><p class="period">'+period+'</p></div><div class="entry-main"><p>'+right+'</p>'
        elif template=='sidebar':
            top=title if kind=='education' else sub or title
            second=sub if kind=='education' else title
            out+='<article class="modern-entry"><div class="entry-main"><h3>'+top+'</h3><p class="entry-subtitle">'+second+(' <span class="period">( '+period+' )</span>' if period else '')+'</p>'
        elif template=='metro':
            out+='<article class="modern-entry"><div class="entry-main"><p class="period">'+period+'</p><p class="entry-role">'+(sub if kind=='education' else title)+'</p><h3>'+(title if kind=='education' else sub)+'</h3>'
        else:
            left=period
            lefttitle='' if kind=='education' else sub
            main=title
            out+='<article class="modern-entry"><div class="entry-aside"><p class="period">'+left+'</p><h3>'+lefttitle+'</h3></div><div class="entry-main"><h3>'+main+'</h3>'+('<p>'+sub+'</p>' if kind=='education' and sub else '')
        if entry.bullets:
            out+='<ul>'
            for bullet in entry.bullets:
                value=bullet.text
                if kind=='education' and any(r.endswith('/gpa') for r in bullet.source_refs) and not value.lower().startswith('gpa'):value='GPA: '+value
                out+='<li>'+escape(value)+'</li>'
            out+='</ul>'
        out+='</div></article>'
    return out+'</div></section>'


def _contacts(contact,template):
    address=', '.join(dict.fromkeys(v for v in [contact.location,contact.city,contact.state_or_province,contact.country] if v))
    website=' · '.join(dict.fromkeys(v for v in [contact.website,contact.linkedin,contact.github,contact.portfolio_url] if v))
    values=dict(phone=contact.phone,email=contact.email,location=address,website=website,date_of_birth=contact.date_of_birth,gender=contact.gender)
    order=('location','email','phone','website','date_of_birth','gender') if template=='modern' else ('phone','email','location','website','date_of_birth','gender') if template=='metro' else ('phone','email','website','location','date_of_birth','gender')
    labels=dict(phone='Số điện thoại',email='Email',location='Địa chỉ',website='Website',date_of_birth='Ngày sinh',gender='Giới tính')
    return '<div class="modern-contacts">'+''.join('<div class="contact-item">'+('' if template=='modern' else _icon(key))+'<div>'+('<strong>'+labels[key]+'</strong>' if template=='metro' else '')+'<p>'+escape(values[key] or '')+'</p></div></div>' for key in order if values[key] or template=='metro' or (key=='website' and template in {'sidebar','split'}))+'</div>'


CSS='''
@page{size:A4;margin:12pt 15pt 18pt}*{box-sizing:border-box}html,body{margin:0;padding:0;background:white}body{font-family:ModernFont,Arial,sans-serif;font-size:9.5pt;line-height:1.48;color:#111;overflow-wrap:anywhere;-webkit-print-color-adjust:exact;print-color-adjust:exact}h1,h2,h3,p{margin:0}h1{font-size:20pt;font-weight:700;line-height:1.3;color:var(--accent)}h2{font-size:12pt;line-height:1.4;font-weight:700;break-after:avoid}h3{font-size:9.5pt;font-weight:700;line-height:1.5;break-after:avoid}ul{padding-left:13pt;margin:5pt 0 0}li{margin:2pt 0;break-inside:avoid}.modern-avatar{display:block;width:150pt;height:150pt;object-fit:cover;background:#f4f5f5;border:1px solid #e5e5e5}.modern-headline{font-size:11.5pt;margin-top:6pt}.modern-header{break-inside:avoid}.modern-section{margin:18pt 0 0}.modern-section h2{color:var(--accent);margin-bottom:10pt}.modern-entry{margin:0 0 15pt;display:grid;grid-template-columns:minmax(0,32%) minmax(0,1fr);gap:14pt}.modern-entry:last-child{margin-bottom:0}.entry-aside h3{font-weight:400}.entry-subtitle{margin-top:4pt}.skills-line{margin:6pt 0;line-height:1.5}.modern-person{margin-top:7pt}.modern-person p{margin-top:3pt}.contact-item{display:flex;gap:9pt;align-items:flex-start;min-width:0}.contact-icon{flex-shrink:0;width:10pt;height:11pt;fill:none;stroke:currentColor;stroke-width:1.8;stroke-linejoin:round;stroke-linecap:round;margin-top:2pt}.modern-contacts{display:flex;flex-direction:column;gap:7pt;font-size:9pt}.modern-columns{display:grid;grid-template-columns:minmax(0,65%) minmax(0,1fr);gap:15pt;align-items:start}.modern-main,.modern-sidebar{min-width:0}.modern-summary p{margin-top:7pt}.supplementary{grid-template-columns:70pt minmax(0,1fr)}
'''
CSS += '@media screen{body{width:210mm;min-height:297mm;padding:12pt 15pt 18pt}}'
STYLES={
'modern':'''@page{margin:3pt 0 18pt}@media screen{body{padding:3pt 0 18pt}}body{font-family:Arial,ModernFont,sans-serif}.modern-header{background:#38a16b;position:relative;margin-bottom:61pt}.modern-header:after{content:"";position:absolute;top:calc(100% - 1px);left:0;width:100%;height:36pt;background:#38a16b;clip-path:polygon(0 0,100% 0,100% 20%,0 100%)}.modern-header-top{display:grid;grid-template-columns:33.333% minmax(0,1fr)}.modern-avatar{border:0;border-radius:50%;width:90pt;height:90pt;margin:8pt auto}.modern-name{padding:16pt 14pt;border-left:1px solid #ffffff40}.modern-name h1{color:#111;font-size:18pt;font-weight:400}.modern-headline{color:white;margin-top:16pt}.modern-header .modern-contacts{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:7pt;border-top:1px solid #ffffff40;border-bottom:1px solid #ffffff40;color:white;padding:8pt 11pt}.modern-content{padding:0 18pt}.modern-section{margin-top:21pt}.modern-section h2{color:#111;font-weight:400;font-size:11.5pt}.modern-entry{grid-template-columns:minmax(0,32%) minmax(0,1fr);gap:13pt}.modern-entry h3{font-weight:400}.entry-main>p:first-child{margin-bottom:6pt}.modern-summary{margin-top:0}''',
'sidebar':''' .modern-header{display:grid;grid-template-columns:157pt minmax(0,1fr);gap:28pt;min-height:192pt;margin:5pt 0 15pt}.modern-avatar{width:157pt;height:181pt;border-radius:0}.modern-name-line{border-left:3px solid #203040;padding:3pt 0 4pt 10pt}.modern-header h1{color:#263e52;font-size:20pt}.modern-header .modern-headline{color:#111;font-size:11pt}.modern-header .header-summary{background:#f1f1f1;border-radius:3pt;padding:9pt;margin-top:10pt}.modern-section h2{text-transform:uppercase;color:#263e52;font-size:12pt;padding-bottom:10pt;position:relative}.modern-section h2:after{content:"";position:absolute;bottom:4pt;left:0;width:125pt;height:1.5px;background:#111}.modern-main>.section-education{background:#203040;color:white;padding:13pt 14pt;margin-top:0}.modern-main>.section-education h2{color:white}.modern-main>.section-education h2:after{background:white}.modern-entry{display:block}.entry-subtitle{font-weight:700}.section-education .entry-subtitle{font-weight:400}.modern-main>.section-experience{margin-top:20pt}.modern-sidebar .modern-section:first-child{margin-top:8pt}.modern-sidebar .modern-section h2:after{width:125pt;max-width:100%}.modern-sidebar .supplementary{display:block}.supplementary h3{font-weight:400}.modern-sidebar .contact-item{margin-bottom:2pt}''',
'metro':''' .modern-columns{grid-template-columns:minmax(0,55%) minmax(0,1fr);gap:18pt}.modern-left-intro .modern-avatar{width:135pt;height:135pt;border-radius:50%;margin:9pt 0 23pt}.modern-left-intro h1{text-transform:uppercase;font-weight:400;font-size:18pt;color:#0088bb}.modern-headline{color:#0088bb;font-size:11pt;font-weight:600}.modern-summary{position:relative;padding-top:24pt;margin-top:18pt}.modern-summary:before{content:"“";position:absolute;left:-4pt;top:-5pt;font-size:45pt;font-weight:700;color:#bbb;line-height:1}.modern-summary p{margin:0}.modern-section h2{color:#0088bb;font-size:12pt}.modern-entry{display:block}.entry-role{margin:4pt 0}.modern-entry h3{color:#555}.modern-sidebar{background:#f3f9fc;min-height:780pt;padding:0 10pt 16pt 43pt;margin-right:-8pt}.modern-contacts{position:relative;gap:9pt;margin:0 0 30pt;padding:7pt 0 4pt;min-height:190pt}.modern-contacts:before{content:"";position:absolute;left:-44pt;top:0;bottom:0;width:30pt;border-radius:18pt;background:#0788b8}.modern-contacts .contact-item{position:relative;display:block;min-height:24pt}.modern-contacts .contact-icon{position:absolute;left:-37pt;top:0;color:white;width:15pt;height:15pt}.modern-contacts strong{color:#555;font-size:9pt}.modern-contacts p{margin-top:3pt}.modern-sidebar .modern-section{position:relative;margin-top:24pt}.modern-sidebar .modern-section h2:before{content:"";position:absolute;left:-44pt;top:-3pt;width:30pt;height:30pt;background:#0788b8;border-radius:50%}.modern-sidebar .modern-section h2{margin-bottom:5pt}.modern-sidebar .modern-entry{display:block}.modern-sidebar .entry-subtitle,.modern-sidebar .entry-role{font-weight:700}.modern-sidebar .skills-line{font-weight:600;color:#555}.modern-sidebar .supplementary h3{font-weight:400}.modern-sidebar .supplementary .period{margin-bottom:5pt}''',
'split':'''@page{margin:8pt}@media screen{body{padding:8pt}} .modern-top-contacts{background:#faeaf2;padding:10pt 9pt;margin-bottom:15pt}.modern-top-contacts .modern-contacts{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:8pt}.modern-top-contacts .contact-icon{color:#ff896a;width:9pt;height:10pt}.modern-top-contacts .contact-item{font-size:9pt}.modern-header{display:grid;grid-template-columns:2fr 1fr;background:#faeaf2;gap:0;margin-bottom:15pt}.modern-avatar{border:0;width:100%;height:193pt;object-fit:cover}.modern-header-text{padding:15pt}.modern-header h1{font-size:19pt;color:#e76a99}.modern-headline{display:flex;align-items:center;gap:15pt;font-size:11pt;margin-top:20pt}.modern-headline:after{content:"";height:1px;width:105pt;background:#ff896a}.header-summary{margin-top:26pt}.modern-section{background:#faeaf2;padding:7pt 10pt 10pt;border-radius:5pt;margin-top:15pt}.modern-section h2{color:#e76a99;font-size:12pt;padding-bottom:5pt;border-bottom:1px solid #ff896a;margin-bottom:10pt}.modern-entry{position:relative;grid-template-columns:minmax(0,32%) minmax(0,1fr);gap:17pt;border-left:1px solid #aaa;margin:0 0 14pt 5pt;padding-left:16pt}.modern-entry:before{content:"";position:absolute;left:-5pt;top:2pt;width:9pt;height:9pt;background:#ff896a;border:1px solid #ccc;border-radius:50%}.modern-entry:last-child{margin-bottom:0}.entry-aside h3{font-weight:700;margin-top:5pt}.modern-bottom{display:grid;grid-template-columns:1fr 1fr;gap:15pt;align-items:start}.modern-bottom .modern-section{height:auto}.supplementary{display:block}.supplementary:before{display:none}.supplementary .period{margin-bottom:5pt}''',
}


def render_modern(document,template,options):
    sections={s.kind:s for s in document.sections}
    avatar='data:image/svg+xml;base64,'+base64.b64encode(AVATAR.encode()).decode()
    if options.photo_asset_id:
        from backend.app.services.assets import photo_data
        avatar=photo_data(options.photo_asset_id)
    image='<img class="modern-avatar" alt="Ảnh đại diện" src="'+avatar+'">'
    name='<h1>'+escape(document.contact.full_name or 'Họ và tên')+'</h1><p class="modern-headline">'+escape(document.contact.headline or '')+'</p>'
    summary='<section class="modern-section modern-summary"><h2>'+('Mục tiêu nghề nghiệp' if document.language=='vi' else 'Career objective')+'</h2><p>'+escape(document.summary.text)+'</p></section>' if document.summary else ''
    plain_summary='<p class="header-summary">'+escape(document.summary.text)+'</p>' if document.summary else ''
    if template=='modern':
        body='<header class="modern-header"><div class="modern-header-top">'+image+'<div class="modern-name">'+name+'</div></div>'+_contacts(document.contact,template)+'</header><main class="modern-content">'+summary+''.join(_section(sections.get(k),template) for k in ['experience','education','certifications','awards','skills','references','project','involvement'])+'</main>'
    elif template=='sidebar':
        header='<header class="modern-header">'+image+'<div><div class="modern-name-line">'+name+'</div>'+plain_summary+'</div></header>'
        main=''.join(_section(sections.get(k),template) for k in ['education','experience','project','involvement'])
        side='<section class="modern-section personal-section"><h2>Thông tin cá nhân</h2>'+_contacts(document.contact,template)+'</section>'+''.join(_section(sections.get(k),template) for k in ['skills','certifications','references','awards'])
        body=header+'<div class="modern-columns"><main class="modern-main">'+main+'</main><aside class="modern-sidebar">'+side+'</aside></div>'
    elif template=='metro':
        main='<header class="modern-left-intro">'+image+name+'</header>'+('<section class="modern-section modern-summary"><p>'+escape(document.summary.text)+'</p></section>' if document.summary else '')+''.join(_section(sections.get(k),template) for k in ['experience','project','involvement','references','awards'])
        side=_contacts(document.contact,template)+''.join(_section(sections.get(k),template) for k in ['education','skills','certifications'])
        body='<div class="modern-columns"><main class="modern-main">'+main+'</main><aside class="modern-sidebar">'+side+'</aside></div>'
    else:
        body='<div class="modern-top-contacts">'+_contacts(document.contact,template)+'</div><header class="modern-header"><div class="modern-header-text">'+name+plain_summary+'</div>'+image+'</header><main>'+''.join(_section(sections.get(k),template) for k in ['experience','education','skills','certifications','project','involvement'])+'<div class="modern-bottom">'+_section(sections.get('references'),template)+_section(sections.get('awards'),template)+'</div></main>'
    fonts=''.join('@font-face{font-family:ModernFont;font-weight:'+str(w)+';src:url(data:font/ttf;base64,'+reference_font(w)+')}' for w in (400,500,600,700))
    accent=options.color if options.color!='#000000' else REFERENCES[template][2]
    css=fonts+CSS+STYLES[template]+f':root{{--accent:{accent}}}body{{font-size:{options.font_size}pt;line-height:{options.line_height}}}'
    return '<!doctype html><html lang="'+document.language+'"><head><meta charset="utf-8"><meta http-equiv="Content-Security-Policy" content="default-src \'none\'; style-src \'unsafe-inline\'; img-src data:; font-src data:; base-uri \'none\'"><style>'+css+'</style></head><body class="modern-'+template+'">'+body+'</body></html>'
