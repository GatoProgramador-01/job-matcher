import json
import os
import uuid
from pathlib import Path
from typing import AsyncGenerator

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from job_matcher.mongo import mongo_db
from job_matcher.pipeline import build_pipeline
from job_matcher.profile import load_profile

router = APIRouter()


class RunRequest(BaseModel):
    profile_path: str = Field(default="profile.json", max_length=500)


def _safe_profile_path(raw: str) -> Path:
    requested = Path(raw).resolve()
    base = Path(".").resolve()
    if not str(requested).startswith(str(base)):
        raise HTTPException(status_code=400, detail="Invalid profile path")
    if not requested.exists():
        raise HTTPException(status_code=404, detail="Profile not found")
    return requested


async def _stream_pipeline(profile_path: str) -> AsyncGenerator[str, None]:
    path = _safe_profile_path(profile_path)
    profile = load_profile(str(path))
    pipeline = build_pipeline()
    run_id = f"run_{uuid.uuid4().hex[:8]}"

    initial_state = {
        "profile": profile,
        "raw_jobs": [],
        "filtered_jobs": [],
        "extracted_jobs": [],
        "scored_jobs": [],
        "top_jobs": [],
        "output_format": "json",
        "token_stats": {},
    }

    try:
        for event in pipeline.stream(initial_state):
            node_name = next(iter(event))
            state = event[node_name]
            token_stats = state.get("token_stats") or {}

            yield f"data: {json.dumps({'node': node_name, 'token_stats': token_stats})}\n\n"

            if node_name == "rank":
                top = state.get("top_jobs", [])
                jobs_payload = [
                    {
                        "score": round(j.score, 1),
                        "title": j.job.title,
                        "company": j.job.company,
                        "posted_at": str(j.job.posted_at) if j.job.posted_at else None,
                        "apply_url": j.job.apply_url,
                        "skills": j.extracted.required_skills,
                        "seniority": j.extracted.seniority,
                    }
                    for j in top
                ]

                # Record completed run to MongoDB
                mongo_db.record_pipeline_run(
                    run_id=run_id,
                    profile_name=path.name,
                    jobs_fetched=len(state.get("raw_jobs", [])),
                    jobs_filtered=len(state.get("filtered_jobs", [])),
                    jobs_extracted_new=token_stats.get("cache_misses", 0),
                    jobs_cached_hits=token_stats.get("cache_hits", 0),
                    token_stats=token_stats,
                )

                yield f"data: {json.dumps({'done_node': node_name, 'jobs': jobs_payload, 'token_stats': token_stats})}\n\n"
            else:
                yield f"data: {json.dumps({'done_node': node_name, 'token_stats': token_stats})}\n\n"
    except Exception as exc:
        yield f"data: {json.dumps({'error': str(exc)})}\n\n"


@router.post("/run")
async def run_matcher(req: RunRequest) -> StreamingResponse:
    return StreamingResponse(
        _stream_pipeline(req.profile_path),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/profile")
def get_profile(profile_path: str = "profile.json") -> dict:
    path = _safe_profile_path(profile_path)
    profile = load_profile(str(path))
    return {
        "preferred_keywords": profile.preferred_keywords,
        "reject_keywords": profile.reject_keywords,
        "target_seniority": profile.target_seniority,
    }
