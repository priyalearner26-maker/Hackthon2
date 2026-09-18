"""Application entry point."""

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from backend.app.api.routes import chat, dashboard, documents, email, knowledge, observability
from backend.app.config import settings
from backend.app.middleware import RequestContextMiddleware, unhandled_exception_handler

app = FastAPI(title="Bank Employee AI Workspace", version="0.1.0")
app.add_middleware(RequestContextMiddleware)
app.add_middleware(
	CORSMiddleware,
	allow_origins=[settings.frontend_origin],
	allow_credentials=True,
	allow_methods=["*"],
	allow_headers=["*"],
)
app.add_exception_handler(Exception, unhandled_exception_handler)
app.include_router(chat.router, prefix="/api/v1")
app.include_router(dashboard.router, prefix="/api/v1")
app.include_router(email.router, prefix="/api/v1")
app.include_router(documents.router, prefix="/api/v1")
app.include_router(knowledge.router, prefix="/api/v1")
app.include_router(observability.router, prefix="/api/v1")


@app.get("/", tags=["system"])
def root() -> dict[str, str]:
	return {"message": "Bank Employee AI Workspace API"}


@app.get("/health", tags=["system"])
def health_check() -> dict[str, str]:
	return {"status": "ok"}
