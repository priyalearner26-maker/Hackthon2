from pathlib import Path

from backend.documents import analyze_document
from backend.knowledge.loaders import load_text


def test_document_analysis_extracts_summary_actions_and_keywords() -> None:
    result = analyze_document(
        "policy.md",
        "Customer verification policy. Employees must complete two identity checks. "
        "Review the account before approval.",
    )

    assert result["filename"] == "policy.md"
    assert result["word_count"] > 0
    assert "Customer verification policy." in result["summary"]
    assert result["summary"].startswith("- ")
    assert len(result["action_items"]) == 2
    assert "verification" in result["keywords"]


def test_document_analysis_summary_is_capped_to_250_words() -> None:
    long_text = " ".join([
        "Customer verification policy requires two identity checks before account access.",
        "Employees must confirm the customer identity using approved documentation and validate the account holder details.",
        "The process applies to new onboarding, sensitive transactions, and account updates with elevated risk indicators.",
        "The compliance team reviews all exceptions and escalation cases before approval."
    ] * 12)

    result = analyze_document("policy.md", long_text)

    assert len(result["summary"].split()) <= 250
    assert result["summary"].strip()


def test_load_text_supports_plain_text_documents(tmp_path: Path) -> None:
    document = tmp_path / "notes.txt"
    document.write_text("Review the payment flow before approval.", encoding="utf-8")

    assert load_text(document) == "Review the payment flow before approval."