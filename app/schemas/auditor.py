from datetime import date, datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class RuleType(StrEnum):
    FINANCIAL_LIMIT = "FINANCIAL_LIMIT"
    DEADLINE = "DEADLINE"
    PERCENTAGE = "PERCENTAGE"
    OBLIGATION = "OBLIGATION"
    PROHIBITION = "PROHIBITION"
    VALIDITY = "VALIDITY"


class AlertKind(StrEnum):
    POSSIBLE_CONTRADICTION = "POSSIBLE_CONTRADICTION"
    RELEVANT_CHANGE = "RELEVANT_CHANGE"
    POSSIBLE_OUTDATED = "POSSIBLE_OUTDATED"
    NEEDS_CLARIFICATION = "NEEDS_CLARIFICATION"


class ReviewState(StrEnum):
    PENDING_REVIEW = "PENDING_REVIEW"
    CONFIRMED = "CONFIRMED"
    FALSE_POSITIVE = "FALSE_POSITIVE"
    RESOLVED = "RESOLVED"


class RuleEvidence(BaseModel):
    document_id: int = Field(gt=0)
    version: int = Field(gt=0)
    section_index: int = Field(ge=0)
    page: int | None = None
    sheet: str | None = None
    location: str | None = None
    start: int = Field(ge=0)
    end: int = Field(gt=0)
    excerpt: str = Field(min_length=1, max_length=1800)

    @model_validator(mode="after")
    def validate_span(self):
        if self.end - self.start != len(self.excerpt):
            raise ValueError("Os limites precisam corresponder ao trecho de origem.")
        return self


class CorporateRule(BaseModel):
    kind: RuleType
    subject: str = Field(min_length=1, max_length=240)
    target: str | None = Field(default=None, max_length=240)
    action: str = Field(min_length=1, max_length=400)
    department: str | None = None
    audience: str | None = None
    responsible: str | None = None
    condition: str | None = None
    exception: str | None = None
    policy_id: str | None = None
    value: str | None = None
    unit: str | None = None
    constraint: Literal["minimum", "maximum", "exact"] | None = None
    valid_from: date | None = None
    valid_until: date | None = None
    uncertainty: list[str] = Field(default_factory=list)
    evidence: RuleEvidence


class RunCreate(BaseModel):
    document_id: int = Field(gt=0)
    previous_document_id: int | None = Field(default=None, gt=0)


class RunRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    document_id: int
    status: str
    stage: str
    progress: int
    outcome: str | None
    error: str | None
    configuration: dict
    created_at: datetime


class AlertDocument(BaseModel):
    id: int
    name: str
    version: int


class ReviewRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    state: ReviewState
    justification: str
    created_at: datetime


class AlertRead(BaseModel):
    id: int
    kind: AlertKind
    state: ReviewState
    subject: str
    explanation: str
    documents: list[AlertDocument]
    evidence: list[CorporateRule]
    historical: bool
    detected_at: datetime


class AlertDetail(AlertRead):
    reviews: list[ReviewRead]


class AlertPage(BaseModel):
    items: list[AlertRead]
    total: int


class ReviewCreate(BaseModel):
    state: ReviewState
    justification: str = Field(min_length=3, max_length=1000)

    @field_validator("justification", mode="before")
    @classmethod
    def strip_justification(cls, value):
        return value.strip() if isinstance(value, str) else value
