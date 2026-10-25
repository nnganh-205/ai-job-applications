import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.ai.agents.jd_agent import (
    analyze_job_description,
    build_skill_items,
    extract_requirement_section,
    extract_responsibility_section,
    normalize_requirements,
    validate_evidence,
)
from backend.app.ai.graph import jd_workflow
from backend.app.ai.llm.ollama_client import (
    OllamaConnectionError,
    OllamaSchemaError,
    request_structured,
)
from backend.app.schemas.job import (
    ExtractedJobRequirements,
    ExtractedSkills,
    JobRequirements,
    RequirementItem,
)
from backend.app.services.job_fetcher import (
    JobFetchError,
    UnsafeJobUrl,
    extract_job_text,
    fetch_job_content,
    validate_public_url,
)
from backend.app.db.job_repository import load_job_analysis, save_job_analysis


def empty_requirements(**changes) -> JobRequirements:
    data = {
        "job_title": None,
        "company": None,
        "location": None,
        "employment_type": None,
        "required_skills": [],
        "preferred_skills": [],
        "experience_requirements": [],
        "education_requirements": [],
        "responsibilities": [],
        "core_requirements": [],
        "job_description_raw": "Backend Developer. Python is required for this role.",
    }
    data.update(changes)
    return JobRequirements.model_validate(data)


class JobFetcherTests(unittest.TestCase):
    @patch("backend.app.services.job_fetcher.socket.getaddrinfo")
    def test_public_job_url_is_valid(self, mock_dns):
        mock_dns.return_value = [(2, 1, 6, "", ("93.184.216.34", 0))]
        validate_public_url("https://jobs.example.com/backend")

    def test_private_url_is_rejected(self):
        with self.assertRaises(UnsafeJobUrl):
            validate_public_url("http://127.0.0.1:8000/private")

    def test_jobposting_json_ld(self):
        job = {
            "@context": "https://schema.org",
            "@type": "JobPosting",
            "title": "Backend Developer",
            "hiringOrganization": {"name": "ABC"},
            "description": "<p>Python is required. Build backend APIs.</p>",
        }
        html = f'<script type="application/ld+json">{json.dumps(job)}</script>'
        text = extract_job_text(html)
        self.assertIn("Backend Developer", text)
        self.assertIn("Python is required.", text)

    def test_normal_html_page(self):
        html = "<html><main><h1>Data Analyst</h1><p>Required: SQL and Excel.</p></main></html>"
        text = extract_job_text(html)
        self.assertIn("Required: SQL and Excel.", text)

    @patch("backend.app.services.job_fetcher.validate_public_url", return_value=["93.184.216.34"])
    def test_fetch_job_url(self, _mock_validate):
        transport = httpx.MockTransport(
            lambda request: httpx.Response(
                200,
                text="<main><h1>QA Engineer</h1><p>Testing experience is required.</p></main>",
                headers={"content-type": "text/html; charset=utf-8"},
                request=request,
            )
        )
        with httpx.Client(transport=transport) as client:
            text, final_url = fetch_job_content("https://jobs.example.com/qa", client)
        self.assertIn("Testing experience", text)
        self.assertEqual(final_url, "https://jobs.example.com/qa")

    @patch("backend.app.services.job_fetcher.validate_public_url", return_value=["93.184.216.34"])
    def test_unreachable_page(self, _mock_validate):
        def fail(request):
            raise httpx.ConnectError("failed", request=request)

        with httpx.Client(transport=httpx.MockTransport(fail)) as client:
            with self.assertRaises(JobFetchError):
                fetch_job_content("https://jobs.example.com/missing", client)


