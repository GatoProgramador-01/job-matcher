import os
from pydantic import BaseModel
from langchain_openai import ChatOpenAI
from ..models import Job, ExtractedJob, MatcherState


class _JobExtraction(BaseModel):
    required_skills: list[str]
    seniority: str | None
    is_remote: bool
    latam_eligible: bool


_SYSTEM = (
    "You are a job posting analyzer. Given a job title and description, "
    "extract the required skills, inferred seniority level (junior/mid/senior/staff or null), "
    "whether the role is remote, and whether Latin American candidates are eligible. "
    "Return only the JSON fields — no commentary."
)


def _make_llm() -> ChatOpenAI:
    return ChatOpenAI(
        model="deepseek-chat",
        base_url="https://api.deepseek.com",
        api_key=os.environ["DEEPSEEK_API_KEY"],
        temperature=0,
    ).with_structured_output(_JobExtraction)


def _extract_one(job: Job, llm) -> ExtractedJob:
    prompt = f"Title: {job.title}\n\nDescription: {job.description[:2000]}"
    try:
        result: _JobExtraction = llm.invoke([
            {"role": "system", "content": _SYSTEM},
            {"role": "user", "content": prompt},
        ])
        return ExtractedJob(
            job=job,
            required_skills=result.required_skills,
            seniority=result.seniority,
            is_remote=result.is_remote,
            latam_eligible=result.latam_eligible,
        )
    except Exception:
        return ExtractedJob(job=job)


def extract_node(state: MatcherState) -> dict:
    llm = _make_llm()
    extracted = [_extract_one(job, llm) for job in state["filtered_jobs"]]
    return {"extracted_jobs": extracted}
