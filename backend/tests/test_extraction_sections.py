import unittest

import pymupdf

from ai.agents.cv_agent import source_document
from ai.agents.profile_agent import fill_explicit_skill_section, _entry_span, validate_against_source
from ai.agents.profile_sections import explicit_skills
from backend.app.schemas.profile import MasterProfile
from backend.app.services.document_reader import read_pdf


class ExtractionSectionTests(unittest.TestCase):
    def test_two_columns_do_not_interleave_experience_into_skills(self):
        with pymupdf.open() as pdf:
            page = pdf.new_page(width=600, height=800)
            for x, y, text in [(30, 100, 'Skills'), (30, 140, 'Python, SQL'),
                               (30, 180, 'Docker, Git'), (30, 240, 'Certifications'),
                               (260, 100, 'Work Experience'), (260, 140, 'Developer | Example Corp'),
                               (260, 180, 'Built APIs with TensorFlow.'),
                               (260, 240, 'Maintained production services.')]:
                page.insert_text((x, y), text, fontsize=10)
            text = read_pdf(pdf.tobytes())
        skills = explicit_skills(text)
        self.assertEqual([item for group in skills for item in group.items], ['Python', 'SQL', 'Docker', 'Git'])
        self.assertNotIn('TensorFlow', str(skills))
        self.assertLess(text.index('Certifications'), text.index('Work Experience'))

    def test_full_width_header_and_footer_surround_columns(self):
        with pymupdf.open() as pdf:
            page = pdf.new_page(width=600, height=800)
            page.insert_text((30, 30), 'Candidate ' + 'full width header ' * 4, fontsize=10)
            for x, label in [(30, 'Left'), (300, 'Right')]:
                for index, y in enumerate([200, 300, 400]):
                    page.insert_text((x, y), f'{label} {index}', fontsize=10)
            page.insert_text((30, 780), 'Copyright Example', fontsize=10)
            text = read_pdf(pdf.tobytes())
        self.assertLess(text.index('header'), text.index('Left 0'))
        self.assertLess(text.index('Left 2'), text.index('Right 0'))
        self.assertGreater(text.index('Copyright'), text.index('Right 2'))

    def test_wrapped_skill_parentheses_and_all_section_boundaries(self):
        text = '''Kỹ năng
✨
Machine Learning (Linear
Regression, SVM)

✨ Python (NumPy, pandas,
scikit-learn, matplotlib)

SQL
Azure ML
Kinh nghiệm làm việc
Thiết kế pipeline huấn luyện với TensorFlow và PyTorch.
Company ABC
2021 - Nay
'''
        groups = explicit_skills(text)
        self.assertEqual([(g.group, g.items) for g in groups], [
            ('Machine Learning', ['Linear Regression', 'SVM']),
            ('Python', ['NumPy', 'pandas', 'scikit-learn', 'matplotlib']),
            ('Chuyên môn', ['SQL', 'Azure ML']),
        ])
        for heading in ['Chứng chỉ', 'Người giới thiệu', 'Danh hiệu và giải thưởng', 'Mục tiêu nghề nghiệp', 'Professional Experience']:
            self.assertEqual(explicit_skills('Skills\nPython\n' + heading + '\nNot a skill')[0].items, ['Python'])

    def test_explicit_section_replaces_polluted_model_skills(self):
        profile = MasterProfile(contact={}, experience=[], project=[], education=[], involvement=[],
                                skills=[{'group': 'Other Skills', 'items': ['Built 20 APIs.', 'ABC Company']}])
        result = fill_explicit_skill_section(profile, 'Skills: Python, SQL\nWork Experience\nBuilt 20 APIs.')
        self.assertEqual([item for group in result.skills for item in group.items], ['Python', 'SQL'])

    def test_absent_skills_section_does_not_erase_existing_explicit_data(self):
        self.assertIsNone(explicit_skills('Used Python to build APIs.'))
        self.assertEqual(explicit_skills('Skills\nEducation'), [])

    def test_experience_tools_are_metadata_and_projects_use_one_nonduplicate_line(self):
        profile = MasterProfile(contact={}, experience=[{'company': 'ABC', 'job_title': 'Developer',
            'description': ['Built APIs with TensorFlow.'], 'technologies_used': ['TensorFlow', 'Docker']}],
            project=[{'project_name': 'Demo', 'description': ['Built APIs with Python.'],
                      'technologies': ['Python', 'Docker', 'PostgreSQL']}], education=[], involvement=[], skills=[])
        document = source_document(profile, 'fixture', language='vi')
        sections = {section.kind: section for section in document.sections}
        self.assertEqual([b.text for b in sections['experience'].entries[0].bullets], ['Built APIs with TensorFlow.'])
        bullets = sections['project'].entries[0].bullets
        self.assertEqual([b.text for b in bullets], ['Built APIs with Python.', 'Python, Docker, PostgreSQL'])
        self.assertEqual(bullets[1].source_refs, ['/project/0/technologies/0', '/project/0/technologies/1', '/project/0/technologies/2'])

    def test_company_mentioned_in_reference_does_not_hide_real_job(self):
        text = 'Người giới thiệu\nManager | ABC Company\n\nKinh nghiệm làm việc\nABC Company\nAI Engineer\n' + '\n'.join('Source bullet' for _ in range(20)) + '\nHọc vấn\nUniversity'
        span = _entry_span(text, 'ABC Company', ['ABC Company'], previous_line=True)
        self.assertIsNotNone(span)
        self.assertIn('AI Engineer', text[slice(*span)])
        self.assertEqual(text[slice(*span)].count('Source bullet'), 20)
        self.assertNotIn('University', text[slice(*span)])

    def test_omitted_sections_and_cross_section_bullets_are_reported(self):
        profile = MasterProfile(contact={}, experience=[{'company':'ABC', 'description':['Built APIs.']}],
                                project=[{'description':['Maintained 20 database tables.']}],
                                education=[], involvement=[], skills=[])
        warnings = validate_against_source(profile, 'Work Experience\nABC\n• Built APIs.\n• Maintained 20 database tables.\nAwards\nEmployee of the year')
        self.assertTrue(any('experience' in warning and '1 dòng' in warning for warning in warnings))
        self.assertTrue(any('awards' in warning and 'trống' in warning for warning in warnings))
