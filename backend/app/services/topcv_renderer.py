"""Fill downloaded public TopCV HTML/CSS with the application's CV facts."""
from copy import deepcopy
from functools import lru_cache
from pathlib import Path
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1] / 'templates' / 'topcv'


@lru_cache(maxsize=24)
def source(template):
    return (ROOT / (template + '.html')).read_text(), (ROOT / (template + '.css')).read_text()


def _text(node, value):
    if node is not None:
        node.clear()
        node.append(str(value or ''))


def _fill_row(prototype, entry, kind, soup):
    row = deepcopy(prototype)
    prefix = {'education':'education', 'experience':'experience', 'involvement':'activity', 'project':'experience'}[kind]
    first, _, last = (entry.period or '').partition(' – ')
    title = {'education':'school','experience':'position','involvement':'position','project':'company'}[kind]
    subtitle = {'education':'title','experience':'company','involvement':'organization','project':'position'}[kind]
    values = {title:entry.title, subtitle:entry.subtitle or '', 'start':first, 'end':last}
    for field, value in values.items():
        for target in row.select('.cvo-' + prefix + '-' + field):
            _text(target, value)
    # Templates use either two date spans or one time field.
    if not row.select('.cvo-' + prefix + '-start'):
        for target in row.select('.cvo-' + prefix + '-time'):
            _text(target, entry.period)
    detail = row.select_one('.cvo-' + prefix + '-details')
    if detail is None:
        detail = soup.new_tag('div', attrs={'class':['cvo-' + prefix + '-details']})
        row.append(detail)
    detail.clear()
    if entry.bullets:
        ul = soup.new_tag('ul')
        for bullet in entry.bullets:
            li = soup.new_tag('li');li.string = bullet.text;ul.append(li)
        detail.append(ul)
    # Some original rows omit a subtitle or period; keep every source field visible.
    visible = row.get_text(' ', strip=True)
    for value in (entry.title, entry.subtitle):
        if value and ' '.join(value.split()) not in ' '.join(visible.split()):
            field = soup.new_tag('p');field.string = value;row.insert(0, field)
    if entry.period and not row.select('.cvo-' + prefix + '-start, .cvo-' + prefix + '-time'):
        field = soup.new_tag('p');field.string = entry.period;row.insert(0,field)
    if not entry.period:
        for text in list(row.find_all(string=True)):
            if text.strip() and all(c in '[]()-–— /' for c in text.strip()):text.extract()
    return row


