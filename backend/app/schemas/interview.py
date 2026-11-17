"""Versioned practice contracts; scores are feedback, never hiring decisions."""
from typing import Literal
from pydantic import Field
from backend.app.schemas.profile import StrictModel


class InterviewStart(StrictModel):
    cv_id: str = Field(pattern=r'^cv_[a-f0-9]{32}$')
    posting_id: str = Field(pattern=r'^posting_[a-f0-9]{24}$')
    language: Literal['vi','en'] = 'vi'
    question_count: int = Field(default=3,ge=2,le=8)
    event_id: str = Field(pattern=r'^[A-Za-z0-9_-]{1,128}$')


class InterviewAnswer(StrictModel):
    expected_version: int = Field(ge=1)
    event_id: str = Field(pattern=r'^[A-Za-z0-9_-]{1,128}$')
    answer: str = Field(min_length=1,max_length=6000)


class QuestionEvidence(StrictModel):
    source: Literal['cv','jd']
    quote: str = Field(min_length=1,max_length=600)


class PracticeQuestion(StrictModel):
    kind: Literal['technical','behavioral']
    text: str = Field(min_length=10,max_length=1400)
    evidence: list[QuestionEvidence] = Field(min_length=1,max_length=3)


class RubricItem(StrictModel):
    dimension: Literal['relevance','clarity','specificity','technical_accuracy']
    score: int | None = Field(ge=0,le=4)
    reason: str = Field(min_length=1,max_length=800)


class PracticeFeedback(StrictModel):
    rubric: list[RubricItem] = Field(min_length=4,max_length=4)
    strengths: list[str] = Field(max_length=3)
    improvements: list[str] = Field(min_length=1,max_length=3)
    answer_quotes: list[str] = Field(min_length=1,max_length=3)
    suggested_approach: str = Field(min_length=1,max_length=1400)


class PracticeTurn(StrictModel):
    question: PracticeQuestion | None
    feedback: PracticeFeedback | None


class QuestionPlan(StrictModel):
    kind: Literal['technical','behavioral']
    text: str = Field(min_length=10,max_length=1400)
    evidence_refs: list[str] = Field(min_length=1,max_length=3)


class InitialTurn(StrictModel):
    question: QuestionPlan


class NextTurn(StrictModel):
    question: QuestionPlan
    feedback: PracticeFeedback


class FinalTurn(StrictModel):
    feedback: PracticeFeedback
