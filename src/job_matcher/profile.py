import json
from pathlib import Path
from .models import ProfileData


def load_profile(path: str) -> ProfileData:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    criteria = data["job_search_criteria"]
    return ProfileData(
        preferred_keywords=criteria["preferred_keywords"],
        reject_keywords=criteria["reject_keywords"],
        target_seniority=criteria["target_seniority"],
        avoid_seniority=criteria["avoid_seniority"],
    )