def render_topcv(document, template, options):
    html, css = source(template)
    soup = BeautifulSoup(html, 'html.parser')
    root = soup.select_one('#cvo-body')
    contact = document.contact
    contact_values = {'fullname':contact.full_name or 'CV', 'title':contact.headline, 'email':contact.email,
                      'phone':contact.phone, 'address':contact.location,
                      'website':' · '.join(dict.fromkeys(v for v in [contact.website,contact.linkedin,contact.github,contact.portfolio_url] if v)),
                      'dob':contact.date_of_birth, 'gender':contact.gender}
    places = [getattr(contact, key) for key in ('location','city','state_or_province','country') if getattr(contact,key)]
    contact_values['address'] = ', '.join(dict.fromkeys(places))
    for field, value in contact_values.items():
        target = soup.select_one('#cvo-profile-' + field)
        if target is None: continue
        _text(target, value)
        if not value:
            tr = target.find_parent('tr')
            if tr and tr.find('table') is None:tr.decompose()
            elif any(c in target.parent.get('class',[]) for c in ('profile-item','cvo-profile-info-row','contact-item')) or target.parent.get('id','').endswith('-wraper'):
                target.parent.decompose()
            else:target['style']='display:none'
    header = soup.select_one('#cvo-header')
    if header:header['class']=header.get('class',[]) + ['hide-avatar']
    if options.photo_asset_id:
        from backend.app.services.assets import photo_data
        avatar = soup.new_tag('img', id='cvo-profile-avatar', src=photo_data(options.photo_asset_id))
        avatar['style']='width:75px;height:95px;object-fit:cover;float:right;margin:0 0 12px 16px'
        root.insert(0, avatar)
    # Source fragments contain empty prototypes, never candidate/sample facts.
    prototypes = {kind:deepcopy(soup.select_one('#cvo-' + kind)) for kind in ('education','experience','activity')}
    for block in list(soup.select('.cvo-block')):
        if block.get('id') not in {'cvo-profile','cvo-objective','cvo-education','cvo-experience','cvo-activity'} and not block.select_one('[id^="cvo-profile-"]'):
            block.decompose()
    summary = soup.select_one('#cvo-objective')
    if summary:
        if document.summary:_text(summary.select_one('#cvo-objective-objective'), document.summary.text)
        else:summary.decompose()
    sections = {section.kind:section for section in document.sections}
    blocks = {}
    for kind in ('education','experience','project','involvement','skills','certifications','awards','references'):
        original_kind = {'involvement':'activity','project':'experience','skills':'education','certifications':'education','awards':'education','references':'education'}.get(kind,kind)
        section = sections.get(kind)
        block = soup.select_one('#cvo-' + original_kind) if kind in {'education','experience','involvement'} else None
        if not section:
            if block:block.decompose()
            continue
        if block is None:
            block = deepcopy(prototypes[original_kind])
            if block is None:raise ValueError('Mẫu TopCV thiếu cấu trúc mục: '+kind)
            block['id']='cvo-' + kind
        block.name='section'
        block['class']=block.get('class',[]) + ['cv-section','section-'+kind]
        heading = block.select_one('[id$="-blocktitle"]')
        if heading:_text(heading,section.heading);heading['id']='cvo-'+kind+'-blocktitle'
        table = block.select_one('[id$="-table"]')
        if table is None:raise ValueError('Mẫu TopCV thiếu vùng nội dung')
        row = deepcopy(table.select_one('.row'))
        table.clear();table['id']=kind+'-table'
        if kind=='skills':
            for entry in section.entries:
                line = soup.new_tag('p',attrs={'class':['skills-line']})
                strong = soup.new_tag('strong');strong.string=entry.title+':';line.append(strong)
                line.append(' '+', '.join(b.text for b in entry.bullets));table.append(line)
        elif kind in {'certifications','awards','references'}:
            for entry in section.entries:
                article=soup.new_tag('article',attrs={'class':['entry']})
                title=soup.new_tag('h4');title.string=entry.title;article.append(title)
                for value in (entry.subtitle,entry.period):
                    if value:
                        paragraph=soup.new_tag('p');paragraph.string=value;article.append(paragraph)
                for bullet in entry.bullets:
                    paragraph=soup.new_tag('p');paragraph.string=bullet.text;article.append(paragraph)
                table.append(article)
        else:
            if row is None:raise ValueError('Mẫu TopCV thiếu cấu trúc dòng')
            for entry in section.entries:table.append(_fill_row(row,entry,kind,soup))
        blocks[kind]=block
    # Education comes first, including saved CVs whose source order predates this UI.
    anchor = blocks.get('experience') or blocks.get('involvement')
    education = blocks.get('education')
    if anchor and education:
        education.extract();anchor.insert_before(education)
    primary = (blocks.get('experience') or blocks.get('education'))
    parent = primary.parent if primary and primary.parent else (soup.select_one('#group-content') or soup.select_one('#cvo-main') or root)
    if 'project' in blocks:
        (blocks.get('experience') or blocks.get('education')).insert_after(blocks['project']) if primary else parent.append(blocks['project'])
    if 'skills' in blocks:
        # Several originals reserve a second column for optional skill blocks.
        spare = next((column for column in soup.select('#group-right,#group-col-left,#group-col-right')
                      if not column.select('.cvo-block,[id^="cvo-profile-"]')),None)
        (spare if spare is not None else parent).append(blocks['skills'])
    for kind in ('certifications','awards','references'):
        if kind in blocks:parent.append(blocks[kind])
    # Remove empty picture scaffolding left by the source template.
    for target in list(soup.select('#cvo-avatar,#avatar,#avatar-group-outer,#group-header-avatar,#cvo-profile-avatar-wraper')):
        if not target.get_text(strip=True) and not target.select('img'):target.decompose()
    from backend.app.services.cv_renderer import font_data
    font = 'serif' if options.font=='serif' else 'sans-serif'
    from backend.app.services.cv_templates import metadata
    if options.color != metadata(template)['color']:
        css += '#cvo-profile-fullname,[id$=\"-blocktitle\"]{color:'+options.color+'!important}'
    css=css.replace('#cvo-experience', ':is(#cvo-experience,#cvo-project)')
    fixes = f'''
    @font-face{{font-family:LocalCV;src:url(data:font/ttf;base64,{font_data(options.font)})}}
    @page{{size:A4;margin:0}}
    html,body{{margin:0!important;background:white!important;color:#222;-webkit-print-color-adjust:exact;print-color-adjust:exact}}
    #cvo-document-root,#cvo-document,.cvo-document .cvo-page,.cvo-document .cvo-subpage{{width:210mm!important;max-width:210mm!important;min-height:0!important;height:auto!important;margin:0!important;box-shadow:none!important;border:0!important}}
    .cvo-document .cvo-page,.cvo-document .cvo-subpage{{padding:0!important;page-break-after:auto!important;break-after:auto!important;overflow:visible!important}}
    #cvo-main{{page-break-after:auto!important;break-after:auto!important}}
    #cvo-body{{min-height:0!important;height:auto!important;font-family:LocalCV,{font}!important;font-size:{options.font_size}pt!important;line-height:{options.line_height}!important;overflow-wrap:anywhere}}
    #cvo-body .cvo-block,#cvo-body .row{{height:auto!important;min-height:0!important}}
    #cvo-body .cvo-block-title,#cvo-body [id$="-blocktitle"]{{break-after:avoid}}
    #cvo-body .skills-line{{margin:4px 0!important;line-height:1.5!important;white-space:normal!important}}
    #cvo-body .skills-line strong{{font-weight:bold}}
    #cvo-body .row li{{margin:2px 0;break-inside:avoid}}
    #cvo-body:after{{content:"";display:block;clear:both}}
    '''
    body='<div id="cvo-document-root"><div id="cvo-document" class="cvo-document"><div class="cvo-page"><div class="cvo-subpage">'+str(root)+'</div></div></div></div>'
    return '<!doctype html><html lang="'+document.language+'"><head><meta charset="utf-8"><meta http-equiv="Content-Security-Policy" content="default-src \'none\'; style-src \'unsafe-inline\'; font-src data:; img-src data:; base-uri \'none\'"><style>'+css+fixes+'</style></head><body id="cv-viewer">'+body+'</body></html>'
