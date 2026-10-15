from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Contact(StrictModel):
    full_name: str | None = None
    email: str | None = None
    phone: str | None = None
    location: str | None = None
    linkedin: str | None = None
    github: str | None = None
    website: str | None = None


class Experience(StrictModel):
    job_title: str | None = None
    company: str | None = None
    location: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    description: list[str] = Field(default_factory=list)


class Project(StrictModel):
    project_name: str | None = None
    role: str | None = None
    technologies: list[str] = Field(default_factory=list)
    start_date: str | None = None
    end_date: str | None = None
    description: list[str] = Field(default_factory=list)
    project_url: str | None = None


class Education(StrictModel):
    institution: str | None = None
    degree: str | None = None
    major: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    gpa: str | None = None
    details: list[str] = Field(default_factory=list)


class Involvement(StrictModel):
    organization: str | None = None
    role: str | None = None
    activity_name: str | None = None
    period: str | None = None
    description: list[str] = Field(default_factory=list)


class SkillGroup(StrictModel):
    group: str | None = None
    items: list[str] = Field(default_factory=list)


class MasterProfile(StrictModel):
    contact: Contact
    experience: list[Experience]
    project: list[Project]
    education: list[Education]
    involvement: list[Involvement]
    skills: list[SkillGroup]
    summary: str | None = None


class ExtractionResponse(StrictModel):
    thread_id: str
    status: Literal["pending_confirmation"]
    profile: MasterProfile
    warnings: list[str]


class ConfirmationRequest(StrictModel):
    profile: MasterProfile


class SavedProfileResponse(StrictModel):
    thread_id: str
    status: Literal["confirmed"]
    profile: MasterProfile
    warnings: list[str]

