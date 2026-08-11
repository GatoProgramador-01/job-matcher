from __future__ import annotations
from datetime import date, datetime, timezone
from typing import Any, Literal
from pydantic import BaseModel, Field
from typing_extensions import TypedDict


class Job(BaseModel):
    id: str
    title: str
    company: str
    location: str | None = None
    remote: bool = False
    description: str = ""
    apply_url: str
    source: str = ""
    posted_at: date | None = None
    fetched_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ExtractedJob(BaseModel):
    job: Job
    required_skills: list[str] = Field(default_factory=list)
    seniority: str | None = None
    is_remote: bool = False
    latam_eligible: bool = False


class ScoredJob(BaseModel):
    job: Job
    extracted: ExtractedJob
    score: float
    discard_reason: str | None = None


class ProfileData(BaseModel):
    preferred_keywords: list[str]
    reject_keywords: list[str]
    target_seniority: list[str]
    avoid_seniority: list[str]


class MatcherState(TypedDict):
    profile: ProfileData
    raw_jobs: list[dict[str, Any]]
    filtered_jobs: list[Job]
    extracted_jobs: list[ExtractedJob]
    scored_jobs: list[ScoredJob]
    top_jobs: list[ScoredJob]
    output_format: Literal["table", "json"]
