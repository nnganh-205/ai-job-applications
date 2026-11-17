"""Original local CV layouts. IDs ats/classic remain backward compatible."""
TEMPLATES = [
    dict(id='ats',version=2,name='Essential',category='basic',layout='one-column',font='sans',color='#2457d6',description='Một cột gọn gàng, ưu tiên nội dung và khả năng đọc văn bản.'),
    dict(id='classic',version=2,name='Harvard (Classic)',category='basic',layout='one-column',font='serif',color='#28374b',description='Căn giữa tên, đường phân cách mảnh và bố cục truyền thống.'),
    dict(id='modern',version=2,name='Horizon',category='modern',layout='two-column',font='sans',color='#2457d6',description='Hai cột với kỹ năng và học vấn ở cột phụ.'),
    dict(id='sidebar',version=2,name='Perspective',category='modern',layout='two-column',font='sans',color='#176b68',description='Thanh bên nhẹ, nhấn mạnh kinh nghiệm và dự án.'),
    dict(id='creative',version=2,name='Studio',category='creative',layout='one-column',font='sans',color='#8050ad',description='Tên nổi bật và dấu nhấn màu dành cho hồ sơ sáng tạo.'),
    dict(id='academic',version=2,name='Scholar',category='academic',layout='one-column',font='serif',color='#3d4655',description='Typography serif và phân cấp rõ cho hồ sơ học thuật.'),
]
for template in TEMPLATES:
    template['thumbnail'] = '/templates/previews/' + template['id'] + '.png'


def metadata(template_id):
    item=next((t for t in TEMPLATES if t['id']==template_id),None)
    if item is None:raise ValueError('Mẫu CV không tồn tại')
    return item


def example_document():
    from backend.app.schemas.profile import MasterProfile
    from ai.agents.cv_agent import source_document
    profile=MasterProfile(contact={'full_name':'Nguyễn Minh An','email':'minhan@example.com','phone':'090 000 0000','location':'Hà Nội, Việt Nam'},summary='Kỹ sư phần mềm xây dựng sản phẩm rõ ràng, hữu ích. Kinh nghiệm về hệ thống dữ liệu và ứng dụng web.',experience=[{'id':'demo-e','job_title':'Kỹ sư phần mềm','company':'Công ty Minh Họa','start_date':'2022-01','end_date':'2025-12','description':['Phát triển dịch vụ dữ liệu bằng Python và PostgreSQL.','Phối hợp cùng đội sản phẩm xây dựng trải nghiệm người dùng.','Thiết kế kiểm thử, giám sát và quy trình triển khai.']}],project=[{'id':'demo-p','project_name':'Career Workspace','role':'Lập trình viên','description':['Xây dựng công cụ chuẩn bị CV và khám phá cơ hội nghề nghiệp.','Phát triển frontend React và API FastAPI.']}],education=[{'id':'demo-ed','institution':'Đại học Minh Họa','degree':'Cử nhân Công nghệ thông tin','start_date':'2018-09','end_date':'2022-06'}],involvement=[{'id':'demo-i','organization':'Câu lạc bộ công nghệ','role':'Thành viên','description':['Chia sẻ kiến thức và hỗ trợ sinh viên xây dựng sản phẩm.']}],skills=[{'id':'demo-s','group':'Chuyên môn','items':['Python','PostgreSQL','React','FastAPI','Git']},{'id':'demo-l','group':'Ngôn ngữ','items':['Tiếng Việt','Tiếng Anh']}])
    return source_document(profile,'synthetic-template-preview',language='vi')
