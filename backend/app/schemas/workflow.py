"""Validated public contracts; these types do not execute future Agents."""

from typing import Literal

from pydantic import Field, model_validator

from backend.app.schemas.profile import MasterProfile, SourceEvidence, StrictModel


Intent = Literal["tailor", "build_profile", "analyze_jd", "match", "review", "generate"]


class RequirementAssessment(StrictModel):
    requirement_id: str
    label: str = ""
    dimension: str = ""
    source_field: str = ""
    is_core: bool = False
    counted_in_score: bool = True
    member_ids: list[str] = Field(default_factory=list)
    status: Literal["met", "partially_met", "unknown", "not_met"]
    evidence_refs: list[str] = Field(default_factory=list)
    explanation: str
    contribution: float = Field(ge=0, le=1)


class MatchResult(StrictModel):
    profile_revision_id: str
    job_analysis_id: str
    algorithm_version: str
    score: float | None = Field(default=None, ge=0, le=100)
    dimension_scores: dict[str, float] = Field(default_factory=dict)
    assessments: list[RequirementAssessment]
    strengths: list[str]
    gaps: list[str]
    warnings: list[str] = Field(default_factory=list)


class ProfilePatch(StrictModel):
    base_revision_id: str
    proposed_profile: MasterProfile
    changed_paths: list[str] = Field(min_length=1)
    evidence: list[SourceEvidence]


class PendingAction(StrictModel):
    id: str
    kind: Literal["answer_question", "confirm_profile", "approve_patch", "approve_cv"]
    message: str


class WorkflowResponse(StrictModel):
    thread_id: str
    intent: Intent
    status: Literal["running", "waiting", "completed", "failed", "cancelled"]
    pending_action: PendingAction | None = None
    profile_revision_id: str | None = None
    job_analysis_id: str | None = None
    cv_version_id: str | None = None
    warnings: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def waiting_requires_action(self):
        if (self.status == "waiting") != (self.pending_action is not None):
            raise ValueError("Only a waiting workflow must carry a pending action")
        return self