class JobAgentTests(unittest.TestCase):
    def test_missing_experience_years_remain_null(self):
        requirements = empty_requirements(
            experience_requirements=[{
                "description": "Backend development experience",
                "minimum_years": None,
                "requirement_type": "required",
                "evidence": "Python is required for this role.",
            }]
        )
        self.assertIsNone(requirements.experience_requirements[0].minimum_years)

    def test_explicit_experience_years_are_extracted_from_evidence(self):
        requirements = empty_requirements(
            experience_requirements=[{
                "description": "Backend experience",
                "minimum_years": None,
                "requirement_type": "required",
                "evidence": "At least 2 years of backend development experience.",
            }],
            job_description_raw="At least 2 years of backend development experience.",
        )
        result, warnings = normalize_requirements(requirements)
        self.assertEqual(result.experience_requirements[0].minimum_years, 2.0)
        self.assertEqual(warnings, [])

    def test_required_preferred_and_alias_normalization(self):
        requirements = empty_requirements(
            required_skills=[{
                "name": "Python",
                "requirement_type": "required",
                "evidence": "Python is required for this role.",
            }],
            preferred_skills=[{
                "name": "torch",
                "requirement_type": "preferred",
                "evidence": "Torch is preferred.",
            }],
            job_description_raw="Python is required for this role. Torch is preferred.",
        )
        result, warnings = normalize_requirements(requirements)
        self.assertEqual(result.required_skills[0].requirement_type, "required")
        self.assertEqual(result.preferred_skills[0].name, "PyTorch")
        self.assertEqual(result.preferred_skills[0].original_name, "torch")
        self.assertEqual(warnings, [])

    def test_invalid_evidence_requires_review(self):
        requirements = empty_requirements(
            required_skills=[{
                "name": "Kubernetes",
                "requirement_type": "required",
                "evidence": "Kubernetes is required.",
            }]
        )
        warnings = validate_evidence(requirements)
        self.assertTrue(any("evidence không xuất hiện" in warning for warning in warnings))

    def test_skill_not_stated_in_jd_requires_review(self):
        requirements = empty_requirements(
            required_skills=[{
                "name": "Kubernetes",
                "requirement_type": "required",
                "evidence": "Python is required for this role.",
            }]
        )
        warnings = validate_evidence(requirements)
        self.assertEqual(len(warnings), 1)
        self.assertIn("tên kỹ năng", warnings[0])

    def test_vietnamese_requirement_section_and_skill_mapping(self):
        raw_text = """Mô tả công việc
Xây dựng AI agent.
Yêu cầu ứng viên
Có khả năng lập trình Python và làm việc với API.
Điểm cộng: Kinh nghiệm với n8n.
Quyền lợi
Lương cạnh tranh."""
        requirement_text = extract_requirement_section(raw_text)
        items, warnings = build_skill_items(
            ["Python", "Có khả năng lập trình JavaScript", "API", "n8n"],
            requirement_text.replace("Python và", "Python hoặc JavaScript và"),
        )
        self.assertEqual(warnings, [])
        self.assertEqual(
            [(item.name, item.requirement_type) for item in items],
            [
                ("Python", "required"),
                ("JavaScript", "required"),
                ("API", "required"),
                ("n8n", "preferred"),
            ],
        )

    @patch("backend.app.ai.agents.jd_agent.request_structured")
    def test_empty_skill_lists_use_focused_extraction(self, mock_request):
        mock_request.side_effect = [
            ExtractedJobRequirements(job_title="AI Engineer"),
            ExtractedSkills(skills=["Python", "n8n"]),
            ExtractedSkills(skills=["n8n"]),
        ]
        result, warnings = analyze_job_description("""AI Engineer
Yêu cầu ứng viên
Có khả năng lập trình Python.
Điểm cộng: Kinh nghiệm với n8n.
Quyền lợi
Lương cạnh tranh.""")
        self.assertEqual([item.name for item in result.required_skills], ["Python"])
        self.assertEqual([item.name for item in result.preferred_skills], ["n8n"])
        self.assertEqual(warnings, [])

    @patch("backend.app.ai.agents.jd_agent.request_structured")
    def test_english_sections_are_classified_separately(self, mock_request):
        raw_text = """AI Engineer Intern
Responsibilities:
Build APIs using Python and FastAPI.
ReactJS knowledge is a plus.
Your Skills and Experience
Requirements:
Bachelor’s degree in Computer Science or related field.
Having basic knowledge of
NLP (Natural Language Processing)
and
Computer Vision
is an advantage.
Experience working with FastAPI or similar backend frameworks.
Basic experience with SQL and MongoDB for data management.
What We Offer:
Work with modern Software Engineering projects."""
        mock_request.side_effect = [
            ExtractedJobRequirements(job_title="AI Engineer Intern"),
            ExtractedSkills(skills=[
                "NLP",
                "Natural Language Processing",
                "Computer Vision",
                "FastAPI",
                "SQL",
                "MongoDB",
                "ReactJS",
                "Engineering",
            ]),
            ExtractedSkills(skills=["NLP", "Computer Vision", "ReactJS"]),
        ]
        result, warnings = analyze_job_description(raw_text)

        self.assertNotIn("Engineering", [item.name for item in result.required_skills])
        self.assertEqual(
            [item.name for item in result.preferred_skills],
            ["NLP (Natural Language Processing)", "Computer Vision", "ReactJS"],
        )
        self.assertEqual(len(result.education_requirements), 1)
        self.assertEqual(len(result.experience_requirements), 2)
        self.assertEqual(len(result.responsibilities), 2)
        self.assertNotIn("What We Offer", extract_requirement_section(raw_text))
        self.assertNotIn("Requirements", extract_responsibility_section(raw_text))
        self.assertTrue(any("Engineering" in warning for warning in warnings))

    def test_normalization_does_not_add_requirements(self):
        requirements = empty_requirements()
        result, _warnings = normalize_requirements(requirements)
        self.assertEqual(result.required_skills, [])
        self.assertEqual(result.preferred_skills, [])

    @patch("backend.app.ai.agents.jd_agent.request_structured")
    def test_valid_jd_text_is_analyzed(self, mock_request):
        mock_request.return_value = ExtractedJobRequirements(
            job_title="Backend Developer",
            required_skills=[RequirementItem(
                name="Python",
                requirement_type="required",
                evidence="Python is required.",
            )],
        )
        result, warnings = analyze_job_description(
            "Backend Developer. Python is required. Build and maintain APIs."
        )
        self.assertEqual(result.job_title, "Backend Developer")
        self.assertEqual(warnings, [])

    @patch("backend.app.ai.agents.jd_agent.request_structured")
    def test_invalid_schema_is_retried_once(self, mock_request):
        mock_request.side_effect = [
            OllamaSchemaError("invalid schema"),
            ExtractedJobRequirements(job_title="Backend Developer"),
        ]
        result, _warnings = analyze_job_description(
            "Backend Developer. Build and maintain Python APIs for the product."
        )
        self.assertEqual(result.job_title, "Backend Developer")
        self.assertEqual(mock_request.call_count, 2)

    @patch("backend.app.ai.graph.jd_workflow.analyze_job_description")
    def test_jd_graph_runs_without_profile_agent(self, mock_analyze):
        requirements = empty_requirements()
        mock_analyze.return_value = (requirements, [])
        state = jd_workflow.run_jd_analysis(
            job_description_text=requirements.job_description_raw,
        )
        self.assertEqual(state["status"], "completed")
        self.assertIn("job_requirements", state)

    @patch("backend.app.ai.llm.ollama_client.httpx.post")
    def test_ollama_not_running(self, mock_post):
        mock_post.side_effect = httpx.ConnectError("connection refused")
        with self.assertRaises(OllamaConnectionError):
            request_structured(
                [{"role": "user", "content": "Analyze this JD"}],
                ExtractedJobRequirements,
            )

    def test_saved_job_can_be_loaded_without_fetching_url(self):
        with tempfile.TemporaryDirectory() as directory:
            response = save_job_analysis(
                empty_requirements(),
                warnings=[],
                source_url="https://jobs.example.com/1",
                storage_dir=Path(directory),
            )
            loaded = load_job_analysis(response.job_id, Path(directory))
            self.assertEqual(loaded.job_id, response.job_id)
            self.assertEqual(loaded.job_requirements.job_description_raw, response.job_description_raw)
            saved = json.loads(
                (Path(directory) / f"{response.job_id}.json").read_text(encoding="utf-8")
            )
            self.assertNotIn("job_description_raw", saved["job_requirements"])


class JobApiTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_unsafe_url_returns_http_400(self):
        response = self.client.post(
            "/api/jobs/analyze",
            json={"source_url": "http://127.0.0.1:8000/private"},
        )
        self.assertEqual(response.status_code, 400)

    def test_missing_saved_job_returns_http_404(self):
        response = self.client.post(
            "/api/jobs/analyze",
            json={"saved_job_id": "missing-job"},
        )
        self.assertEqual(response.status_code, 404)

    def test_multiple_sources_are_rejected(self):
        response = self.client.post(
            "/api/jobs/analyze",
            json={
                "source_url": "https://jobs.example.com/1",
                "job_description_text": "A sufficiently long job description for testing.",
            },
        )
        self.assertEqual(response.status_code, 422)


if __name__ == "__main__":
    unittest.main()
