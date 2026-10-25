import tempfile
import unittest
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

import httpx
import pymupdf
from docx import Document
from langgraph.types import Command
from pydantic import ValidationError

from backend.app.ai.agents.profile_agent import (
    fill_clear_missing_fields,
    fill_missing_job_titles,
    remove_contact_from_involvement,
    validate_against_source,
)
from backend.app.ai.graph import profile_workflow
from backend.app.ai.llm.ollama_client import (
    CONTEXT_LENGTH,
    TIMEOUT_SECONDS,
    OllamaError,
    clean_null_strings,
)
from backend.app.ai.llm.profile_extractor import request_profile
from backend.app.ai.prompts.profile_prompt import PROFILE_EXTRACTION_PROMPT
from backend.app.schemas.profile import MasterProfile
from backend.app.services.document_reader import DocumentReadError, read_cv
from backend.app.db.profile_repository import load_master_profile, save_master_profile


def empty_profile(**changes) -> MasterProfile:
    data = {
        "contact": {},
        "experience": [],
        "project": [],
        "education": [],
        "involvement": [],
        "skills": [],
        "summary": None,
    }
    data.update(changes)
    return MasterProfile.model_validate(data)


def make_docx(text: str) -> bytes:
    document = Document()
    for line in text.splitlines():
        document.add_paragraph(line)
    output = BytesIO()
    document.save(output)
    return output.getvalue()


class DocumentReaderTests(unittest.TestCase):
    def test_read_pdf_with_text(self):
        document = pymupdf.open()
        page = document.new_page()
        page.insert_text((72, 72), "Nguyen Van A - developer@example.com")
        content = document.tobytes()
        document.close()
        self.assertIn("developer@example.com", read_cv("resume.pdf", content))

    def test_read_docx_with_sections(self):
        text = read_cv("resume.docx", make_docx("SUMMARY\nBackend developer\nPROJECTS\nJob Search"))
        self.assertIn("SUMMARY", text)
        self.assertIn("Job Search", text)

    def test_scanned_pdf_requires_ocr(self):
        document = pymupdf.open()
        document.new_page()
        content = document.tobytes()
        document.close()
        with self.assertRaisesRegex(DocumentReadError, "OCR"):
            read_cv("scan.pdf", content)


class ProfileSchemaTests(unittest.TestCase):
    def test_missing_summary_and_experience_are_valid(self):
        profile = empty_profile()
        self.assertIsNone(profile.summary)
        self.assertEqual(profile.experience, [])

    def test_experience_project_involvement_and_contact(self):
        profile = empty_profile(
            contact={"full_name": "Nguyen Van A", "email": "a@example.com"},
            experience=[{"job_title": "Developer", "company": "ABC"}],
            project=[{"project_name": "Job Search"}],
            involvement=[{"organization": "AI Club", "role": "Member"}],
        )
        self.assertEqual(profile.experience[0].company, "ABC")
        self.assertEqual(profile.project[0].project_name, "Job Search")
        self.assertEqual(profile.involvement[0].organization, "AI Club")

    def test_missing_top_level_field_is_rejected(self):
        data = empty_profile().model_dump()
        del data["skills"]
        with self.assertRaises(ValidationError):
            MasterProfile.model_validate(data)

    def test_new_summary_is_flagged(self):
        profile = empty_profile(summary="New summary written by a model")
        warnings = validate_against_source(profile, "CV without a summary section")
        self.assertTrue(any("Summary" in warning for warning in warnings))

    def test_skill_not_in_resume_is_flagged(self):
        profile = empty_profile(skills=[{"group": "Languages", "items": ["Python"]}])
        warnings = validate_against_source(profile, "Skills: Java")
        self.assertTrue(any("skills[0].items[0]" in warning for warning in warnings))

    def test_clear_contact_fields_are_filled_from_vietnamese_cv(self):
        profile = empty_profile()
        text = "NGUYỄN VĂN AN\nEmail: an.nguyen@example.com\nĐiện thoại: +84 912 345 678"
        result = fill_clear_missing_fields(profile, text)
        self.assertEqual(result.contact.full_name, "NGUYỄN VĂN AN")
        self.assertEqual(result.contact.email, "an.nguyen@example.com")
        self.assertEqual(result.contact.phone, "+84 912 345 678")

    def test_gpa_is_filled_without_changing_its_format(self):
        profile = empty_profile(education=[{"institution": "Đại học ABC"}])
        result = fill_clear_missing_fields(
            profile,
            "Đại học ABC\nĐiểm trung bình: 8.25/10",
        )
        self.assertEqual(result.education[0].gpa, "8.25/10")

    def test_truncated_phone_and_wrong_gpa_are_replaced_from_source(self):
        profile = empty_profile(
            contact={"phone": "+84 912 ..."},
            education=[{"institution": "Đại học ABC", "gpa": "3.4/4"}],
        )
        text = "Điện thoại: +84 912 345 678\nĐại học ABC\nGPA: 3.45/4.0"
        result = fill_clear_missing_fields(profile, text)
        self.assertEqual(result.contact.phone, "+84 912 345 678")
        self.assertEqual(result.education[0].gpa, "3.45/4.0")

    def test_missing_contact_and_gpa_are_not_invented(self):
        profile = empty_profile(education=[{"institution": "Đại học ABC"}])
        result = fill_clear_missing_fields(profile, "Đại học ABC")
        self.assertIsNone(result.contact.phone)
        self.assertIsNone(result.education[0].gpa)

    @patch("backend.app.ai.agents.profile_agent.extract_missing_job_titles")
    def test_missing_job_title_is_filled_when_it_exists_in_cv(self, mock_extract):
        mock_extract.return_value = {0: "Backend Developer"}
        profile = empty_profile(
            experience=[{"company": "Công ty ABC", "job_title": None}],
        )
        result = fill_missing_job_titles(
            profile,
            "Backend Developer | Công ty ABC | 01/2023 - Hiện tại",
        )
        self.assertEqual(result.experience[0].job_title, "Backend Developer")

    @patch("backend.app.ai.agents.profile_agent.extract_missing_job_titles")
    def test_unsupported_job_title_is_rejected(self, mock_extract):
        mock_extract.return_value = {0: "Senior Backend Developer"}
        profile = empty_profile(experience=[{"company": "Công ty ABC"}])
        result = fill_missing_job_titles(profile, "Backend Developer | Công ty ABC")
        self.assertIsNone(result.experience[0].job_title)

    def test_contact_entry_is_removed_from_involvement(self):
        profile = empty_profile(
            contact={
                "full_name": "Nguyễn Văn An",
                "email": "an@example.com",
            },
            involvement=[
                {
                    "organization": "Thông tin liên hệ",
                    "description": ["an@example.com"],
                },
                {
                    "organization": "Câu lạc bộ AI",
                    "role": "Thành viên",
                },
            ],
        )
        result = remove_contact_from_involvement(profile)
        self.assertEqual(len(result.involvement), 1)
        self.assertEqual(result.involvement[0].organization, "Câu lạc bộ AI")

    def test_candidate_name_is_not_an_involvement_organization(self):
        profile = empty_profile(
            contact={"full_name": "Nguyễn Văn An"},
            involvement=[{"organization": "Nguyễn Văn An"}],
        )
        result = remove_contact_from_involvement(profile)
        self.assertEqual(result.involvement, [])

    @patch("backend.app.ai.agents.profile_agent.extract_missing_job_titles")
    def test_supported_job_title_does_not_call_second_inference(self, mock_extract):
        profile = empty_profile(
            experience=[{"company": "Công ty ABC", "job_title": "Backend Developer"}],
        )
        result = fill_missing_job_titles(profile, "Backend Developer | Công ty ABC")
        self.assertEqual(result.experience[0].job_title, "Backend Developer")
        mock_extract.assert_not_called()


