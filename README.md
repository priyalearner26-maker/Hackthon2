# Bank Employee AI Workspace

A bank employee workspace with a Next.js frontend, FastAPI backend, LangGraph request routing, live mailbox/calendar integrations, Jira and Confluence workflows, document analysis, approved-knowledge retrieval, and AskBank general assistance.

## Project layout

- `frontend/`: employee chat and dashboard UI
- `backend/`: FastAPI API, LangGraph supervisor, specialist agents, integrations, and RAG
- `data/`: source documents and vector-index artifacts
- `tests/`: backend unit and integration tests
- `docs/`: architecture and API notes
- `generate_architecture_diagram.py`: source for `architecture_diagram.png` and `architecture_diagram.svg`

## Technology stack

- **Frontend**: Next.js App Router, React, TypeScript, `lucide-react`, and CSS with responsive workspace layouts.
- **Backend API**: Python 3.13, FastAPI, Pydantic, Uvicorn, HTTPX, and `python-dotenv` configuration.
- **Orchestration**: LangGraph supervisor with specialist agents for MailMate, MeetMate, Jira/Confluence, Document Analyzer, and AskBank.
- **AI providers**: OpenAI-compatible chat and embedding APIs, with Ollama supported for local chat inference.
- **Knowledge and RAG**: document loaders, ChromaDB persistent storage, FAISS CPU cosine search, NumPy, and lexical retrieval fallback.
- **Mailbox and calendar**: Classic Outlook desktop COM through `pywin32`, Microsoft Graph through MSAL, and a local JSON calendar fallback.
- **Jira and Confluence**: Atlassian REST APIs through HTTPX, optional `atlassian-python-api`, and optional LangChain Confluence loading.
- **Document processing**: `pypdf`, `python-docx`, `openpyxl`, `python-pptx`, Pillow, and Tesseract OCR through `pytesseract`.
- **Testing and quality**: pytest and Ruff configuration through `pyproject.toml`.
- **Infrastructure**: Docker Compose with backend, frontend, PostgreSQL, and Redis services. PostgreSQL and Redis are provisioned for the workspace stack; current knowledge artifacts are stored locally in the `data/` directory.

## Current capabilities

- **MailMate**: unread mailbox loading/search, email selection, AI summaries, action extraction, new email drafts, reply drafts, copy/edit, and send through Classic Outlook or Microsoft Graph.
- **MeetMate**: upcoming calendar reads, meeting creation, local calendar fallback, and Microsoft Teams launching.
- **JiraPilot**: JQL issue search, story analysis, and task/story creation.
- **Confluence Coach**: page search, page retrieval, page creation/update, and knowledge-base ingestion.
- **Document Analyzer**: upload and analyze PDF, Word, Excel, PowerPoint, text, JSON, HTML, and image files.
- **Knowledge Hub**: approved-document retrieval with ChromaDB/FAISS when embeddings are configured and lexical fallback otherwise.
- **AskBank**: general Q&A through OpenAI-compatible APIs or Ollama.

## Development

Keep secrets in `.env` and use `.env.example` as the shared configuration contract. The current implementation has request IDs, CORS, and stable error responses, but authentication, RBAC, persistent chat sessions, rate limiting, and audit storage are not yet active.

## Local development

Install backend dependencies and start the API:

```powershell
python -m pip install -r backend/requirements.txt
python -m uvicorn backend.app.main:app --reload --port 8000
```

Start the frontend in another terminal:

```powershell
cd frontend
npm install
npm run dev
```

Open `http://localhost:3000`. The frontend defaults to `http://localhost:8000/api/v1`; set `NEXT_PUBLIC_API_BASE_URL` when the backend uses another port, for example `http://localhost:8001/api/v1`.

Health check: `http://localhost:8000/health`.

## Run with Docker Compose

Copy `.env.example` to `.env`, then start the local services:

```bash
docker compose up --build
```

- Frontend: `http://localhost:3000`
- Backend API: `http://localhost:8000`
- PostgreSQL: `localhost:5432`
- Redis: `localhost:6379`

