import argparse
import json
import os
from dotenv import load_dotenv

from .profile import load_profile
from .pipeline import build_pipeline
from .infrastructure.mongo import mongo_db

load_dotenv()


def main():
    parser = argparse.ArgumentParser(description="Personal job matcher -- hiring.cafe")
    sub = parser.add_subparsers(dest="cmd", required=True)

    run_cmd = sub.add_parser("run", help="Fetch and rank today's jobs")
    run_cmd.add_argument("--json", action="store_true", help="Output as JSON")
    run_cmd.add_argument("--profile", default=os.environ.get("PROFILE_PATH", "profile.json"))

    sub.add_parser("cache-stats", help="Show MongoDB cache counts and last run token spend")

    args = parser.parse_args()

    if args.cmd == "run":
        _run(args)
    elif args.cmd == "cache-stats":
        _cache_stats()


def _run(args):
    profile = load_profile(args.profile)
    pipeline = build_pipeline()

    initial_state = {
        "profile": profile,
        "raw_jobs": [],
        "filtered_jobs": [],
        "extracted_jobs": [],
        "scored_jobs": [],
        "top_jobs": [],
        "output_format": "json" if args.json else "table",
    }
    pipeline.invoke(initial_state)


def _cache_stats():
    stats = mongo_db.cache_stats()
    if not stats.get("enabled"):
        print("MongoDB disabled — no cache stats available")
        return
    if "error" in stats:
        print(f"Error: {stats['error']}")
        return
    print(f"Extractions cached : {stats['extractions_cached']}")
    print(f"Raw jobs stored    : {stats['raw_jobs_stored']}")
    print(f"Pipeline runs      : {stats['pipeline_runs']}")
    if stats["last_run_tokens"]:
        print(f"Last run tokens    : {json.dumps(stats['last_run_tokens'], indent=2)}")


if __name__ == "__main__":
    main()
