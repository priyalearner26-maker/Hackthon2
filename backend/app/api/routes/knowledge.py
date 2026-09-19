"""Approved knowledge search endpoints."""

from fastapi import APIRouter, HTTPException
import httpx
from pydantic import BaseModel, Field

from backend.app.config import settings
from backend.agents.jira_confluence_agent import JiraConfluenceAgent
from backend.knowledge.loaders import ingest_confluence_page
from backend.knowledge.retriever import KnowledgeRetriever

router = APIRouter(prefix="/knowledge", tags=["knowledge"])


class KnowledgeSearchRequest(BaseModel):
    query: str = Field(min_length=1)
    top_k: int = Field(default=5, ge=1, le=20)
    metadata_filter: dict[str, str] | None = None


class ConfluenceIngestRequest(BaseModel):
    page_url: str = Field(min_length=1)


class ConfluencePageCreateRequest(BaseModel):
    title: str = Field(min_length=1)
    content: str = Field(min_length=1)


@router.post("/search")
def search_knowledge(request: KnowledgeSearchRequest) -> dict[str, object]:
    chunks = KnowledgeRetriever().search(
        request.query,
        top_k=request.top_k,
        metadata_filter=request.metadata_filter,
    )
    return {
        "query": request.query,
        "results": [
            {
                "citation": chunk.citation,
                "source": chunk.source,
                "content": chunk.content,
                "score": chunk.score,
                "page": chunk.page,
                "metadata": chunk.metadata,
            }
            for chunk in chunks
        ],
    }


@router.post("/confluence/ingest")
def ingest_knowledge_from_confluence(request: ConfluenceIngestRequest) -> dict[str, object]:
    try:
        path = ingest_confluence_page(
            request.page_url,
            base_url=settings.confluence_base_url or settings.jira_base_url,
            email=settings.jira_email,
            api_token=settings.jira_api_token,
        )
        chunks = KnowledgeRetriever().rebuild_store()
    except (ValueError, OSError, httpx.HTTPError) as error:
        raise HTTPException(status_code=400, detail=str(error)) from error

    return {"status": "indexed", "source": str(path), "chunks": len(chunks)}


@router.post("/confluence/pages")
def create_confluence_page(request: ConfluencePageCreateRequest) -> dict[str, str]:
    result = JiraConfluenceAgent()._write_confluence_page("create", request.title.strip(), request.content.strip())
    if not result.startswith("Confluence page created successfully:"):
        raise HTTPException(status_code=502, detail=result)
    page_url = result.split("Open page: ", 1)[-1].strip()
    return {"status": "created", "message": result, "url": page_url}
