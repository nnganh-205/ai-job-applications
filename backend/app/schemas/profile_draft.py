"""Editable drafts are separate from immutable confirmed profiles."""
from pydantic import Field
from backend.app.schemas.profile import MasterProfile, StrictModel


class DraftStart(StrictModel):
    base_profile_id: str | None = Field(default=None, pattern=r'^[A-Za-z0-9_-]{1,128}$')


class DraftSave(StrictModel):
    expected_version: int = Field(ge=1)
    profile: MasterProfile


class DraftConfirm(StrictModel):
    expected_version: int = Field(ge=1)
    event_id: str = Field(pattern=r'^[A-Za-z0-9_-]{1,128}$')