Azure AI Search is optional and configured through `.env`. The current Docker Compose stack includes the backend, frontend, PostgreSQL, and Redis; the application currently uses local file/vector storage for knowledge artifacts.

### Embedding-backed RAG

The knowledge pipeline extracts and chunks approved documents, creates embeddings, stores them in
ChromaDB, embeds each incoming query, and ranks normalized vectors with FAISS CPU cosine similarity.
Configure these values
in `.env` before starting Docker Compose:

```env
VECTOR_STORE_BACKEND=chroma
VECTOR_STORE_PATH=data/vector_store
VECTOR_COLLECTION=banking_knowledge
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_API_KEY=your-api-key
OPENAI_EMBEDDING_MODEL=text-embedding-3-small
OPENAI_EMBEDDING_DIMENSION=1536
```

Rebuild the index after adding or changing approved documents:

```bash
python scripts/ingest.py
```

Without `OPENAI_API_KEY`, development falls back to local chunks and lexical retrieval; it does not claim to provide vector similarity search.

### RAG evaluation

Ragas evaluation is opt-in and uses the sample dataset at `data/rag_eval_dataset.jsonl`:

```powershell
python -m venv .venv-rag-eval
.venv-rag-eval\Scripts\activate
python -m pip install -r requirements-eval.txt
python scripts/evaluate_rag.py
```

Add evaluation cases as JSONL records with `user_input`, `reference`, and `reference_contexts`.
The evaluator reports context precision, context recall, faithfulness, and response relevancy.

## Architecture diagram

Regenerate the diagram after architecture changes:

```powershell
python generate_architecture_diagram.py
```

This writes `architecture_diagram.png` and `architecture_diagram.svg` at the repository root.

## Microsoft Graph calendar

New Outlook and Outlook Web calendar access uses Microsoft Graph rather than the Classic Outlook COM API.
Register a public-client application in Microsoft Entra ID, grant delegated `Calendars.ReadWrite` and
`User.Read` permissions, and add these values to `.env`:

```env
GRAPH_CLIENT_ID=your-public-client-id
GRAPH_TENANT_ID=common
GRAPH_SCOPES=Calendars.ReadWrite User.Read
GRAPH_TOKEN_CACHE_PATH=data/graph_token_cache.json
GRAPH_TIMEZONE=UTC
```

The first calendar request starts Microsoft device authentication and prints a one-time code in the backend
terminal. Complete that sign-in once; the MSAL token cache is reused for later calendar reads and writes.

## Microsoft Graph mail

MailMate can use Microsoft Graph or Classic Outlook desktop COM. Configure `MAIL_PROVIDER=graph` for Microsoft Graph, or leave the default `outlook` for local Classic Outlook access. For Graph, register the same public-client Entra ID application
with delegated `Mail.Read`, `Mail.ReadWrite`, `Mail.Send`, and `User.Read` permissions, then configure:

```env
GRAPH_CLIENT_ID=your-public-client-id
GRAPH_TENANT_ID=common
GRAPH_MAIL_SCOPES=Mail.Read Mail.ReadWrite Mail.Send User.Read
MAIL_IMPORTANT_SENDERS=ceo@bank.example,manager@bank.example
```

The first Graph mail request starts device authentication in the backend terminal. MailMate reads the current user's mailbox,
returns the latest email on request, and triages every message by read state, relevance, sender importance,
attachments, and action needed. Set `ALLOW_OUTLOOK_FALLBACK=false` to require Graph and disable local Outlook COM.

For Classic Outlook, Outlook desktop must be installed, open, and signed in on the same Windows user session as the backend. The backend uses the existing Outlook profile and does not require a mailbox password.

## API surface

- `GET /health`
- `POST /api/v1/chat/sessions/{session_id}/messages`
- `GET /api/v1/dashboard/summary`
- `GET /api/v1/email/messages`
- `POST /api/v1/email/send`
- `POST /api/v1/documents/upload`
- `POST /api/v1/knowledge/search`
- `POST /api/v1/knowledge/confluence/ingest`
