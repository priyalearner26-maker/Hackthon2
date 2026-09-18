"""Aggregated, local-safe observability data for the engineering dashboard."""

import json
from pathlib import Path

from fastapi import APIRouter

from backend.app.config import settings
from backend.core.ai_controls import observability_snapshot

router = APIRouter(prefix="/observability", tags=["observability"])


@router.get("/summary")
def observability_summary() -> dict[str, object]:
    evaluation_path = Path("data/rag_eval_results.json")
    evaluation: dict[str, object] = {"status": "not_run", "scores": []}
    if evaluation_path.exists():
        try:
            evaluation = json.loads(evaluation_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            evaluation = {"status": "unavailable", "scores": []}

    return {
        "langsmith": {
            "enabled": bool(settings.langsmith_tracing and settings.langsmith_api_key),
            "project": settings.langsmith_project,
            "endpoint": settings.langsmith_endpoint,
            "content_tracing": settings.langsmith_trace_content,
        },
        "llm": {"provider": settings.llm_provider, "model": settings.llm_model},
        "evaluation": evaluation,
        **observability_snapshot(),
    }