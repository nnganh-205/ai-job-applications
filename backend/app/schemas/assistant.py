"""Thin intent routing over the existing agents; attachment context is immutable."""
from typing import Literal
from pydantic import Field, model_validator
from backend.app.schemas.profile import StrictModel

Intent = Literal['review_cv','tailor_cv','evaluate','update_profile','find_jobs','clarify','advice','build_cv','prepare_cv']


class AssistantStart(StrictModel):
    profile_id: str | None = Field(default=None,pattern=r'^[A-Za-z0-9_-]{1,128}$')
    cv_id: str | None = Field(default=None,pattern=r'^cv_[a-f0-9]{32}$')
    posting_id: str | None = Field(default=None,pattern=r'^posting_[a-f0-9]{24}$')
    language: Literal['vi','en'] = 'vi'
    event_id: str = Field(pattern=r'^[A-Za-z0-9_-]{1,128}$')

    @model_validator(mode='after')
    def one_source(self):
        if self.profile_id and self.cv_id:raise ValueError('Chọn hồ sơ hoặc CV, không đồng thời')
        return self


class AssistantMessage(StrictModel):
    expected_version: int = Field(ge=1)
    event_id: str = Field(pattern=r'^[A-Za-z0-9_-]{1,128}$')
    text: str = Field(default='',max_length=4000)
    intent: Intent | None = None

    @model_validator(mode='after')
    def content(self):
        if not self.text.strip() and not self.intent:raise ValueError('Nhập yêu cầu hoặc chọn tác vụ')
        return self


class ProfilePatch(StrictModel):
    section: Literal['contact','experience','project','education','involvement','skills','summary','target_role']
    field: str = Field(default='',max_length=60)
    index: int | None = Field(default=None,ge=0,le=30)
    operation: Literal['set','append','remove_entry'] = 'set'
    value: str | list[str] | bool | None = None
    evidence: str = Field(min_length=1,max_length=1500)


class IntakeSignal(StrictModel):
    kind: Literal['not_available','skip','unknown','explain','navigate','resume','wording','accept_wording','more_entries','section_complete','accept_polish','write_bullets']
    section: Literal['contact','target_role','education','experience','project','skills','involvement','summary']
    evidence: str = Field(min_length=1,max_length=1500)


class IntentDecision(StrictModel):
    intent: Intent
    clarification: str = Field(default='',max_length=500)
    reply: str = Field(default='',max_length=3000)
    intake_signal: IntakeSignal | None = None
    updates: list[ProfilePatch] = Field(default_factory=list,max_length=24)
