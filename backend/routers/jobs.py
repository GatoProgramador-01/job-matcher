import asyncio
import json
import os
import queue as q_module
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

    progress_q: q_module.SimpleQueue = q_module.SimpleQueue()
    pipeline_states: dict = {}
    error_holder: list[str] = []

    initial_state = {
        "profile": profile,
        "raw_jobs": [],
        "filtered_jobs": [],
        "extracted_jobs": [],
        "scored_jobs": [],
        "top_jobs": [],
        "output_format": "json",
        "token_stats": {},
        "progress_queue": progress_q,
    }

    def _run_pipeline() -> None:
        try:
            for event in pipeline.stream(initial_state):
                node_name = next(iter(event))
                state = event[node_name]
                pipeline_states[node_name] = state
                progress_q.put({"_type": "node_done", "_node": node_name})
        except Exception as exc:
            error_holder.append(str(exc))
        finally:
            progress_q.put({"_type": "__sentinel__"})

    loop = asyncio.get_event_loop()
    pipeline_task = loop.run_in_executor(None, _run_pipeline)

    try:
        while True:
            # Drain queue without blocking the event loop
            msg = await loop.run_in_executor(None, progress_q.get)

            if msg["_type"] == "job_progress":
                yield f"data: {json.dumps({'type': 'job_progress', 'index': msg['index'], 'total': msg['total'], 'title': msg['title'], 'skills': msg['skills'], 'tokens': msg['tokens'], 'cost': msg['cost'], 'cached': msg['cached']})}\n\n"

            elif msg["_type"] == "node_start":
                yield f"data: {json.dumps({'node': msg['_node'], 'total': msg.get('total', 0)})}\n\n"

            elif msg["_type"] == "node_done":
                node_name = msg["_node"]
                state = pipeline_states.get(node_name, {})
                token_stats = state.get("token_stats") or {}

                # Emit done_node event (existing format)
                if node_name == "rank":
                    top = state.get("top_jobs", [])
                    jobs_payload = [
                        {
                            "score": round(j.score, 1),
                            "score_breakdown": {
                                "stack": round(j.breakdown.stack, 1),
                                "seniority": round(j.breakdown.seniority, 1),
                                "ai_bonus": round(j.breakdown.ai_bonus, 1),
                                "recency": round(j.breakdown.recency, 1),
                            } if j.breakdown else None,
                            "title": j.job.title,
                            "company": j.job.company,
                            "posted_at": str(j.job.posted_at) if j.job.posted_at else None,
                            "apply_url": j.job.apply_url,
                            "skills": j.extracted.required_skills,
                            "seniority": j.extracted.seniority,
                            "description": j.job.description,
                        }
                        for j in top
                    ]

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

            elif msg["_type"] == "__sentinel__":
                if error_holder:
                    yield f"data: {json.dumps({'error': error_holder[0]})}\n\n"
                break

    finally:
        await pipeline_task


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
