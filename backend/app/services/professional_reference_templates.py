"""Professional layouts matched to the four supplied TopCV PDF references."""
import base64
from html import escape
from backend.app.services.simple_reference_templates import AVATAR, reference_font, _icon

REFERENCES = {
 'executive':('Chuyên nghiệp 01 · Tím nhạt','50227','#80445d','two-column'),
 'corporate':('Chuyên nghiệp 02 · Xám đen','50208','#303030','two-column'),
 'consultant':('Chuyên nghiệp 03 · Xanh rêu','50150','#52604f','two-column'),
 'precision':('Chuyên nghiệp 04 · Nâu trầm','50133','#5d4545','two-column'),
}


def _section(section, template, sidebar=False):
    if not section or not section.entries:return ''
    kind=section.kind
    heading='Kinh nghiệm làm việc' if section.heading=='Kinh nghiệm' else section.heading
    result='<section class="professional-section section-'+kind+'"><h2><span>'+escape(heading)+'</span></h2><div class="section-content">'
    for entry in section.entries:
        title,sub,period=map(lambda value:escape(value or ''),(entry.title,entry.subtitle,entry.period))
        if kind=='skills':
            result+='<p class="skills-line"><strong>'+title+':</strong> '+', '.join(escape(b.text) for b in entry.bullets)+'</p>'
            continue
        if kind=='references':
            result+='<article class="professional-person"><h3>'+title+'</h3>'+(('<p>'+sub+'</p>') if sub else '')
            for bullet in entry.bullets:
                field=bullet.source_refs[0].split('/')[3] if bullet.source_refs and len(bullet.source_refs[0].split('/'))>3 else ''
                result+='<p>'+{'email':'Email: ','phone':'SĐT: ','relationship':'Quan hệ: '}.get(field,'')+escape(bullet.text)+'</p>'
            result+='</article>'
            continue
        if kind in {'certifications','awards'}:
            result+='<article class="professional-entry supplementary"><p class="period">'+period+'</p><div><h3>'+title+'</h3>'+(('<p>'+sub+'</p>') if sub else '')
        elif kind=='education':
            if sidebar:
                result+='<article class="professional-entry"><h3>'+sub+'</h3><p class="period">'+period+'</p><p class="institution">'+title+'</p><div>'
            elif template=='consultant':
                result+='<article class="professional-entry"><div class="entry-top"><p>'+sub+'</p><p class="period">'+period+'</p></div><h3>'+title+'</h3><div>'
            else:
                result+='<article class="professional-entry"><div class="entry-top"><h3>'+title+'</h3><p class="period">'+period+'</p></div><p class="entry-subtitle">'+sub+'</p><div>'
        else:
            top=sub if template=='corporate' else title
            second=title if template=='corporate' else sub
            result+='<article class="professional-entry"><div class="entry-top"><h3>'+top+'</h3><p class="period">'+period+'</p></div>'+(('<p class="entry-subtitle">'+second+'</p>') if second else '')+'<div>'
        if entry.bullets:
            result+='<ul>'
            for bullet in entry.bullets:
                text=bullet.text
                if kind=='education' and any(ref.endswith('/gpa') for ref in bullet.source_refs) and not text.lower().startswith('gpa'):
                    text='GPA: '+text
                result+='<li>'+escape(text)+'</li>'
            result+='</ul>'
        result+='</div></article>'
    return result+'</div></section>'


def _contacts(contact, template):
    website=' · '.join(dict.fromkeys(v for v in [contact.website,contact.linkedin,contact.github,contact.portfolio_url] if v))
    address=', '.join(dict.fromkeys(v for v in [contact.location,contact.city,contact.state_or_province,contact.country] if v))
    values=dict(date_of_birth=contact.date_of_birth,gender=contact.gender,phone=contact.phone,email=contact.email,location=address,website=website)
    order={'executive':('date_of_birth','gender','phone','email','website','location'),'corporate':('phone','date_of_birth','email','website','location','gender'),'consultant':('phone','email','website','location','date_of_birth','gender'),'precision':('phone','date_of_birth','email','website','location','gender')}[template]
    return '<div class="professional-contacts">'+''.join('<div class="contact-item">'+('<span class="contact-letter">'+{'phone':'M','email':'@','website':'W'}.get(key,'')+'</span>' if template=='corporate' and key in {'phone','email','website'} else _icon(key))+'<span>'+escape(values[key] or '')+'</span></div>' for key in order if values[key] or key!='gender' or template in {'executive','consultant'})+'</div>'


