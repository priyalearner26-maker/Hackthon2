"""Evaluate the approved-knowledge RAG pipeline with Ragas.

Run from the repository root:
    python scripts/evaluate_rag.py

The input JSONL contains user_input, reference, and reference_contexts fields.
The script retrieves contexts with the application retriever, asks the configured
Azure/OpenAI-compatible model for an answer, and writes scores to stdout.
"""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from backend.app.config import settings
from backend.knowledge.retriever import KnowledgeRetriever
from backend.orchestrator.supervisor import Supervisor


def load_samples(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def build_ragas_dataset(samples: list[dict[str, object]], retriever: KnowledgeRetriever):
    try:
        from ragas import EvaluationDataset, SingleTurnSample
    except ImportError as error:
        raise SystemExit(
            "Ragas is not available in this environment. "
            "Create a Python 3.11/3.12 evaluation environment and install requirements-eval.txt."
        ) from error

    rows = []
    supervisor = Supervisor()
    for sample in samples:
        question = str(sample["user_input"])
        chunks = retriever.search(question, top_k=5)
        response = supervisor.handle(
            session_id=f"ragas-eval-{len(rows)}",
            message=question,
            agent="document",
        )
        rows.append(
            SingleTurnSample(
                user_input=question,
                response=response,
                retrieved_contexts=[chunk.content for chunk in chunks],
                reference=str(sample["reference"]),
                reference_contexts=list(sample.get("reference_contexts", [])),
            )
        )
    return EvaluationDataset.from_samples(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate Nexa Bank RAG with Ragas")
    parser.add_argument(
        "--dataset",
        type=Path,
        default=Path("data/rag_eval_dataset.jsonl"),
        help="JSONL file with user_input, reference, and reference_contexts",
    )
    args = parser.parse_args()

    try:
        asyncio.get_event_loop()
    except RuntimeError:
        asyncio.set_event_loop(asyncio.new_event_loop())

    if not settings.llm_api_key or not settings.llm_model:
        raise SystemExit("LLM_API_KEY/OPENAI_API_KEY and LLM_MODEL are required for Ragas evaluation")

    from langchain_openai import ChatOpenAI
    try:
        from ragas import evaluate
        from ragas.metrics import AnswerCorrectness, ContextPrecision, ContextRecall, Faithfulness, ResponseRelevancy
    except ImportError as error:
        raise SystemExit(
            "Ragas dependencies are incomplete. Install requirements-eval.txt in Python 3.11/3.12."
        ) from error

    dataset = build_ragas_dataset(load_samples(args.dataset), KnowledgeRetriever())
    evaluator_llm = ChatOpenAI(
        api_key=settings.llm_api_key,
        base_url=(settings.openai_base_url or "https://api.openai.com/v1").rstrip("/"),
        model=settings.llm_model,
        max_completion_tokens=700,
    )
    result = evaluate(
        dataset=dataset,
        metrics=[ContextPrecision(), ContextRecall(), Faithfulness(), ResponseRelevancy(), AnswerCorrectness()],
        llm=evaluator_llm,
    )
    scores = json.loads(result.to_pandas().to_json(orient="records"))
    output = {"status": "completed", "dataset": str(args.dataset), "scores": scores}
    Path("data/rag_eval_results.json").write_text(json.dumps(output, indent=2), encoding="utf-8")
    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()