class OllamaTests(unittest.TestCase):
    @patch("backend.app.ai.llm.ollama_client.httpx.post")
    def test_ollama_not_running(self, mock_post):
        mock_post.side_effect = httpx.ConnectError("connection refused")
        with self.assertRaisesRegex(OllamaError, "Không kết nối"):
            request_profile("Resume text")

    @patch("backend.app.ai.llm.ollama_client.httpx.post")
    def test_ollama_timeout_has_correct_message(self, mock_post):
        mock_post.side_effect = httpx.ReadTimeout("timed out")
        with self.assertRaisesRegex(OllamaError, "quá 600 giây"):
            request_profile("Resume text")

    def test_long_context_and_vietnamese_are_configured(self):
        self.assertEqual(TIMEOUT_SECONDS, 600)
        self.assertEqual(CONTEXT_LENGTH, 16_384)
        self.assertIn("Vietnamese", PROFILE_EXTRACTION_PROMPT)
        self.assertIn("Kinh nghiệm", PROFILE_EXTRACTION_PROMPT)
        self.assertIn("Do not translate", PROFILE_EXTRACTION_PROMPT)
        self.assertIn("job_title", PROFILE_EXTRACTION_PROMPT)
        self.assertIn("project's technology line", PROFILE_EXTRACTION_PROMPT)
        self.assertIn("Điểm trung bình", PROFILE_EXTRACTION_PROMPT)

    def test_string_null_is_cleaned(self):
        cleaned = clean_null_strings({"degree": "null", "skills": ["Python", "N/A"]})
        self.assertIsNone(cleaned["degree"])
        self.assertEqual(cleaned["skills"], ["Python", None])


class StorageAndGraphTests(unittest.TestCase):
    def test_profile_is_not_saved_before_confirmation(self):
        with tempfile.TemporaryDirectory() as directory:
            storage_dir = Path(directory)
            self.assertIsNone(load_master_profile("thread1", storage_dir))
            save_master_profile("thread1", empty_profile(), storage_dir)
            self.assertIsNotNone(load_master_profile("thread1", storage_dir))

    def test_unknown_thread_cannot_be_confirmed(self):
        with self.assertRaisesRegex(ValueError, "Không tìm thấy"):
            profile_workflow.confirm_extraction("unknown-thread", empty_profile())

    def test_langgraph_resumes_the_same_thread(self):
        profile = empty_profile(contact={"full_name": "Nguyen Van A"})
        saved = {}

        def fake_extract(_resume_text):
            return profile

        def fake_save(thread_id, confirmed_profile, **metadata):
            saved[thread_id] = confirmed_profile

        with (
            patch.object(profile_workflow, "extract_profile", fake_extract),
            patch.object(profile_workflow, "save_master_profile", fake_save),
        ):
            graph = profile_workflow.build_profile_graph()
            config = {"configurable": {"thread_id": "resume-thread"}}
            graph.invoke(
                {
                    "thread_id": "resume-thread",
                    "filename": "resume.docx",
                    "file_bytes": make_docx("Nguyen Van A"),
                },
                config=config,
            )
            self.assertNotIn("resume-thread", saved)
            result = graph.invoke(Command(resume=profile.model_dump()), config=config)
            self.assertEqual(result["status"], "confirmed")
            self.assertEqual(saved["resume-thread"].contact.full_name, "Nguyen Van A")


if __name__ == "__main__":
    unittest.main()
