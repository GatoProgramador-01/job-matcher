import os
from ..fetcher import fetch_jobs, load_cache, save_cache
from ..models import MatcherState


def fetch_node(state: MatcherState) -> dict:
    base_url = os.environ["HIRING_CAFE_URL"]
    raw = fetch_jobs(base_url)

    seen = load_cache()
    new_jobs = [j for j in raw if j["id"] not in seen]

    seen.update(j["id"] for j in new_jobs)
    save_cache(seen)

    return {"raw_jobs": new_jobs}
