# Backward-compat re-export — canonical location: domain.models
from .domain.models import (
    Job,
    ExtractedJob,
    ScoreBreakdown,
    ScoredJob,
    ProfileData,
    MatcherState,
)

__all__ = [
    "Job",
    "ExtractedJob",
    "ScoreBreakdown",
    "ScoredJob",
    "ProfileData",
    "MatcherState",
]