CSS='''
@page{size:A4;margin:8pt}*{box-sizing:border-box}html,body{margin:0;padding:0;background:white}body{font-family:ProfessionalFont,Arial,sans-serif;font-size:9.5pt;line-height:1.48;color:#111;overflow-wrap:anywhere;-webkit-print-color-adjust:exact;print-color-adjust:exact}h1,h2,h3,p{margin:0}h1{font-size:18pt;line-height:1.3;font-weight:700}h2{font-size:12pt;line-height:1.35;font-weight:700;break-after:avoid}h3{font-size:9.5pt;line-height:1.5;font-weight:700;break-after:avoid}ul{padding-left:13pt;margin:4pt 0 0}li{margin:2pt 0;break-inside:avoid}.professional-layout{display:grid;grid-template-columns:41% minmax(0,1fr);gap:10pt;align-items:stretch}.professional-sidebar{background:var(--side-bg);padding:12pt 10pt 16pt;min-width:0}.professional-main{padding:8pt 6pt 14pt 0;min-width:0}.professional-identity{text-align:center;margin-bottom:19pt;break-inside:avoid}.professional-identity h1{color:var(--accent)}.professional-headline{font-size:11pt;margin:4pt 0 17pt}.professional-avatar{display:block;width:132pt;height:132pt;border-radius:50%;object-fit:cover;border:2pt solid var(--accent);margin:0 auto;background:#f4f5f5}.professional-section{margin-bottom:19pt}.professional-section h2{color:var(--accent);margin:0 0 11pt}.professional-section:not(:last-child){border-bottom:1px solid var(--rule);padding-bottom:16pt}.professional-entry{margin:0 0 15pt}.professional-entry:last-child{margin-bottom:0}.entry-top{display:flex;align-items:baseline;justify-content:space-between;gap:8pt;break-after:avoid}.entry-top>h3,.entry-top>p:first-child{flex:1;min-width:0}.entry-top .period{flex-shrink:0;max-width:38%;font-size:9pt}.entry-subtitle{font-weight:700;margin:9pt 0 3pt}.section-education .entry-subtitle{font-weight:400}.professional-contacts{display:flex;flex-direction:column;gap:9pt;font-size:9pt}.contact-item{display:flex;gap:10pt;align-items:flex-start;min-height:11pt;min-width:0}.contact-icon{width:10pt;height:11pt;flex-shrink:0;fill:none;stroke:currentColor;stroke-width:1.8;stroke-linecap:round;stroke-linejoin:round;color:var(--accent);margin-top:1pt}.contact-letter{min-width:10pt;font-weight:700}.professional-sidebar .professional-section{margin-top:20pt}.skills-line{line-height:1.5;margin:7pt 0}.skills-line strong{font-weight:700}.professional-person{margin-top:7pt}.professional-person p{margin-top:3pt}.supplementary{display:grid;grid-template-columns:68pt minmax(0,1fr);gap:8pt}.supplementary h3{font-weight:400}
'''
CSS += '@media screen{body{width:210mm;min-height:297mm;padding:8pt}}'
STYLES={
'executive':''' .professional-layout{--side-bg:#eee5eb;--rule:#d8c5d0}.professional-sidebar .professional-section:last-child{border-bottom:1px solid var(--rule);padding-bottom:16pt}.professional-contacts{color:#111}.professional-main .entry-subtitle{font-weight:700}.professional-identity .professional-headline{margin-bottom:17pt}''',
'corporate':'''@page{margin:3pt 8pt}@media screen{body{padding:3pt 8pt}}.professional-layout{grid-template-columns:46% minmax(0,1fr);gap:22pt;--side-bg:#e9e9e9;--rule:transparent}.professional-sidebar{padding:30pt 10pt 16pt}.professional-main{padding:27pt 6pt 14pt 0}.professional-identity h1{font-size:24pt}.professional-headline{font-size:14pt;margin:3pt 0 15pt}.professional-avatar{border:9pt solid white;width:160pt;height:160pt}.professional-section h2{text-transform:uppercase;background:#303030;color:white;padding:4pt 8pt;font-size:11.5pt;margin-bottom:9pt}.professional-sidebar h2{text-align:center}.professional-section:not(:last-child){padding-bottom:0;border:0}.professional-main .professional-entry{position:relative;margin-left:3pt;padding-left:12pt;border-left:1px solid #777;padding-bottom:10pt}.professional-main .professional-entry:before{content:"";position:absolute;left:-4pt;top:4pt;width:7pt;height:7pt;background:#303030;border-radius:50%}.professional-main .entry-subtitle{font-weight:400;text-transform:uppercase;margin:4pt 0}.professional-main .entry-top h3{font-size:9pt}.professional-sidebar .skills-line{text-transform:uppercase;font-weight:600}.professional-main .supplementary{border:0}.professional-main .supplementary:before{display:none}''',
'consultant':'''@page{margin:3pt 8pt 3pt 0}@media screen{body{padding:3pt 8pt 3pt 0}}.professional-layout{grid-template-columns:34% minmax(0,1fr);gap:8pt;--side-bg:#30382f;--rule:transparent}.professional-sidebar{padding:0 8pt 16pt;color:#f2f2f2}.professional-main{padding:9pt 3pt 12pt 0}.professional-identity{display:flex;flex-direction:column;background:#52604f;margin:0 -8pt 9pt;padding:7pt 7pt 11pt}.professional-identity h1{order:2;color:#f2f2f2;font-size:18pt;padding-top:11pt;margin-top:9pt;border-top:1px solid #3e4c3e}.professional-headline{order:3;margin:8pt 0 0}.professional-avatar{order:1;width:184pt;height:184pt;border:0}.professional-sidebar .contact-icon{color:#edead7;background:#52604f;border-radius:50%;padding:2pt;width:13pt;height:13pt}.professional-sidebar h2{color:#f2f2f2}.professional-main h2{color:#111;padding-left:32pt;position:relative}.professional-main h2:before{content:"";position:absolute;left:0;top:-2pt;width:22pt;height:22pt;background:#52604f;border-radius:50%}.professional-main .section-education h2:after{content:"◆";position:absolute;left:7pt;top:1pt;color:#f5f1df;font-size:10pt}.professional-main .section-experience h2:after{content:"●";position:absolute;left:7pt;top:1pt;color:#f5f1df;font-size:10pt}.professional-section:not(:last-child){border:0;padding-bottom:0}.entry-subtitle{margin-top:7pt}.section-education .professional-entry>h3{margin-top:8pt}''',
'precision':'''@page{margin:3pt 8pt 3pt 0}@media screen{body{padding:3pt 8pt 3pt 0}}.professional-layout{grid-template-columns:37.5% minmax(0,1fr);gap:10pt;--side-bg:#342525;--rule:#6b5656}.professional-sidebar{padding:0 10pt 16pt;color:white}.professional-main{padding:12pt 3pt 12pt 0}.professional-identity{background:#5d4545;margin:0 -10pt 14pt;padding:14pt 10pt 12pt;display:flex;flex-direction:column}.professional-identity h1{color:white;order:2;font-size:19pt;border-top:1px solid #523b3b;margin:3pt -10pt 0;padding:11pt 7pt 0}.professional-headline{color:white;order:3;font-size:14pt;margin:7pt 0 0}.professional-avatar{order:1;width:150pt;height:150pt;border:7pt solid #9b8989;margin:0 auto 0}.professional-contacts{gap:17pt}.professional-contacts .contact-icon{color:white}.professional-section h2{display:flex;align-items:center;gap:4pt;color:white;font-size:11.5pt}.professional-section h2:after{content:"";height:1px;background:#a79c9c;flex:1}.professional-section h2>span{background:#5d4545;border-radius:22pt;padding:6pt 11pt}.professional-section:not(:last-child){border:0;padding-bottom:0}.professional-sidebar .professional-section{margin-top:18pt}.professional-main .entry-subtitle{font-weight:400}.professional-sidebar .professional-entry h3{font-size:9.5pt}.professional-sidebar .period{margin:5pt 0}.professional-sidebar .institution{font-weight:700;margin:7pt 0}.professional-sidebar .professional-section h2:after{background:#5e4949}''',
}


