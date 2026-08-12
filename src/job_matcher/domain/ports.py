from __future__ import annotations
from typing import Any, Protocol


class JobFetcher(Protocol):
    def fetch(self, query: str, limit: int) -> list[dict[str, Any]]: ...


class ExtractionCache(Protocol):
    def get_extraction(self, job_id: str) -> dict[str, Any] | None: ...
    def save_extraction(
        self,
        job_id: str,
        required_skills: list[str],
        seniority: str | None,
        is_remote: bool,
        latam_eligible: bool,
        tokens_used: int,
    ) -> bool: ...


class RawJobStore(Protocol):
    def save_raw_jobs(self, jobs: list[dict[str, Any]]) -> int: ...


class RunRecorder(Protocol):
    def record_pipeline_run(
        self,
        run_id: str,
        profile_name: str,
        jobs_fetched: int,
        jobs_filtered: int,
        jobs_extracted_new: int,
        jobs_cached_hits: int,
        token_stats: dict[str, Any],
    ) -> bool: ...
