"""Renderer-independent CV contracts, shared with training and frontend."""

from typing import Literal

from pydantic import Field

from backend.app.schemas.profile import Contact, StrictModel


class CVBullet(StrictModel):
    text: str = Field(min_length=1)
    source_refs: list[str] = Field(min_length=1)


class CVEntry(StrictModel):
    source_entry_id: str
    title: str
    subtitle: str | None = None
    period: str | None = None
    bullets: list[CVBullet] = Field(default_factory=list)


class CVSection(StrictModel):
    kind: Literal["experience", "project", "education", "involvement", "skills"]
    heading: str
    entries: list[CVEntry]


class CVDocument(StrictModel):
    schema_version: Literal[1] = 1
    source_profile_revision_id: str
    job_analysis_id: str | None = None
    language: Literal["vi", "en"]
    contact: Contact
    summary: CVBullet | None = None
    sections: list[CVSection]


class CVReviewItem(StrictModel):
    source_ref: str
    original_text: str
    proposed_text: str
    reason: str
    severity: Literal["info", "warning", "error"]


class CVReview(StrictModel):
    items: list[CVReviewItem]
    warnings: list[str] = Field(default_factory=list)


class CVPlan(StrictModel):
    selected_refs: list[str] = Field(max_length=150)
    review: CVReview


class CVStart(StrictModel):
    profile_id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,128}$")
    posting_id: str | None = Field(default=None, pattern=r"^posting_[a-f0-9]{24}$")
    mode: Literal["generate", "review"] = "generate"
    language: Literal["vi", "en"] = "en"


class CVApproval(StrictModel):
    decision: Literal["approve", "reject"]
    document: CVDocument | None = None
    template: Literal["ats", "classic"] = "ats"


class CVSession(StrictModel):
    session_id: str
    status: Literal["pending_approval", "confirmed", "cancelled"]
    document: CVDocument
    review: CVReview
    warnings: list[str]
    cv_id: str | None = None
    template: Literal["ats", "classic"] = "ats"
