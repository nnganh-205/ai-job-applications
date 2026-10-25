"""Human-controlled profile updates: answers, exact quotes and explicit approval."""

from typing import Literal

from pydantic import Field, model_validator

from backend.app.schemas.profile import MasterProfile, StrictModel


class UpdateStart(StrictModel):
    profile_id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,128}$")
    posting_id: str = Field(pattern=r"^posting_[a-f0-9]{24}$")


class SessionAction(StrictModel):
    action_id: str = Field(min_length=1, max_length=160)
    event_id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,128}$")
    decision: Literal["yes", "no", "skip", "approve", "reject", "continue", "finish", "message"]
    message: str = Field(default="", max_length=6000)
    target_section: Literal["project", "experience", "skills"] = "project"
    entry_id: str | None = Field(default=None, max_length=128)
    entry_name: str | None = Field(default=None, max_length=200)
    confirmed_skills: list[str] = Field(default_factory=list, max_length=20)
    profile: MasterProfile | None = None

    @model_validator(mode="after")
    def require_details(self):
        if self.decision in {"yes", "message"} and not self.message.strip():
            raise ValueError("Hãy mô tả thông tin thật để hệ thống giữ bằng chứng")
        return self


class GapQuestion(StrictModel):
    question: str = Field(min_length=5, max_length=1000)


class AnswerQuotes(StrictModel):
    quotes: list[str] = Field(default_factory=list, max_length=8)


class ProfileRevision(StrictModel):
    profile_id: str
    root_profile_id: str
    parent_profile_id: str | None = None
    session_id: str | None = None
    created_at: str
    changed_paths: list[str] = Field(default_factory=list)


class SessionView(StrictModel):
    session_id: str
    mode: Literal["update", "build"]
    status: str
    profile_id: str | None = None
    posting_id: str | None = None
    action_id: str | None = None
    question: str | None = None
    target: dict | None = None
    draft_profile: MasterProfile | None = None
    changed_paths: list[str] = Field(default_factory=list)
    messages: list[dict] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    matching: dict | None = None
    persistent_checkpoints: bool = False
