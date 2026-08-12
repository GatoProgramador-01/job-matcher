import os
from ..fetcher import fetch_jobs, load_cache, save_cache
from ..models import MatcherState
from ..mongo import mongo_db
from ..token_tracker import TokenTracker


def fetch_node(state: MatcherState) -> dict:
    base_url = os.environ.get("HIRING_CAFE_URL", "https://hiring.cafe")
    raw = fetch_jobs(base_url, limit=100)

    # Persist raw jobs to MongoDB if enabled
    mongo_db.save_raw_jobs(raw)

    # Update local cache
    seen = load_cache()
    seen.update(j["id"] for j in raw)
    save_cache(seen)

    tracker = TokenTracker()
    return {
        "raw_jobs": raw,
        "token_stats": tracker.to_dict(),
    }

