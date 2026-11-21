"""Render all shipped layouts with synthetic Vietnamese/multipage data; no personal CVs."""
from pathlib import Path
import pymupdf
from PIL import Image,ImageOps,ImageDraw
from backend.app.services.cv_renderer import render_pdf,TEMPLATES
from ai.agents.cv_agent import source_document
from backend.app.schemas.profile import MasterProfile


def main():
    root=Path('output/evaluation/templates');root.mkdir(parents=True,exist_ok=True)
    profile=MasterProfile(contact={'full_name':'Nguyễn Minh An','email':'demo@example.com','location':'Hà Nội, Việt Nam'},summary='Kỹ sư phần mềm quan tâm tới hệ thống dữ liệu, trải nghiệm người dùng và sản phẩm có ích.',experience=[{'id':'exp','job_title':'PRIMARY_MARKER','company':'Đơn vị minh họa','start_date':'2021-01','end_date':'2025-12','description':[f'Mục {i}: Phát triển API Python và PostgreSQL, kiểm thử dữ liệu tiếng Việt, triển khai sản phẩm và giám sát hệ thống.' for i in range(1,60)]}],project=[{'id':'p','project_name':'Nền tảng nghề nghiệp','description':['Xây dựng công cụ chuẩn bị hồ sơ và tìm kiếm việc làm có nguồn.']}],education=[{'id':'e','institution':'Đại học minh họa','degree':'Cử nhân','major':'Công nghệ thông tin','start_date':'2017-09','end_date':'2021-06'}],involvement=[],skills=[{'id':'s','group':'SIDEBAR_MARKER','items':['Python','PostgreSQL','React','Tiếng Việt']}])
    document=source_document(profile,'synthetic-template-qa',language='vi');cards=[]
    for template in (item for item in TEMPLATES if item.get('available',True)):
        options={k:template[k] for k in ('font','color')};options.update(template=template['id'],font_size=10,line_height=1.4)
        content=render_pdf(document,template['id'],options);(root/(template['id']+'.pdf')).write_bytes(content)
        with pymupdf.open(stream=content,filetype='pdf') as pdf:
            text=' '.join(' '.join(p.get_text() for p in pdf).split())
            assert all(x.casefold() in text.casefold() for x in ['Nguyễn Minh An','Mục 59','SIDEBAR_MARKER','Nền tảng nghề nghiệp']),template['id']
            assert len(pdf)>1
            for page in pdf:
                for word in page.get_text('words'):
                    assert word[0]>=0 and word[2]<=page.rect.width,(template['id'],'horizontal overflow',word[:4])
            for i,page in enumerate(pdf):page.get_pixmap().save(str(root/f'{template["id"]}-{i+1}.png'))
            image=Image.open(root/f'{template["id"]}-1.png').convert('RGB');image.thumbnail((300,420));card=Image.new('RGB',(320,450),'#e8edf6');card.paste(image,((320-image.width)//2,20));ImageDraw.Draw(card).text((12,432),template['name'],fill='black');cards.append(card)
    contact=Image.new('RGB',(960,450*((len(cards)+2)//3)),'white')
    for i,card in enumerate(cards):contact.paste(card,((i%3)*320,(i//3)*450))
    contact.save(root/'contact-sheet.png')


if __name__=='__main__':main()
