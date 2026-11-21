"""Public TopCV templates; local IDs preserve compatibility with saved CVs."""
import json
from pathlib import Path

SOURCES = json.loads((Path(__file__).resolve().parents[1] / 'templates/topcv/sources.json').read_text())
CATEGORIES = ('basic','professional','modern','impressive','harvard','ats')
TEMPLATES = []
for index, original in enumerate(SOURCES):
    category = CATEGORIES[index // 4]
    TEMPLATES.append(dict(
        id=original['id'], version=2, name=original['name'], category=category,
        layout='two-column' if original.get('two_column') else 'one-column',
        font='serif' if category=='harvard' else 'sans', color='#000000',
        description='Mẫu gốc TopCV · '+original['name']+'.',
        source='topcv', source_url=original['source_url'], source_template=original['slug'],
        thumbnail='/templates/previews/'+original['id']+'.png',
    ))

from backend.app.services.simple_reference_templates import REFERENCES as SIMPLE_REFERENCES
from backend.app.services.professional_reference_templates import REFERENCES as PROFESSIONAL_REFERENCES
from backend.app.services.modern_reference_templates import REFERENCES as MODERN_REFERENCES
from backend.app.services.harvard_reference_templates import REFERENCES as HARVARD_REFERENCES
REFERENCES = {**SIMPLE_REFERENCES, **PROFESSIONAL_REFERENCES, **MODERN_REFERENCES, **HARVARD_REFERENCES}
for template in TEMPLATES:
    if template['id'] in REFERENCES:
        name, suffix, color, layout = REFERENCES[template['id']]
        template.update(name=name, version=3, color=color, layout=layout, source='user_pdf',
                        source_url=None, reference_file='Anh-Ngoc-TopCV.vn-181126.'+suffix+'.pdf',
                        description='Bố cục theo PDF bạn cung cấp, có ảnh đại diện.', renderer='pdf_reference')
        if suffix == '3':template['reference_file']='3.pdf'
    template['available'] = template['id'] in REFERENCES
    template['has_photo'] = template['category'] != 'harvard'
    template['contact_fields'] = ['full_name','headline','email','phone','location','website','linkedin','github','portfolio_url']
    if template['has_photo']:template['contact_fields'] += ['date_of_birth','gender']
    if template['id']=='consultant':template['contact_fields'] += ['interests','additional_info']
    template['form_sections'] = ['contact','education','experience','project','skills','certifications','awards','references','involvement','summary']
    template['entry_fields'] = {
        'education':['institution','degree','major','start_date','end_date','gpa','details'],
        'experience':['job_title','company','location','start_date','end_date','is_current','description'],
        'project':['project_name','role','technologies','github_url','start_date','end_date','description','project_url'],
        'skills':['group','items'], 'involvement':['activity_name','organization','role','period','description'],
        'certifications':['name','issuer','date','description'], 'awards':['title','organization','date','description'],
        'references':['full_name','position','organization','email','phone','relationship','description'],
    }
    template['page_width'] = 816 if template['id']=='classic' else 794
    template['page_height'] = 1056 if template['id']=='classic' else 1123
    template['font_size'] = 9.5 if template['id'] in {'compact','executive','consultant','precision','modern','sidebar','metro','split','academic','harvard'} else 9 if template['id']=='corporate' else 10
    template['line_height'] = 1.2 if template['id']=='classic' else 1.35 if template['id']=='compact' else 1.45 if template['id'] in REFERENCES else 1.4
    if template['category']=='harvard':template['description']='Bố cục Harvard theo PDF bạn cung cấp, không dùng ảnh đại diện.'


def metadata(template_id):
    from backend.app.services.template_catalog import get_metadata
    return get_metadata(template_id)


def example_document():
    from backend.app.schemas.profile import MasterProfile
    from ai.agents.cv_agent import source_document
    requested_profile = Path(__file__).resolve().parents[1] / 'templates/reference-previews/profile.json'
    profile = MasterProfile.model_validate_json(requested_profile.read_text())
    return source_document(profile,'requested-template-preview',language='vi')


def synthetic_document():
    """Non-personal fixture for renderer regression tests; never gallery content."""
    from backend.app.schemas.profile import MasterProfile
    from ai.agents.cv_agent import source_document
    profile=MasterProfile(contact={'full_name':'Nguyễn Minh An','headline':'Kỹ sư phần mềm','email':'minhan@example.com','phone':'090 000 0000','location':'Hà Nội, Việt Nam'},summary='Kỹ sư phần mềm xây dựng sản phẩm rõ ràng, hữu ích. Kinh nghiệm về hệ thống dữ liệu và ứng dụng web.',experience=[{'id':'demo-e','job_title':'Kỹ sư phần mềm','company':'Công ty Minh Họa','start_date':'2022-01','end_date':'2025-12','description':['Phát triển dịch vụ dữ liệu bằng Python và PostgreSQL.','Phối hợp cùng đội sản phẩm xây dựng trải nghiệm người dùng.','Thiết kế kiểm thử, giám sát và quy trình triển khai.']}],project=[{'id':'demo-p','project_name':'Career Workspace','role':'Lập trình viên','description':['Xây dựng công cụ chuẩn bị CV và khám phá cơ hội nghề nghiệp.','Phát triển frontend React và API FastAPI.']}],education=[{'id':'demo-ed','institution':'Đại học Minh Họa','degree':'Cử nhân Công nghệ thông tin','start_date':'2018-09','end_date':'2022-06'}],involvement=[{'id':'demo-i','organization':'Câu lạc bộ công nghệ','role':'Thành viên','description':['Chia sẻ kiến thức và hỗ trợ sinh viên xây dựng sản phẩm.']}],skills=[{'id':'demo-s','group':'Chuyên môn','items':['Python','PostgreSQL','React','FastAPI','Git']},{'id':'demo-l','group':'Ngôn ngữ','items':['Tiếng Việt','Tiếng Anh']}])
    return source_document(profile,'synthetic-template-preview',language='vi')
