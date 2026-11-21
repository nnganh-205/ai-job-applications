"""Project title, technology and repository row shared by all HTML/PDF layouts."""
import re
from html import escape
from urllib.parse import urlsplit

from bs4 import BeautifulSoup


FIELDS = {'technologies','github_url','demo_url','project_url'}
CSS = '''
.project-header-line{white-space:normal!important;overflow-wrap:anywhere!important;word-break:normal;min-width:0;text-transform:none!important}
.project-header-line .project-meta{font-weight:400;font-style:normal;white-space:normal;overflow-wrap:anywhere}
.project-header-line .project-technologies{font-style:italic}
.project-header-line a{color:inherit;text-decoration:underline;overflow-wrap:anywhere;white-space:normal}
.section-project .entry-main,.section-project .entry-aside{min-width:0}
.section-project .entry-top>h3{min-width:0;flex:1}.section-project .entry-top>.period{flex-shrink:0;max-width:35%;white-space:normal}
'''


def metadata_field(bullet):
    fields = {ref.split('/')[3] for ref in bullet.source_refs if len(ref.split('/')) > 3 and ref.startswith('/project/')}
    return next(iter(fields)) if len(fields)==1 and fields.issubset(FIELDS) else None


def safe_href(value):
    value=value.strip()
    if re.match(r'^(?:www\.)?github\.com/',value,re.I):value='https://'+value
    try:
        parsed=urlsplit(value)
        if parsed.scheme not in {'http','https'} or not parsed.hostname or parsed.username or parsed.password or any(c.isspace() for c in value):return None
    except ValueError:return None
    return value


def decorate_projects(html, document):
    projects=next((s for s in document.sections if s.kind=='project'),None)
    if not projects or not any(metadata_field(b) for e in projects.entries for b in e.bullets):return html
    soup=BeautifulSoup(html,'html.parser')
    scope=soup.select_one('.section-project,#cvo-project')
    if scope is None:
        heading=next((h for h in soup.find_all('h2') if h.get_text(' ',strip=True)==projects.heading),None)
        scope=heading.find_parent('section') if heading else None
    if scope is None:return html
    normalize=lambda value:' '.join(value.split())
    for entry in projects.entries:
        meta=[b for b in entry.bullets if metadata_field(b)]
        if not meta:continue
        title=next((node for node in scope.find_all(string=True)
                    if normalize(str(node))==normalize(entry.title)
                    and not node.find_parent(class_='project-header-line')),None)
        if title is None:continue
        parent=title.parent
        parent['class']=[*parent.get('class',[]),'project-header-line']
        fragments=[]
        links=set()
        for bullet in meta:
            field=metadata_field(bullet)
            if field=='technologies':
                value=re.sub(r'^(?:Công nghệ|Technologies)\s*:\s*','',bullet.text,flags=re.I)
                fragments.append('<span class="project-meta project-technologies"> | '+escape(value)+'</span>')
            else:
                href=safe_href(bullet.text)
                if href in links and href:continue
                if href:links.add(href)
                host=(urlsplit(href).hostname or '').lower() if href else ''
                label='GitHub' if field=='github_url' or host in {'github.com','www.github.com','gist.github.com'} else 'Demo' if field=='demo_url' else ('Dự án' if document.language=='vi' else 'Project')
                content='<a href="'+escape(href,quote=True)+'" target="_blank" rel="noopener noreferrer" aria-label="'+escape(label+' '+entry.title,quote=True)+'">'+label+'</a>' if href else escape(label+': '+bullet.text)
                fragments.append('<span class="project-meta project-link"> | '+content+'</span>')
        fragment=BeautifulSoup(escape(entry.title)+''.join(fragments),'html.parser')
        title.replace_with(*list(fragment.contents))
        # Metadata lives on the heading, not as extra task bullets. Limit removal
        # to this project entry so another project with the same stack is intact.
        container=parent.find_parent('article') or parent.find_parent(class_='row') or scope
        for bullet in meta:
            for item in list(container.find_all('li')):
                if normalize(item.get_text(' ',strip=True))==normalize(bullet.text):item.decompose()
    style=soup.new_tag('style');style.string=CSS
    soup.head.append(style)
    return str(soup)