def render_professional(document,template,options):
    info=REFERENCES[template]
    sections={s.kind:s for s in document.sections}
    avatar='data:image/svg+xml;base64,'+base64.b64encode(AVATAR.encode()).decode()
    if options.photo_asset_id:
        from backend.app.services.assets import photo_data
        avatar=photo_data(options.photo_asset_id)
    identity='<header class="professional-identity"><h1>'+escape(document.contact.full_name or 'Họ và tên')+'</h1><p class="professional-headline">'+escape(document.contact.headline or '')+'</p><img class="professional-avatar" alt="Ảnh đại diện" src="'+avatar+'"></header>'
    contacts='<section class="professional-section personal-section">'+('<h2><span>Thông tin cá nhân</span></h2>' if template in {'executive','corporate'} else '')+_contacts(document.contact,template)+'</section>'
    summary='<section class="professional-section professional-summary"><h2><span>'+('Mục tiêu nghề nghiệp' if document.language=='vi' else 'Career objective')+'</span></h2><p>'+escape(document.summary.text)+'</p></section>' if document.summary else ''
    side=identity+contacts
    if template in {'corporate','consultant'}:side+=summary
    if template=='precision':side+=_section(sections.get('education'),template,True)
    side+=_section(sections.get('skills'),template,True)
    if template in {'corporate','precision'}:side+=_section(sections.get('references'),template,True)
    if template=='consultant' and getattr(document.contact,'interests',None):side+='<section class="professional-section"><h2><span>Sở thích</span></h2><p>'+escape(document.contact.interests)+'</p></section>'
    order={'executive':['education','experience','awards','certifications','project','involvement','references'],'corporate':['experience','project','education','certifications','awards','involvement'],'consultant':['education','experience','awards','certifications','involvement','project','references'],'precision':['experience','awards','certifications','project','involvement']}[template]
    main=summary if template in {'executive','precision'} else ''
    main+=''.join(_section(sections.get(kind),template) for kind in order)
    if getattr(document.contact,'additional_info',None):main+='<section class="professional-section"><h2><span>Thông tin thêm</span></h2><p>'+escape(document.contact.additional_info)+'</p></section>'
    fonts=''.join('@font-face{font-family:ProfessionalFont;font-weight:'+str(w)+';src:url(data:font/ttf;base64,'+reference_font(w)+')}' for w in (400,500,600,700))
    accent=options.color if options.color!='#000000' else info[2]
    css=fonts+CSS+STYLES[template]+f':root{{--accent:{accent}}}body{{font-size:{options.font_size}pt;line-height:{options.line_height}}}'
    return '<!doctype html><html lang="'+document.language+'"><head><meta charset="utf-8"><meta http-equiv="Content-Security-Policy" content="default-src \'none\'; style-src \'unsafe-inline\'; img-src data:; font-src data:; base-uri \'none\'"><style>'+css+'</style></head><body class="professional-'+template+'"><div class="professional-layout"><aside class="professional-sidebar">'+side+'</aside><main class="professional-main">'+main+'</main></div></body></html>'
