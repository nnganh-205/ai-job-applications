"""Small source-neutral contracts for the local recruitment workspace."""

from typing import Literal
from urllib.parse import urlsplit

from pydantic import Field, field_validator, model_validator

from backend.app.schemas.job import JobAnalysisResponse
from backend.app.schemas.matching import MatchResponse
from backend.app.schemas.profile import MasterProfile, StrictModel


class JobPosting(StrictModel):
    posting_id: str = Field(pattern=r"^posting_[a-f0-9]{24}$")
    title: str
    company: str | None = None
    location: str | None = None
    employment_type: str | None = None
    workplace_type: str | None = None
    salary: str | None = None
    description: str = Field(min_length=1, max_length=60000)
    source_name: str
    source_board: str | None = None
    external_id: str
    source_url: str | None = None
    apply_url: str | None = None
    fetched_at: str | None = None
    imported_at: str
    source_created_at: str | None = None
    content_hash: str = ""
    saved: bool = False
    legacy_analysis_id: str | None = None
    import_method: Literal["fetch", "text"] | None = None
    expires_at: str | None = None
    source_updated_at: str | None = None
    location_restrictions: list[str] = Field(default_factory=list)
    timezone_restrictions: list[str] = Field(default_factory=list)

    @field_validator("source_url", "apply_url")
    @classmethod
    def safe_link(cls, value):
        if value is not None:
            parsed = urlsplit(value)
            if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
                raise ValueError("URL nguồn phải là HTTP(S), không chứa thông tin đăng nhập")
        return value


class JobImportRequest(StrictModel):
    source_url: str | None = Field(default=None, max_length=2048)
    job_description_text: str | None = Field(default=None, min_length=30, max_length=60000)

    @field_validator("source_url")
    @classmethod
    def safe_source_url(cls, value):
        return JobPosting.safe_link(value)

    @model_validator(mode="after")
    def require_source(self):
        if not self.source_url and not (self.job_description_text and self.job_description_text.strip()):
            raise ValueError("Cung cấp URL hoặc JD text; có thể kèm URL nguồn khi dán JD")
        return self


class EvaluateRequest(StrictModel):
    profile_id: str | None = Field(default=None, pattern=r"^[A-Za-z0-9_-]{1,128}$")


class SavedJobRequest(StrictModel):
    saved: bool


class DashboardEvaluation(StrictModel):
    status: Literal["completed", "needs_profile", "insufficient_data", "needs_review"]
    job: JobPosting
    analysis: JobAnalysisResponse
    profile_id: str | None = None
    profile: MasterProfile | None = None
    matching: MatchResponse | None = None
    analysis_version: str
    model: str
    analysis_cached: bool
    matching_cached: bool = False
    warnings: list[str] = Field(default_factory=list)
