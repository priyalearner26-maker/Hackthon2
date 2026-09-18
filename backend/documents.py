"""Document upload and deterministic analysis services."""

from collections import Counter
from pathlib import Path
import re
from typing import Any

from backend.app.config import settings
from backend.knowledge.loaders import SUPPORTED_SUFFIXES, load_text


SUMMARY_PROMPT = """You are a document summarization assistant for Nexa Bank.
Summarize the document for a bank employee.
Return exactly 10 concise bullet points, one per line.
Start every line with '- '.
Prioritize purpose, dates, attendees, decisions, progress, risks, blockers, metrics, owners, and next steps.
Do not add a title, introduction, conclusion, markdown code fence, or bullets with sub-items.
Use only information present in the document. If fewer than 10 distinct facts exist, use concise facts from the document without inventing details.

Document:
{document}
"""


def analyze_document(filename: str, text: str) -> dict[str, Any]:
    normalized = re.sub(r"\s+", " ", text).strip()
    sentences = [part.strip() for part in re.split(r"(?<=[.!?])\s+", normalized) if part.strip()]
    action_terms = ("must", "should", "need to", "required", "review", "complete", "submit", "send", "approve", "owner")
    actions = [sentence for sentence in sentences if any(term in sentence.lower() for term in action_terms)][:8]
    headings = re.findall(r"(?:^|\n)\s*(?:#{1,6}\s*)?([A-Z][A-Za-z0-9 /&_-]{3,60})\s*(?::|$)", text, re.MULTILINE)
    words = re.findall(r"[A-Za-z][A-Za-z0-9'-]+", normalized.lower())
    keywords = [word for word, _ in Counter(words).most_common(10) if len(word) > 3]

    summary_sentences = []
    for sentence in sentences:
        if len(" ".join(summary_sentences + [sentence]).split()) > 250:
            break
        if len(summary_sentences) == 10:
            break
        summary_sentences.append(sentence)

    summary = "\n".join(f"- {sentence}" for sentence in summary_sentences).strip() or "- No readable text was found."

    return {
        "filename": filename,
        "characters": len(text),
        "word_count": len(words),
        "summary": summary,
        "headings": list(dict.fromkeys(headings))[:12],
        "action_items": actions,
        "keywords": keywords,
        "text": text,
    }


def summarize_with_langchain(text: str, fallback: str) -> str:
    if not text.strip() or not settings.llm_api_key or not settings.llm_model:
        return fallback

    try:
        from langchain_core.output_parsers import StrOutputParser
        from langchain_core.prompts import ChatPromptTemplate
        from langchain_openai import ChatOpenAI

        prompt = ChatPromptTemplate.from_template(SUMMARY_PROMPT)
        model = ChatOpenAI(
            api_key=settings.llm_api_key,
            base_url=(settings.openai_base_url or "https://api.openai.com/v1").rstrip("/"),
            model=settings.llm_model,
            max_tokens=700,
        )
        chain = prompt | model | StrOutputParser()
        response = chain.invoke({"document": text[:12000]})
        bullets = [
            re.sub(r"^\s*(?:[-*]|\d+[.)])\s*", "", line).strip()
            for line in str(response).splitlines()
            if re.sub(r"^\s*(?:[-*]|\d+[.)])\s*", "", line).strip()
        ][:10]
        if len(bullets) < 10:
            return fallback
        return "\n".join(f"- {bullet}" for bullet in bullets)
    except Exception:
        return fallback


def validate_filename(filename: str) -> None:
    suffix = Path(filename).suffix.lower()
    if suffix not in SUPPORTED_SUFFIXES:
        supported = ", ".join(sorted(SUPPORTED_SUFFIXES))
        raise ValueError(f"Unsupported document type. Supported types: {supported}")