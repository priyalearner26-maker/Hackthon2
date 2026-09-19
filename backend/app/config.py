"""Environment-backed application settings."""

from dataclasses import dataclass
import os
from pathlib import Path

from dotenv import load_dotenv


load_dotenv(Path(__file__).resolve().parents[2] / ".env")


def _env_value(name: str, default: str = "", fallback: str | None = None) -> str:
    value = os.getenv(name, "").strip()
    if value:
        return value
    return fallback if fallback is not None else default


@dataclass(frozen=True)
class Settings:
    app_env: str = os.getenv("APP_ENV", "development")
    frontend_origin: str = os.getenv("FRONTEND_ORIGIN", "http://localhost:3000")
    llm_provider: str = _env_value("LLM_PROVIDER", default="openai")
    llm_model: str = _env_value("LLM_MODEL", default="gpt-5.6-luna")
    llm_api_key: str = _env_value("LLM_API_KEY", fallback=_env_value("OPENAI_API_KEY"))
    openai_base_url: str = _env_value("OPENAI_BASE_URL")
    openai_api_key: str = _env_value("OPENAI_API_KEY")
    openai_embedding_model: str = os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-large")
    openai_embedding_dimension: int = int(os.getenv("OPENAI_EMBEDDING_DIMENSION", "3072"))
    ollama_base_url: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    ollama_model: str = os.getenv("OLLAMA_MODEL", "llama3.2:3b")
    langsmith_tracing: bool = os.getenv("LANGCHAIN_TRACING_V2", "false").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    langsmith_api_key: str = os.getenv("LANGCHAIN_API_KEY", "")
    langsmith_project: str = os.getenv("LANGCHAIN_PROJECT", "bank-employee-ai")
    langsmith_endpoint: str = os.getenv("LANGCHAIN_ENDPOINT", "https://api.smith.langchain.com")
    langsmith_trace_content: bool = os.getenv("LANGSMITH_TRACE_CONTENT", "false").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    vector_store_backend: str = os.getenv("VECTOR_STORE_BACKEND", "chroma")
    vector_store_path: str = os.getenv("VECTOR_STORE_PATH", "data/vector_store")
    vector_collection: str = os.getenv("VECTOR_COLLECTION", "banking_knowledge")
    database_url: str = os.getenv("DATABASE_URL", "")
    jira_base_url: str = os.getenv("JIRA_BASE_URL", "")
    confluence_base_url: str = os.getenv("CONFLUENCE_BASE_URL", "")
    confluence_space_key: str = os.getenv("CONFLUENCE_SPACE_KEY", "")
    jira_email: str = os.getenv("JIRA_EMAIL", "")
    jira_api_token: str = os.getenv("JIRA_API_TOKEN", "")
    jira_project_key: str = os.getenv("JIRA_PROJECT_KEY", "")
    ourtool_base_url: str = os.getenv("OURTOOL_BASE_URL", "")
    ourtool_api_key: str = os.getenv("OURTOOL_API_KEY", "")
    azure_search_endpoint: str = os.getenv("AZURE_SEARCH_ENDPOINT", "")
    azure_search_index: str = os.getenv("AZURE_SEARCH_INDEX", "")
    azure_search_key: str = os.getenv("AZURE_SEARCH_KEY", "")
    graph_client_id: str = os.getenv("GRAPH_CLIENT_ID", "")
    graph_tenant_id: str = os.getenv("GRAPH_TENANT_ID", "common")
    graph_scopes: str = os.getenv("GRAPH_SCOPES", "Calendars.ReadWrite User.Read")
    graph_mail_scopes: str = os.getenv("GRAPH_MAIL_SCOPES", "Mail.Read Mail.ReadWrite Mail.Send User.Read")
    mail_provider: str = os.getenv("MAIL_PROVIDER", "outlook").strip().lower()
    mail_important_senders: str = os.getenv("MAIL_IMPORTANT_SENDERS", "")
    graph_token_cache_path: str = os.getenv("GRAPH_TOKEN_CACHE_PATH", "data/graph_token_cache.json")
    graph_timezone: str = os.getenv("GRAPH_TIMEZONE", "UTC")
    allow_outlook_fallback: bool = os.getenv("ALLOW_OUTLOOK_FALLBACK", "true").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


settings = Settings()
