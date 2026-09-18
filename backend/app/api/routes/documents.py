"""Document upload and analysis endpoints."""

from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, File, HTTPException, UploadFile

from backend.documents import analyze_document, summarize_with_langchain, validate_filename
from backend.knowledge.loaders import load_text
from backend.knowledge.retriever import KnowledgeRetriever

router = APIRouter(prefix="/documents", tags=["documents"])
UPLOAD_ROOT = Path("data/knowledge_base/uploads")
MAX_UPLOAD_BYTES = 15 * 1024 * 1024


@router.post("/upload")
async def upload_document(file: UploadFile = File(...)) -> dict:
    if not file.filename:
        raise HTTPException(status_code=400, detail="A filename is required")
    try:
        validate_filename(file.filename)
    except ValueError as exc:
        raise HTTPException(status_code=415, detail=str(exc)) from exc

    content = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="Document exceeds the 15 MB upload limit")

    safe_name = f"{uuid4().hex}_{Path(file.filename).name}"
    path = UPLOAD_ROOT / safe_name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    try:
        text = load_text(path)
        analysis = analyze_document(file.filename, text)
        analysis["summary"] = summarize_with_langchain(text, analysis["summary"])
        KnowledgeRetriever().rebuild_store()
        return {"status": "indexed", "document_id": path.stem, "analysis": analysis}
    except RuntimeError as exc:
        path.unlink(missing_ok=True)
        raise HTTPException(status_code=422, detail=str(exc)) from exc