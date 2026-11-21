import unittest
from bs4 import BeautifulSoup

from ai.agents.cv_agent import source_document
from backend.app.schemas.profile import MasterProfile
from backend.app.services.cv_renderer import render_html
from backend.app.services.cv_templates import TEMPLATES


def project_profile():
    return MasterProfile(contact={'full_name':'Fixture Candidate'},experience=[],education=[],involvement=[],skills=[],project=[{
        'project_name':'A long project title for geographic data analysis and interactive maps',
        'role':'Developer','start_date':'2024','end_date':'2026',
        'description':['Built a map application with Python.','Added interactive charts.'],
        'technologies':['Python','FastAPI','React','PostgreSQL','LangGraph'],
        'github_url':'https://github.com/example/geographic-analysis',
    }])


class ProjectMetadataTests(unittest.TestCase):
    def test_all_layouts_show_stack_and_clickable_github_in_project_heading(self):
        document=source_document(project_profile(),'fixture',language='vi')
        for template in TEMPLATES:
            with self.subTest(template=template['id']):
                soup=BeautifulSoup(render_html(document,template['id']),'html.parser')
                header=soup.select_one('.project-header-line')
                self.assertIsNotNone(header)
                self.assertIn(document.sections[0].entries[0].title,header.get_text())
                self.assertIn('Python, FastAPI, React, PostgreSQL, LangGraph',header.get_text())
                self.assertEqual(header.find('a',string='GitHub')['href'],'https://github.com/example/geographic-analysis')
                self.assertNotIn('Python, FastAPI, React, PostgreSQL, LangGraph',[li.get_text(' ',strip=True) for li in soup.select('li')])
                self.assertIn('Built a map application with Python.',soup.get_text())
                self.assertIn('overflow-wrap:anywhere',soup.style.get_text()+''.join(s.get_text() for s in soup.find_all('style')))

    def test_legacy_layouts_share_the_same_project_header(self):
        document=source_document(project_profile(),'fixture')
        for template in ['ats','classic']:
            soup=BeautifulSoup(render_html(document,template,{'template_version':1}),'html.parser')
            self.assertEqual(len(soup.select('.project-header-line a')),1)

    def test_unsafe_repository_text_cannot_create_active_links(self):
        profile=project_profile();profile.project[0].github_url='javascript:alert(1)'
        soup=BeautifulSoup(render_html(source_document(profile,'fixture'),'classic'),'html.parser')
        self.assertIsNone(soup.select_one('.project-header-line a'))
        self.assertIn('GitHub: javascript:alert(1)',soup.get_text())
        self.assertFalse(soup.select('script'))

    def test_duplicate_url_is_shown_once_and_missing_metadata_has_no_separator(self):
        profile=project_profile();profile.project[0].project_url=profile.project[0].github_url
        soup=BeautifulSoup(render_html(source_document(profile,'fixture'),'classic'),'html.parser')
        self.assertEqual(len(soup.select('.project-header-line a')),1)
        profile.project[0].github_url=None;profile.project[0].project_url=None;profile.project[0].technologies=[]
        soup=BeautifulSoup(render_html(source_document(profile,'fixture'),'classic'),'html.parser')
        self.assertFalse(soup.select('.project-meta'))

    def test_chat_keeps_project_repository_separate_from_personal_github(self):
        from backend.app.services.assistant_routing import ChatDecision,expand_decision
        from backend.app.services.assistant_intake import apply_updates
        text='Công nghệ Python, React. GitHub: https://github.com/example/demo'
        decision=expand_decision(ChatDecision(intent='build_cv',updates=[
            dict(path='project.0.technologies',value=['Python','React']),
            dict(path='project.0.github_url',value='https://github.com/example/demo'),
        ]),text)
        intake,rejected=apply_updates(None,decision.updates,text)
        self.assertEqual(rejected,0)
        self.assertEqual(intake['profile']['project'][0]['github_url'],'https://github.com/example/demo')
        self.assertIsNone(intake['profile']['contact']['github'])
