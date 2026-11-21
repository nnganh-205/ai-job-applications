"""Three Harvard layouts matched to the supplied PDFs, including Jake Ryan."""
from html import escape
from backend.app.services.simple_reference_templates import _icon

REFERENCES={
 'classic':('Harvard 01 · Jake Ryan','3','#111111','one-column'),
 'academic':('Harvard 02 · Dòng thời gian','51800','#111111','one-column'),
 'harvard':('Harvard 03 · Cổ điển','51814','#111111','one-column'),
}


def _section(section,template):
    if not section or not section.entries:return ''
    kind=section.kind
    heading='Kinh nghiệm làm việc' if section.heading=='Kinh nghiệm' else section.heading
    result='<section class="harvard-section section-'+kind+'"><h2>'+escape(heading)+'</h2><div class="section-content">'
    for entry in section.entries:
        title,subtitle,period=map(lambda value:escape(value or ''),(entry.title,entry.subtitle,entry.period))
        if kind=='skills':
            result+='<p class="skills-line"><strong>'+title+':</strong> '+', '.join(escape(b.text) for b in entry.bullets)+'</p>';continue
        if kind=='references':
            result+='<article class="harvard-person"><h3>'+title+'</h3>'+(('<p>'+subtitle+'</p>') if subtitle else '')
            for bullet in entry.bullets:
                field=bullet.source_refs[0].split('/')[3] if bullet.source_refs and len(bullet.source_refs[0].split('/'))>3 else ''
                result+='<p>'+{'email':'Email: ','phone':'SĐT: ','relationship':'Quan hệ: '}.get(field,'')+escape(bullet.text)+'</p>'
            result+='</article>';continue
        if template=='academic':
            left=(title if kind in {'education','project'} else subtitle or title)
            right=(subtitle if kind in {'education','project'} else title)
            result+='<article class="harvard-entry"><div class="entry-aside"><h3>'+left+'</h3><p class="period">'+period+'</p></div><div class="entry-main"><h3>'+right+'</h3>'
        else:
            top=title if kind in {'education','project','certifications','awards'} or template=='classic' else subtitle or title
            second=subtitle if kind in {'education','project','certifications','awards'} or template=='classic' else title
            if template=='classic' and kind=='education':
                result+='<article class="harvard-entry"><div class="entry-top"><h3>'+top+'</h3></div><div class="entry-top entry-subtitle"><p>'+second+'</p><span class="period">'+period+'</span></div><div class="entry-main">'
            else:
                result+='<article class="harvard-entry"><div class="entry-top"><h3>'+top+'</h3><span class="period">'+period+'</span></div>'+(('<p class="entry-subtitle">'+second+'</p>') if second else '')+'<div class="entry-main">'
        if entry.bullets:
            result+='<ul>'
            for bullet in entry.bullets:
                value=bullet.text
                if kind=='education' and any(ref.endswith('/gpa') for ref in bullet.source_refs) and not value.lower().startswith('gpa'):value='GPA: '+value
                result+='<li>'+escape(value)+'</li>'
            result+='</ul>'
        result+='</div></article>'
    return result+'</div></section>'


