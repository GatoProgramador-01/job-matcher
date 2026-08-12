"""
MongoDB persistence module for Job Matcher.

Handles storing raw jobs, LLM extraction cache, and pipeline run token metrics.
Uses local MongoDB or MONGODB_URI environment variable with graceful fallback.
"""
import os
import sys
from datetime import datetime, timezone
from typing import Any, Optional

try:
    import pymongo
    from pymongo.errors import PyMongoError
    _HAS_PYMONGO = True
except ImportError:
    _HAS_PYMONGO = False


class MongoStorage:
    def __init__(self, uri: Optional[str] = None, db_name: Optional[str] = None):
        self.enabled = False
        self.client = None
        self.db = None

        if not _HAS_PYMONGO:
            print("[mongo] pymongo not installed — MongoDB disabled", file=sys.stderr)
            return

        mongo_uri = uri or os.environ.get("MONGODB_URI", "mongodb://localhost:27017")
        mongo_db = db_name or os.environ.get("MONGODB_DB", "job_matcher")

        try:
            self.client = pymongo.MongoClient(mongo_uri, serverSelectionTimeoutMS=2000)
            # Test connection
            self.client.admin.command("ping")
            self.db = self.client[mongo_db]
            self.enabled = True
            self._ensure_indexes()
            print(f"[mongo] Connected to MongoDB ({mongo_db}) at {mongo_uri}", file=sys.stderr)
        except Exception as exc:
            print(f"[mongo] Connection failed ({exc}) — running without MongoDB cache", file=sys.stderr)
            self.enabled = False

    def _ensure_indexes(self) -> None:
        if not self.enabled or self.db is None:
            return
        try:
            self.db["raw_jobs"].create_index("id", unique=True)
            self.db["extractions"].create_index("job_id", unique=True)
            self.db["pipeline_runs"].create_index("timestamp")
        except Exception as exc:
            print(f"[mongo] Index creation error: {exc}", file=sys.stderr)

    # ── Raw Jobs ──────────────────────────────────────────────────────────────

    def save_raw_jobs(self, jobs: list[dict[str, Any]]) -> int:
        if not self.enabled or not jobs:
            return 0
        saved = 0
        coll = self.db["raw_jobs"]
        for j in jobs:
            try:
                j_doc = dict(j)
                j_doc["updated_at"] = datetime.now(timezone.utc)
                coll.update_one({"id": j["id"]}, {"$set": j_doc}, upsert=True)
                saved += 1
            except Exception:
                pass
        return saved

    # ── LLM Extraction Cache ──────────────────────────────────────────────────

    def get_extraction(self, job_id: str) -> Optional[dict[str, Any]]:
        if not self.enabled:
            return None
        try:
            doc = self.db["extractions"].find_one({"job_id": job_id})
            return doc
        except Exception:
            return None

    def save_extraction(
        self,
        job_id: str,
        required_skills: list[str],
        seniority: Optional[str],
        is_remote: bool,
        latam_eligible: bool,
        tokens_used: int = 0,
    ) -> bool:
        if not self.enabled:
            return False
        try:
            self.db["extractions"].update_one(
                {"job_id": job_id},
                {
                    "$set": {
                        "job_id": job_id,
                        "required_skills": required_skills,
                        "seniority": seniority,
                        "is_remote": is_remote,
                        "latam_eligible": latam_eligible,
                        "tokens_used": tokens_used,
                        "extracted_at": datetime.now(timezone.utc),
                    }
                },
                upsert=True,
            )
            return True
        except Exception as exc:
            print(f"[mongo] Failed to save extraction for {job_id}: {exc}", file=sys.stderr)
            return False

    # ── Pipeline Runs & Token Metrics ─────────────────────────────────────────

    def record_pipeline_run(
        self,
        run_id: str,
        profile_name: str,
        jobs_fetched: int,
        jobs_filtered: int,
        jobs_extracted_new: int,
        jobs_cached_hits: int,
        token_stats: dict[str, Any],
    ) -> bool:
        if not self.enabled:
            return False
        try:
            doc = {
                "run_id": run_id,
                "timestamp": datetime.now(timezone.utc),
                "profile_name": profile_name,
                "jobs_fetched": jobs_fetched,
                "jobs_filtered": jobs_filtered,
                "jobs_extracted_new": jobs_extracted_new,
                "jobs_cached_hits": jobs_cached_hits,
                "token_stats": token_stats,
            }
            self.db["pipeline_runs"].insert_one(doc)
            return True
        except Exception as exc:
            print(f"[mongo] Failed to record pipeline run: {exc}", file=sys.stderr)
            return False


# Singleton instance
mongo_db = MongoStorage()
