from typing import Literal

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Contact(StrictModel):
    full_name: str | None = None
    email: str | None = Field(default=None, validation_alias=AliasChoices("email", "email_address"))
    phone: str | None = Field(default=None, validation_alias=AliasChoices("phone", "phone_number"))
    location: str | None = None
    linkedin: str | None = Field(default=None, validation_alias=AliasChoices("linkedin", "linkedin_url"))
    github: str | None = Field(default=None, validation_alias=AliasChoices("github", "github_url"))
    website: str | None = Field(default=None, validation_alias=AliasChoices("website", "personal_website"))
    portfolio_url: str | None = None
    country: str | None = None
    city: str | None = None
    state_or_province: str | None = None


class Experience(StrictModel):
    id: str | None = None
    job_title: str | None = None
    role: str | None = None
    company: str | None = None
    employment_type: str | None = None
    location: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    is_current: bool | None = None
    description: list[str] = Field(default_factory=list)
    responsibilities: list[str] = Field(default_factory=list)
    achievements: list[str] = Field(default_factory=list)
    technologies_used: list[str] = Field(default_factory=list)
    original_bullets: list[str] = Field(default_factory=list)


class Project(StrictModel):
    id: str | None = None
    project_name: str | None = None
    role: str | None = None
    project_type: str | None = None
    technologies: list[str] = Field(default_factory=list)
    start_date: str | None = None
    end_date: str | None = None
    description: list[str] = Field(default_factory=list)
    objectives: list[str] = Field(default_factory=list)
    responsibilities: list[str] = Field(default_factory=list)
    contributions: list[str] = Field(default_factory=list)
    outcomes: list[str] = Field(default_factory=list)
    original_bullets: list[str] = Field(default_factory=list)
    github_url: str | None = None
    demo_url: str | None = None
    project_url: str | None = None


class Education(StrictModel):
    id: str | None = None
    institution: str | None = None
    degree: str | None = None
    field_of_study: str | None = None
    major: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    graduation_date: str | None = None
    gpa: str | None = None
    gpa_scale: str | None = None
    details: list[str] = Field(default_factory=list)
    academic_achievements: list[str] = Field(default_factory=list)
    relevant_coursework: list[str] = Field(default_factory=list)
    original_description: str | None = None


class Involvement(StrictModel):
    id: str | None = None
    organization: str | None = None
    role: str | None = None
    activity_name: str | None = None
    activity_type: str | None = None
    period: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    description: list[str] = Field(default_factory=list)
    responsibilities: list[str] = Field(default_factory=list)
    achievements: list[str] = Field(default_factory=list)


class SkillGroup(StrictModel):
    id: str | None = None
    group: str | None = None
    items: list[str] = Field(default_factory=list)
    normalized_items: list[str] = Field(default_factory=list)


class MasterProfile(StrictModel):
    contact: Contact
    experience: list[Experience]
    project: list[Project]
    education: list[Education]
    involvement: list[Involvement]
    skills: list[SkillGroup]
    summary: str | None = None


class SourceEvidence(StrictModel):
    """An exact text span, not proof of semantic attribution or real-world truth."""

    field_path: str
    source_id: str
    origin: Literal["document", "user_confirmation"] = "document"
    quote: str = Field(min_length=1)
    start: int | None = Field(default=None, ge=0)
    end: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def validate_span(self):
        if (self.start is None) != (self.end is None):
            raise ValueError("Both span offsets are required together")
        if self.start is not None and self.end - self.start != len(self.quote):
            raise ValueError("Span length must equal quote length")
        return self


class ExtractionResponse(StrictModel):
    thread_id: str
    status: Literal["pending_confirmation"]
    profile: MasterProfile
    warnings: list[str]
    schema_version: int = 2
    evidence: list[SourceEvidence] = Field(default_factory=list)


class ConfirmationRequest(StrictModel):
    profile: MasterProfile


class SavedProfileResponse(StrictModel):
    thread_id: str
    status: Literal["confirmed"]
    profile: MasterProfile
    warnings: list[str]
    schema_version: int = 2
    evidence: list[SourceEvidence] = Field(default_factory=list)


class StoredProfile(StrictModel):
    schema_version: Literal[2] = 2
    profile: MasterProfile
    evidence: list[SourceEvidence] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    source_text: str | None = None
    source_filename: str | None = None
    root_profile_id: str | None = None
    parent_profile_id: str | None = None

