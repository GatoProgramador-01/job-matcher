"""
Fetch node — multi-source job listing retrieval.

Reads:   state["profile"]  (not used — fetch is profile-agnostic)
Writes:  state["raw_jobs"]    (list[dict] — raw job dicts from all sources)
         state["token_stats"] (empty TokenTracker — no LLM calls here)

Side effects:
  - HTTP GET to Remotive API (software-dev, devops-sysadmin, data categories)
  - HTTP GET to RemoteOK API
  - Writes MongoDB raw_jobs collection (upsert by id)
  - Updates local cache.json with seen job IDs (deduplication across runs)

Failure modes:
  - API unreachable: returns partial or empty list (no exception raised)
  - MongoDB down: save_raw_jobs() silently skips (MongoStorage.enabled=False)
"""
import os
from concurrent.futures import ThreadPoolExecutor
from ..infrastructure.hiring_cafe import fetch_jobs, fetch_remoteok, load_cache, save_cache
from ..domain.models import MatcherState
from ..infrastructure.mongo import mongo_db
from ..token_tracker import TokenTracker


def fetch_node(state: MatcherState) -> dict:
    base_url = os.environ.get("HIRING_CAFE_URL", "https://hiring.cafe")

    with ThreadPoolExecutor(max_workers=2) as pool:
        remotive_future = pool.submit(fetch_jobs, base_url, limit=100)
        remoteok_future = pool.submit(fetch_remoteok)
        remotive_jobs = remotive_future.result()
        remoteok_jobs = remoteok_future.result()

    raw = remotive_jobs + remoteok_jobs

    # Deduplicate by apply_url — first occurrence wins
    seen_urls: set[str] = set()
    deduped: list[dict] = []
    for job in raw:
        url = job.get("apply_url", "")
        if not url or url not in seen_urls:
            if url:
                seen_urls.add(url)
            deduped.append(job)

    mongo_db.save_raw_jobs(deduped)

    seen = load_cache()
    seen.update(j["id"] for j in deduped)
    save_cache(seen)

    tracker = TokenTracker()
    return {
        "raw_jobs": deduped,
        "token_stats": tracker.to_dict(),
    }