BASE='''
@page{size:A4;margin:15pt}*{box-sizing:border-box}html,body{margin:0;padding:0;background:white;color:#111}body{font-family:HarvardSerif,"Times New Roman",serif;font-size:9.5pt;line-height:1.4;overflow-wrap:anywhere;-webkit-print-color-adjust:exact;print-color-adjust:exact}h1,h2,h3,p{margin:0}h1{font-size:20pt;line-height:1.2;font-weight:700}h2{font-size:11pt;font-weight:700;line-height:1.3;text-transform:uppercase;break-after:avoid}h3{font-size:9.5pt;font-weight:700;line-height:1.4;break-after:avoid}ul{padding-left:14pt;margin:4pt 0 0}li{margin:2pt 0;break-inside:avoid}.harvard-header{break-inside:avoid;text-align:center;margin-bottom:21pt}.harvard-headline{margin-top:9pt;font-size:10.5pt}.harvard-contacts{display:flex;align-items:center;justify-content:center;flex-wrap:wrap;gap:8pt 11pt;margin-top:12pt;font-size:9pt}.contact-item{display:inline-flex;gap:5pt;align-items:center;min-width:0}.contact-icon{flex-shrink:0;width:10pt;height:11pt;fill:none;stroke:currentColor;stroke-width:1.8;stroke-linecap:round;stroke-linejoin:round}.harvard-section{margin-top:18pt}.harvard-section h2{border-bottom:1px solid #222;padding-bottom:4pt;margin-bottom:7pt}.harvard-entry{margin:0 0 12pt}.harvard-entry:last-child{margin-bottom:0}.entry-top{display:flex;justify-content:space-between;align-items:baseline;gap:10pt;break-after:avoid}.entry-top h3{min-width:0;flex:1}.entry-top .period{flex-shrink:0;max-width:35%}.entry-subtitle{margin-top:4pt}.skills-line{margin:4pt 0}.harvard-person{margin-top:6pt}.harvard-person p{margin-top:2pt}.harvard-summary p{margin-top:10pt}.section-certifications .harvard-entry,.section-awards .harvard-entry{border-bottom:1px solid #eee;padding-bottom:8pt}.section-certifications .harvard-entry:last-child,.section-awards .harvard-entry:last-child{border:0}.harvard-entry ul{margin-bottom:0}@media screen{body{width:210mm;min-height:297mm;padding:15pt}}
'''
STYLES={
'classic':'''@page{size:letter;margin:20pt 36pt 28pt}body{font-size:10pt;line-height:1.2}.harvard-header{margin-bottom:12pt}h1{font-size:25pt}.harvard-headline{font-size:10pt;margin-top:4pt}.harvard-contacts{margin-top:4pt;font-size:8.5pt;gap:3pt}.harvard-contacts .contact-icon{display:none}.harvard-contacts .contact-item:not(:last-child):after{content:" |";padding-left:3pt}.harvard-section{margin-top:11pt}.harvard-section h2{text-transform:none;font-variant:small-caps;font-size:11pt;font-weight:400;letter-spacing:.03em;border-color:#888;padding-bottom:2pt;margin-bottom:5pt}.harvard-entry{margin-bottom:6pt}.entry-subtitle{font-style:italic;margin-top:1pt}.entry-top h3{font-size:10pt}.entry-top .period{font-size:9pt}ul{padding-left:14pt;margin-top:3pt}li{margin:1pt 0}.skills-line{margin:1pt 0}.harvard-summary p{margin-top:4pt}@media screen{body{width:216mm;min-height:279mm;padding:20pt 36pt 28pt}}''',
'academic':'''body{font-family:Arial,HarvardSans,sans-serif}.harvard-header{display:grid;grid-template-columns:minmax(0,1fr) 230pt;gap:25pt;text-align:left;min-height:70pt}.harvard-header h1{font-size:18pt}.harvard-headline{font-size:11pt;margin-top:8pt}.harvard-contacts{display:flex;flex-direction:column;align-items:flex-start;justify-content:flex-start;border-left:1.5px solid #111;padding-left:6pt;margin:0;gap:7pt}.harvard-section{margin-top:25pt}.harvard-section h2{display:flex;align-items:center;gap:10pt;border:0;padding-bottom:12pt;position:relative;font-size:11pt}.harvard-section h2:before{content:"";position:absolute;left:0;bottom:5pt;width:25pt;height:3px;background:#111}.harvard-section h2:after{content:"";height:1px;background:#444;flex:1}.harvard-entry{display:grid;grid-template-columns:minmax(0,25%) minmax(0,1fr);gap:22pt;position:relative;margin-bottom:0;padding-bottom:15pt}.entry-main{border-left:1px dashed #555;padding-left:15pt;position:relative}.entry-main:before{content:"";position:absolute;left:-4pt;top:2pt;width:7pt;height:7pt;background:#111;border-radius:50%}.entry-aside .period{margin-top:7pt}.entry-main>h3{margin-bottom:4pt}.harvard-summary p{margin-top:3pt}''',
'harvard':'''body{font-family:"Times New Roman",HarvardSerif,serif;font-size:9.5pt;line-height:1.4}.harvard-header h1{font-size:19pt}.harvard-headline{font-size:11pt;margin-top:9pt}.harvard-section h2{font-size:11pt}.harvard-entry{border-bottom:1px solid #eee;padding-bottom:8pt;margin-bottom:10pt}.harvard-entry:last-child{border:0}.entry-top h3{font-size:9.5pt}.entry-subtitle{margin:8pt 0 4pt}.harvard-section{margin-top:20pt}''',
}


def render_harvard(document,template,options):
    from backend.app.services.cv_renderer import font_data
    sections={s.kind:s for s in document.sections}
    contact=document.contact
    address=', '.join(dict.fromkeys(v for v in [contact.location,contact.city,contact.state_or_province,contact.country] if v))
    values=[('phone',contact.phone),('email',contact.email),('website',contact.linkedin),('website',contact.github),('website',contact.website),('website',contact.portfolio_url),('location',address)]
    contacts='<div class="harvard-contacts">'+''.join('<span class="contact-item">'+_icon(kind)+escape(value)+'</span>' for kind,value in values if value)+'</div>'
    identity='<div><h1>'+escape(contact.full_name or 'Họ và tên')+'</h1>'+('<p class="harvard-headline">'+escape(contact.headline)+'</p>' if contact.headline else '')+'</div>'
    body='<header class="harvard-header">'+identity+contacts+'</header>'
    if document.summary:body+='<section class="harvard-section harvard-summary"><h2>'+('Mục tiêu nghề nghiệp' if document.language=='vi' else 'Summary')+'</h2><p>'+escape(document.summary.text)+'</p></section>'
    order=['experience','project','education','certifications','awards','skills','references','involvement'] if template=='academic' else ['education','experience','project','skills','certifications','awards','references','involvement'] if template=='classic' else ['education','experience','certifications','awards','skills','references','project','involvement']
    body+=''.join(_section(sections.get(kind),template) for kind in order)
    fonts='@font-face{font-family:HarvardSerif;src:url(data:font/ttf;base64,'+font_data('serif')+')}@font-face{font-family:HarvardSans;src:url(data:font/ttf;base64,'+font_data('sans')+')}'
    pagination='.harvard-entry{break-inside:avoid}.entry-aside{break-inside:avoid}' if template=='academic' else ''
    css=fonts+BASE+STYLES[template]+pagination+f'body{{font-size:{options.font_size}pt;line-height:{options.line_height}}}'
    return '<!doctype html><html lang="'+document.language+'"><head><meta charset="utf-8"><meta http-equiv="Content-Security-Policy" content="default-src \'none\'; style-src \'unsafe-inline\'; font-src data:; img-src data:; base-uri \'none\'"><style>'+css+'</style></head><body>'+body+'</body></html>'
