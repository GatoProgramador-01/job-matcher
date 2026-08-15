"""
Upload golden JSONL datasets to LangSmith.

Run once per dataset version:
    .venv/Scripts/python.exe evals/upload_datasets.py

Re-run after adding or correcting examples.
Requires LANGSMITH_API_KEY and LANGSMITH_TRACING=true in .env
"""
import json
import sys
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

from langsmith import Client

_ROOT = Path(__file__).parent.parent

DATASETS = {
    "job-matcher-extraction-v1": _ROOT / "evals" / "datasets" / "extraction_golden.jsonl",
    "job-matcher-ranking-v1":    _ROOT / "evals" / "datasets" / "ranking_golden.jsonl",
}


def upload() -> None:
    client = Client()
    existing = {d.name: d for d in client.list_datasets()}

    for name, path in DATASETS.items():
        lines = [l for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]
        examples = [json.loads(l) for l in lines]

        if name in existing:
            print(f"Dataset '{name}' already exists ({len(examples)} examples) -- skipping creation")
            print(f"  To replace, delete it in LangSmith UI first, then re-run this script")
            continue

        dataset = client.create_dataset(name)
        client.create_examples(
            inputs=[e["inputs"] for e in examples],
            outputs=[e["outputs"] for e in examples],
            dataset_id=dataset.id,
        )
        print(f"Created dataset '{name}' with {len(examples)} examples")
        print(f"  View at: https://smith.langchain.com/datasets/{dataset.id}")


if __name__ == "__main__":
    upload()
