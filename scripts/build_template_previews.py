"""Build gallery thumbnails from the same HTML used by PDF export."""
import json
import re
import unicodedata
from pathlib import Path
import pymupdf
from PIL import Image, ImageDraw
from playwright.sync_api import sync_playwright
from backend.app.services.cv_templates import TEMPLATES, example_document
from backend.app.services.cv_renderer import render_html
from backend.app.services.topcv_renderer import render_topcv
from backend.app.schemas.resume import Presentation


def main():
    output = Path('frontend/public/templates/previews')
    output.mkdir(parents=True, exist_ok=True)
    report_dir = Path('output/evaluation/templates-24')
    report_dir.mkdir(parents=True, exist_ok=True)
    document = example_document()
    reports, cards = [], []
    with sync_playwright() as engine:
        browser = engine.chromium.launch(headless=True)
        try:
            context = browser.new_context(offline=True, java_script_enabled=False)
            page = context.new_page()
            for template in TEMPLATES:
                options = {key: template[key] for key in ('font', 'color')}
                options['template'] = template['id']
                html = (render_html(document, template['id'], options) if template.get('available', True)
                        else render_topcv(document, template['id'], Presentation.model_validate(options)))
                page.set_content(html, wait_until='load')
                page.evaluate('document.fonts.ready')
                skills = page.locator('.section-skills').inner_text()
                assert all(word.casefold() in skills.casefold() for word in ['Python', 'SQL', 'Azure ML', 'AWS']), template['id']
                assert page.locator('.section-skills li').count() == 0
                content = page.pdf(format='A4', print_background=True, prefer_css_page_size=True)
                (report_dir / (template['id'] + '.pdf')).write_bytes(content)
                with pymupdf.open(stream=content, filetype='pdf') as pdf:
                    text = ' '.join(' '.join(p.get_text() for p in pdf).split())
                    def normalized(value):
                        value=unicodedata.normalize('NFC',value).casefold()
                        value=re.sub(r'(?<=\w)([-–—])\s+(?=\w)',r'\1',value)
                        return ' '.join(value.split())
                    pdf_text=normalized(text)
                    for section in document.sections:
                        for entry in section.entries:
                            for value in [entry.title,entry.subtitle]+[bullet.text for bullet in entry.bullets]:
                                if value:assert normalized(value) in pdf_text,(template['id'],'missing PDF source field',value[:60])
                    assert 'nguyễn minh an' in text.casefold() and '3.6/4.0' in text and 'đại học minh họa' in text.casefold(), template['id']
                    assert 1 <= len(pdf) <= 12, (template['id'], len(pdf))
                    pages = len(pdf)
                    assert all(page.get_text().strip() for page in pdf), (template['id'], 'blank page')
                    for sheet in pdf:
                        for word in sheet.get_text('words'):
                            assert word[0] >= 0 and word[2] <= sheet.rect.width, (template['id'], word[:5])
                    pdf[0].get_pixmap(matrix=pymupdf.Matrix(1.25, 1.25)).save(str(output / (template['id'] + '.png')))
                image = Image.open(output / (template['id'] + '.png')).convert('RGB')
                image.thumbnail((270, 382))
                card = Image.new('RGB', (300, 420), '#eaf0f5')
                card.paste(image, ((300-image.width)//2, 8))
                ImageDraw.Draw(card).text((12, 398), template['name'], fill='black')
                cards.append(card)
                reports.append(dict(template=template['id'], category=template['category'], pages=pages, skills_inline=True))
        finally:
            browser.close()
    contact = Image.new('RGB', (1200, 2520), 'white')
    for index, card in enumerate(cards):
        contact.paste(card, ((index % 4)*300, (index // 4)*420))
    contact.save(report_dir / 'contact-sheet.png')
    (report_dir / 'report.json').write_text(json.dumps(reports, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
