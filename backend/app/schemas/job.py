from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


RequirementType = Literal["required", "preferred", "unspecified"]
Priority = Literal["high", "medium", "low"]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class RequirementItem(StrictModel):
    id: str | None = None
    name: str = Field(min_length=1)
    requirement_type: RequirementType
    evidence: str = Field(min_length=1)
    priority: Priority | None = None
    original_name: str | None = None


class ExperienceRequirement(StrictModel):
    id: str | None = None
    description: str = Field(min_length=1)
    minimum_years: float | None = Field(default=None, ge=0)
    requirement_type: RequirementType
    evidence: str = Field(min_length=1)
    priority: Priority | None = None


class EducationRequirement(StrictModel):
    id: str | None = None
    description: str = Field(min_length=1)
    requirement_type: RequirementType
    evidence: str = Field(min_length=1)
    priority: Priority | None = None


class RequirementGroup(StrictModel):
    id: str | None = None
    operator: Literal["all", "any"]
    members: list[str] = Field(min_length=2)
    requirement_ids: list[str] = Field(default_factory=list)
    requirement_type: RequirementType
    evidence: str = Field(min_length=1)


class ExtractedJobRequirements(StrictModel):
    job_title: str | None = Field(
        default=None,
        description="Advertised position title, copied from the JD; not a candidate title.",
    )
    company: str | None = Field(
        default=None,
        description="Hiring company explicitly named in the JD.",
    )
    location: str | None = Field(
        default=None,
        description="Work location explicitly named in the JD.",
    )
    employment_type: Literal["full-time", "part-time", "internship", "contract"] | None = Field(
        default=None,
        description="Employment type stated in the JD, normalized to the enum.",
    )
    salary: str | None = None
    job_summary: str | None = None
    unspecified_skills: list[RequirementItem] = Field(
        default_factory=list,
        description="Explicit skills whose mandatory/preferred status is not stated; do not promote one-of options to individually mandatory skills.",
    )
    requirement_groups: list[RequirementGroup] = Field(default_factory=list)
    certifications: list[RequirementItem] = Field(default_factory=list)
    languages: list[RequirementItem] = Field(default_factory=list)
    technical_requirements: list[RequirementItem] = Field(default_factory=list)
    required_skills: list[RequirementItem] = Field(
        default_factory=list,
        description="Mandatory technologies, tools, technical or soft skills.",
    )
    preferred_skills: list[RequirementItem] = Field(
        default_factory=list,
        description="Skills explicitly marked preferred, plus, bonus or nice-to-have.",
    )
    experience_requirements: list[ExperienceRequirement] = Field(
        default_factory=list,
        description="Experience requirements; minimum_years is null unless stated.",
    )
    education_requirements: list[EducationRequirement] = Field(
        default_factory=list,
        description="Degree, education level and major requirements.",
    )
    responsibilities: list[RequirementItem] = Field(
        default_factory=list,
        description="Tasks and duties the employee will perform.",
    )
    core_requirements: list[RequirementItem] = Field(
        default_factory=list,
        description=(
            "Only requirements explicitly emphasized as essential in the JD, with source evidence. "
            "May duplicate specific fields. Do not select an arbitrary number; leave empty if absent."
        ),
    )


class ExtractedSkills(StrictModel):
    skills: list[str]


class JobRequirements(ExtractedJobRequirements):
    job_description_raw: str = Field(min_length=1)


class JobAnalysisRequest(StrictModel):
    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        json_schema_extra={
            "examples": [{
                "source_url": "https://example.com/jobs/backend-developer"
            }]
        },
    )

    source_url: str | None = Field(default=None, max_length=2048)
    job_description_text: str | None = Field(default=None, max_length=60000)
    saved_job_id: str | None = Field(default=None, pattern=r"^[A-Za-z0-9_-]{1,128}$")

    @model_validator(mode="after")
    def require_one_source(self):
        values = [self.source_url, self.job_description_text, self.saved_job_id]
        if sum(bool(value and value.strip()) for value in values) != 1:
            raise ValueError("Chỉ cung cấp một trong source_url, job_description_text hoặc saved_job_id")
        return self


class JobAnalysisResponse(StrictModel):
    job_id: str
    status: Literal["completed", "review"]
    job_requirements: JobRequirements
    warnings: list[str]
    source_url: str | None = None
    job_description_raw: str
    analysis_version: str | None = None
    content_hash: str | None = None
    model: str | None = None

