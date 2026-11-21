from backend.app.schemas.templates import TemplateID
"""Library drafts/version wrapper v2; CVDocument/CVPlan v1 stay compatible."""
from typing import Literal
from pydantic import Field,model_validator
from backend.app.schemas.profile import StrictModel
from backend.app.schemas.cv import CVDocument


class Presentation(StrictModel):
    template: TemplateID = 'ats'
    template_version: Literal[1,2,3] = 2
    color: str = Field(default='#2457d6',pattern=r'^#[a-fA-F0-9]{6}$')
    photo_asset_id: str | None = Field(default=None,pattern=r'^asset_[a-f0-9]{64}$')
    font: Literal['sans','serif'] = 'sans'
    font_size: float = Field(default=10,ge=9,le=12)
    line_height: float = Field(default=1.4,ge=1.2,le=1.7)


class ResumeStart(StrictModel):
    profile_id: str | None = Field(default=None,pattern=r'^[A-Za-z0-9_-]{1,128}$')
    session_id: str | None = Field(default=None,pattern=r'^[a-f0-9]{32}$')
    refine_form: bool = False
    language: Literal['vi','en'] = 'vi'
    title: str = Field(default='CV của tôi',min_length=1,max_length=120)
    presentation: Presentation = Field(default_factory=Presentation)

    @model_validator(mode='after')
    def one_source(self):
        if bool(self.profile_id)==bool(self.session_id):raise ValueError('Chọn hồ sơ hoặc phiên CV')
        if self.refine_form and not self.profile_id:
            raise ValueError('Tinh chỉnh form cần hồ sơ nguồn')
        return self


class ResumeSave(StrictModel):
    expected_version: int = Field(ge=1)
    title: str = Field(min_length=1,max_length=120)
    document: CVDocument
    presentation: Presentation


class ResumePublish(StrictModel):
    expected_version: int = Field(ge=1)
    event_id: str = Field(pattern=r'^[A-Za-z0-9_-]{1,128}$')


class ResumeEditStart(StrictModel):
    expected_version: int = Field(ge=1)


class ResumeEditComplete(StrictModel):
    draft_id: str = Field(pattern=r'^draft_[a-f0-9]{32}$')
    expected_version: int = Field(ge=1)
    event_id: str = Field(pattern=r'^[A-Za-z0-9_-]{1,128}$')


class ResumeRestore(StrictModel):
    expected_version: int = Field(ge=1)
    target_version: int = Field(ge=1)
    event_id: str = Field(pattern=r'^[A-Za-z0-9_-]{1,128}$')
    editing_draft_version: int | None = Field(default=None,ge=1)
