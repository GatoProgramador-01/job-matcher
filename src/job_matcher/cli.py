import argparse
import os
from dotenv import load_dotenv

load_dotenv()


def main():
    parser = argparse.ArgumentParser(description="Personal job matcher -- hiring.cafe")
    sub = parser.add_subparsers(dest="cmd", required=True)

    run_cmd = sub.add_parser("run", help="Fetch and rank today's jobs")
    run_cmd.add_argument("--json", action="store_true", help="Output as JSON")
    run_cmd.add_argument("--profile", default=os.environ.get("PROFILE_PATH", "profile.json"))
    args = parser.parse_args()

    if args.cmd == "run":
        _run(args)


def _run(args):
    from .profile import load_profile
    from .pipeline import build_pipeline

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


if __name__ == "__main__":
    main()
