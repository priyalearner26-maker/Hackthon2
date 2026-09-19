"""Hybrid knowledge retrieval with Azure AI Search and a local fallback."""

from collections import Counter
import difflib
import json
from pathlib import Path
import re
from typing import Protocol

import httpx

from backend.app.config import settings
from backend.core.models import RetrievedChunk
from backend.knowledge.loaders import DocumentChunk, load_chunks


QUERY_CONCEPTS = {
    "retail lending": ("loan", "mortgage", "credit", "affordability", "eligibility", "documentation"),
    "lending": ("loan", "mortgage", "credit", "affordability", "eligibility", "documentation"),
    "banking": ("retail banking", "customer service", "account", "payments", "deposits", "withdrawals", "branches"),
    "core banking": ("retail banking", "customer service", "account", "payments", "deposits", "withdrawals", "branches"),
    "rules": ("policy", "requirements", "procedure", "approved", "controls"),
    "requirements": ("required", "eligibility", "documentation", "procedure"),
    "customer verification": ("identity checks", "passcode", "account detail", "fraud"),
    "project status": ("progress", "risks", "blockers", "defects", "next steps"),
}

_COMMON_TYPO_MAP = {
    "bankin": "banking",
    "corebaking": "core banking",
    "cor": "core",
    "custmer": "customer",
    "verifcation": "verification",
    "verfication": "verification",
    "requirment": "requirement",
    "requriment": "requirement",
    "identty": "identity",
    "accout": "account",
    "retial": "retail",
    "reail": "retail",
    "bankig": "banking",
    "lendig": "lending",
    "eligiblity": "eligibility",
    "documenation": "documentation",
    "aprove": "approve",
    "approvd": "approved",
    "polciy": "policy",
    "segmet": "segment",
}


def normalize_query(query: str) -> str:
    """Normalize basic user typos and domain phrasing before retrieval."""
    cleaned = re.sub(r"[^a-z0-9\s]+", " ", query.casefold())
    tokens: list[str] = []
    for raw_token in cleaned.split():
        token = raw_token.strip()
        if not token:
            continue
        corrected = _COMMON_TYPO_MAP.get(token, token)
        normalized = _normalize_term(corrected)
        if normalized and normalized not in _STOP_WORDS:
            tokens.append(normalized)
    normalized_query = " ".join(tokens)
    if not normalized_query:
        return " ".join(_normalize_term(part) for part in cleaned.split() if _normalize_term(part))
    return normalized_query


def analyze_retrieval_query(query: str) -> dict[str, object]:
    """Analyze a user query into retrieval concepts without changing the user wording."""
    raw_normalized = re.sub(r"[^a-z0-9\s]+", " ", query.casefold())
    concepts = [name for name in QUERY_CONCEPTS if name in raw_normalized]
    expanded_terms: list[str] = []
    for concept in concepts:
        expanded_terms.extend(QUERY_CONCEPTS[concept])
    normalized_query = normalize_query(query)
    expanded_query = " ".join(dict.fromkeys([normalized_query or raw_normalized, *expanded_terms]))
    return {
        "original_query": query,
        "concepts": concepts,
        "expanded_query": expanded_query,
    }


class EmbeddingProvider(Protocol):
    def embed(self, text: str) -> list[float]: ...


class OpenAIEmbeddingProvider:
    """Embedding client for OpenAI and OpenAI-compatible providers."""

    def __init__(self) -> None:
        if not settings.openai_api_key:
            raise ValueError("OPENAI_API_KEY is required for embeddings")
        self.endpoint = (settings.openai_base_url or "https://api.openai.com/v1").rstrip("/")
        self.model = settings.openai_embedding_model

    def embed(self, text: str) -> list[float]:
        response = httpx.post(
            f"{self.endpoint}/embeddings",
            headers={"Authorization": f"Bearer {settings.openai_api_key}"},
            json={"model": self.model, "input": text},
            timeout=30,
        )
        response.raise_for_status()
        payload = response.json()
        return [float(value) for value in payload["data"][0]["embedding"]]

    def embed_many(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        response = httpx.post(
            f"{self.endpoint}/embeddings",
            headers={"Authorization": f"Bearer {settings.openai_api_key}"},
            json={"model": self.model, "input": texts},
            timeout=60,
        )
        response.raise_for_status()
        items = sorted(response.json()["data"], key=lambda item: item["index"])
        return [[float(value) for value in item["embedding"]] for item in items]


class ChromaFaissVectorStore:
    """Persist embeddings in ChromaDB and search them with FAISS on CPU."""

    def __init__(self) -> None:
        try:
            import chromadb
            import faiss
            import numpy as np
        except ImportError as exc:
            raise RuntimeError("chromadb, faiss-cpu, and numpy are required for vector storage") from exc

        self._faiss = faiss
        self._numpy = np
        model_slug = re.sub(r"[^a-z0-9]+", "_", settings.openai_embedding_model.lower()).strip("_")
        collection_name = settings.vector_collection
        if model_slug:
            collection_name = f"{settings.vector_collection}_{model_slug}"
        client = chromadb.PersistentClient(path=str(Path(settings.vector_store_path).resolve()))
        self.collection = client.get_or_create_collection(
            name=collection_name,
            metadata={"hnsw:space": "cosine"},
        )

    def read_chunks(self) -> list[DocumentChunk]:
        data = self.collection.get(include=["documents", "metadatas"])
        documents = data.get("documents") or []
        metadatas = data.get("metadatas") or []
        ids = data.get("ids") or []
        return [
            DocumentChunk(
                chunk_id=chunk_id,
                source=str(metadata.get("source", "unknown")),
                content=document,
                page=metadata.get("page"),
                metadata={str(key): str(value) for key, value in metadata.items() if key not in {"source", "page"}},
            )
            for chunk_id, document, metadata in zip(ids, documents, metadatas)
        ]

    def has_embeddings(self) -> bool:
        return self.collection.count() > 0

    def write_chunks(self, chunks: list[DocumentChunk], embeddings: list[list[float]]) -> None:
        if len(chunks) != len(embeddings):
            raise ValueError("Each document chunk must have one embedding")

        existing_ids = self.collection.get(include=[]).get("ids") or []
        if existing_ids:
            self.collection.delete(ids=existing_ids)

        self.collection.add(
            ids=[chunk.chunk_id for chunk in chunks],
            documents=[chunk.content for chunk in chunks],
            embeddings=embeddings,
            metadatas=[
                {"source": chunk.source, "page": chunk.page if chunk.page is not None else -1, **chunk.metadata}
                for chunk in chunks
            ],
        )

    def search(self, embedding: list[float], top_k: int) -> list[RetrievedChunk]:
        data = self.collection.get(include=["embeddings", "documents", "metadatas"])
        ids = data.get("ids") or []
        embeddings = data.get("embeddings")
        if not ids or embeddings is None or len(embeddings) == 0:
            return []

        vectors = self._numpy.asarray(embeddings, dtype="float32")
        query = self._numpy.asarray([embedding], dtype="float32")
        self._faiss.normalize_L2(vectors)
        self._faiss.normalize_L2(query)
        index = self._faiss.IndexFlatIP(vectors.shape[1])
        index.add(vectors)
        scores, positions = index.search(query, min(top_k, len(ids)))
        documents = data.get("documents") or []
        metadatas = data.get("metadatas") or []
        results: list[RetrievedChunk] = []
        for score, position in zip(scores[0], positions[0]):
            if position < 0:
                continue
            metadata = metadatas[position] or {}
            page = metadata.get("page")
            results.append(
                RetrievedChunk(
                    chunk_id=ids[position],
                    source=str(metadata.get("source", "unknown")),
                    content=documents[position],
                    score=float(score),
                    page=None if page in (None, -1) else int(page),
                    metadata={
                        str(key): str(value)
                        for key, value in metadata.items()
                        if key not in {"source", "page"}
                    },
                )
            )
        return results


class AzureSearchClient:
    """Azure adapter; local development does not require cloud credentials."""

    def __init__(self, endpoint: str, index_name: str) -> None:
        from azure.core.credentials import AzureKeyCredential
        from azure.search.documents import SearchClient

        if not settings.azure_search_key:
            raise ValueError("AZURE_SEARCH_KEY is required for Azure AI Search")
        self.client = SearchClient(endpoint, index_name, AzureKeyCredential(settings.azure_search_key))

    def search(self, query: str, top_k: int) -> list[RetrievedChunk]:
        results = self.client.search(search_text=query, top=top_k, query_type="semantic")
        return [
            RetrievedChunk(
                chunk_id=str(item.get("id", "")),
                source=str(item.get("source", "unknown")),
                content=str(item.get("content", "")),
                score=float(item.get("@search.reranker_score", item.get("@search.score", 0))),
                page=item.get("page"),
            )
            for item in results
        ]


class LocalReranker:
    def rerank(self, query: str, chunks: list[tuple[float, DocumentChunk]]) -> list[tuple[float, DocumentChunk]]:
        query_terms = set(_terms(query))
        ordered_terms = _terms(query)
        if not query_terms:
            return chunks

        reranked: list[tuple[float, DocumentChunk]] = []
        for score, chunk in chunks:
            source_terms = set(_terms(chunk.source))
            content_terms = set(_terms(chunk.content))
            overlap = len(query_terms & content_terms)
            source_overlap = len(query_terms & source_terms)
            title_bonus = 0.25 * source_overlap
            content_bonus = 0.1 * overlap
            normalized_content = _terms(chunk.content)
            phrase_bonus = sum(
                8.0
                for left, right in zip(ordered_terms, ordered_terms[1:])
                if any(
                    normalized_content[index:index + 2] == [left, right]
                    for index in range(max(0, len(normalized_content) - 1))
                )
            )
            exact_phrase_bonus = _phrase_bonus(query, chunk.content)
            reranked.append((score + title_bonus + content_bonus + phrase_bonus + exact_phrase_bonus, chunk))

        reranked.sort(key=lambda item: item[0], reverse=True)
        return reranked


def _phrase_bonus(query: str, text: str) -> float:
    query_terms = _terms(query)
    content_terms = _terms(text)
    if len(query_terms) < 2:
        return 0.0

    match_count = 0
    for index in range(len(query_terms) - 1):
        phrase = tuple(query_terms[index:index + 2])
        for cursor in range(len(content_terms) - 1):
            if tuple(content_terms[cursor:cursor + 2]) == phrase:
                match_count += 1
                break
    return float(match_count) * 2.5


class LocalLexicalRetriever:
    def __init__(self, chunks: list[DocumentChunk]) -> None:
        self.chunks = chunks
        self.reranker = LocalReranker()
        self.vocabulary = {
            term
            for chunk in self.chunks
            for term in _terms(chunk.content + " " + (chunk.source or ""))
            if term
        }

    def _expand_query_terms(self, query_terms: Counter[str]) -> Counter[str]:
        expanded = Counter()
        for term, count in query_terms.items():
            expanded[term] += count * 2
            normalized_term = _COMMON_TYPO_MAP.get(term, term)
            if normalized_term != term:
                expanded[normalized_term] += count * 2
            matches = difflib.get_close_matches(term, self.vocabulary, n=3, cutoff=0.72)
            for match in matches:
                expanded[match] += count
            if len(term) > 4:
                for candidate in self.vocabulary:
                    if candidate == term:
                        continue
                    if len(candidate) < max(3, len(term) - 2) or len(candidate) > len(term) + 2:
                        continue
                    if difflib.SequenceMatcher(None, term, candidate).ratio() >= 0.75:
                        expanded[candidate] += count
        return expanded

    def search(self, query: str, top_k: int) -> list[RetrievedChunk]:
        query_terms = Counter(_terms(query))
        if not query_terms:
            return []

        expanded_query_terms = self._expand_query_terms(query_terms)
        scored: list[tuple[float, DocumentChunk]] = []
        for chunk in self.chunks:
            terms = Counter(_terms(chunk.content))
            matched_terms = set(expanded_query_terms) & set(terms)
            if not matched_terms:
                continue

            overlap = sum(min(expanded_query_terms[term], terms[term]) for term in matched_terms)
            if len(query_terms) > 1 and overlap == 0:
                continue

            unique_query_terms = len(expanded_query_terms)
            unique_chunk_terms = len(terms)
            weighted_overlap = overlap * 10
            term_coverage = overlap / max(unique_query_terms, 1)
            chunk_density = term_coverage * (len(terms) / max(unique_chunk_terms, 1))
            score = weighted_overlap + term_coverage + chunk_density
            scored.append((score, chunk))

        reranked = self.reranker.rerank(query, scored)
        results: list[RetrievedChunk] = []
        seen_content: set[str] = set()
        for score, chunk in reranked:
            content_key = re.sub(r"\s+", " ", chunk.content).strip().casefold()
            if content_key in seen_content:
                continue
            seen_content.add(content_key)
            results.append(RetrievedChunk(chunk.chunk_id, chunk.source, chunk.content, score, chunk.page, chunk.metadata))
            if len(results) == top_k:
                break
        return results


_STOP_WORDS = {
    "a", "an", "and", "are", "as", "at", "be", "for", "from", "how", "i", "in",
    "is", "it", "me", "of", "on", "or", "that", "the", "this", "to", "what", "with",
    "you", "your",
}


def _terms(text: str) -> list[str]:
    return [
        _normalize_term(term)
        for term in re.findall(r"[a-z0-9]{2,}", text.lower())
        if term not in _STOP_WORDS
    ]


def _normalize_term(term: str) -> str:
    if len(term) > 5 and term.endswith("ies"):
        return term[:-3] + "y"
    if len(term) > 5 and term.endswith("ing"):
        return term[:-3]
    if len(term) > 4 and term.endswith("es"):
        return term[:-2]
    if len(term) > 4 and term.endswith("s"):
        return term[:-1]
    return term


class KnowledgeRetriever:
    def __init__(self, knowledge_root: Path | None = None, search_client: AzureSearchClient | None = None) -> None:
        repository_root = Path(__file__).resolve().parents[2]
        root = knowledge_root or repository_root / "data" / "knowledge_base"
        self.knowledge_root = root
        use_persistent_store = knowledge_root is None
        self.search_client = search_client
        if self.search_client is None and settings.azure_search_endpoint and settings.azure_search_index:
            self.search_client = AzureSearchClient(settings.azure_search_endpoint, settings.azure_search_index)
        self.chunk_store_path = (root / ".vector_store" / "chunks.json").resolve()
        self.vector_store: ChromaFaissVectorStore | None = None
        if use_persistent_store and settings.vector_store_backend.lower() in {"chroma", "chromadb", "faiss"}:
            try:
                self.vector_store = ChromaFaissVectorStore()
            except Exception:
                self.vector_store = None
        self.embedding_provider: OpenAIEmbeddingProvider | None = None
        if self.vector_store is not None and settings.openai_api_key:
            self.embedding_provider = OpenAIEmbeddingProvider()
        elif self.vector_store is not None:
            self.vector_store = None
        self.chunks = self._load_or_rebuild_chunks(root)
        self.local = LocalLexicalRetriever(self.chunks)

    def _load_or_rebuild_chunks(self, root: Path) -> list[DocumentChunk]:
        if self.vector_store is not None:
            try:
                chunks = self.vector_store.read_chunks()
                if chunks and (self.embedding_provider is None or self.vector_store.has_embeddings()):
                    return chunks
            except Exception:
                self.vector_store = None

        if self.chunk_store_path.exists():
            data = json.loads(self.chunk_store_path.read_text(encoding="utf-8"))
            if data:
                return [
                    DocumentChunk(
                        chunk_id=item["chunk_id"],
                        source=item["source"],
                        content=item["content"],
                        page=item.get("page"),
                        metadata=item.get("metadata", {}),
                    )
                    for item in data
                ]

        chunks = load_chunks(root)
        self._write_chunks(chunks)
        return chunks

    def _write_chunks(self, chunks: list[DocumentChunk]) -> None:
        if self.vector_store is not None:
            if self.embedding_provider is None:
                raise RuntimeError("OPENAI_API_KEY is required to write ChromaDB embeddings")
            try:
                embeddings = self.embedding_provider.embed_many([chunk.content for chunk in chunks])
            except httpx.HTTPError:
                self.vector_store = None
            else:
                self.vector_store.write_chunks(chunks, embeddings)
                return

        self.chunk_store_path.parent.mkdir(parents=True, exist_ok=True)
        payload = [
            {
                "chunk_id": chunk.chunk_id,
                "source": chunk.source,
                "content": chunk.content,
                "page": chunk.page,
                "metadata": chunk.metadata,
            }
            for chunk in chunks
        ]
        self.chunk_store_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def rebuild_store(self) -> list[DocumentChunk]:
        chunks = load_chunks(self.knowledge_root)
        self.chunks = chunks
        self.local = LocalLexicalRetriever(chunks)
        self._write_chunks(chunks)
        return chunks

    def search(self, query: str, top_k: int = 5, metadata_filter: dict[str, str] | None = None) -> list[RetrievedChunk]:
        if not query.strip():
            return []
        analysis = analyze_retrieval_query(query)
        retrieval_query = str(analysis["expanded_query"])
        semantic_results: list[RetrievedChunk] = []
        if self.vector_store is not None and self.embedding_provider is not None:
            try:
                semantic_results = self.vector_store.search(self.embedding_provider.embed(retrieval_query), top_k * 2)
            except Exception:
                pass
        elif self.search_client is not None:
            try:
                semantic_results = self.search_client.search(query, top_k * 2)
            except Exception:
                pass

        lexical_results = self.local.search(retrieval_query, top_k * 2)
        combined = self._fuse_results(semantic_results, lexical_results)
        if metadata_filter:
            combined = [
                result for result in combined
                if all(result.metadata.get(key) == value for key, value in metadata_filter.items())
            ]
        reranked = self._rerank_results(retrieval_query, combined)
        return reranked[:top_k]

    @staticmethod
    def _fuse_results(*result_sets: list[RetrievedChunk]) -> list[RetrievedChunk]:
        fused: dict[str, tuple[RetrievedChunk, float]] = {}
        for result_set in result_sets:
            for rank, result in enumerate(result_set, start=1):
                reciprocal_rank = 1.0 / (60 + rank)
                current = fused.get(result.chunk_id)
                fused[result.chunk_id] = (result, (current[1] if current else 0.0) + reciprocal_rank)
        return [result for result, _score in sorted(fused.values(), key=lambda item: item[1], reverse=True)]

    @staticmethod
    def _rerank_results(query: str, results: list[RetrievedChunk]) -> list[RetrievedChunk]:
        if not results:
            return []

        query_terms = set(_terms(query))
        scored: list[tuple[float, RetrievedChunk]] = []
        for result in results:
            content_terms = set(_terms(result.content))
            source_terms = set(_terms(result.source))
            overlap = len(query_terms & content_terms)
            source_overlap = len(query_terms & source_terms)
            phrase_bonus = _phrase_bonus(query, result.content)
            score = result.score + (overlap * 0.75) + (source_overlap * 0.5) + phrase_bonus
            if result.page is not None:
                score += 0.1
            scored.append((score, result))

        scored.sort(key=lambda item: item[0], reverse=True)
        return [result for _score, result in scored]

    def evaluate_queries(self, queries: list[str], expected_terms: list[set[str]]) -> dict[str, float]:
        if len(queries) != len(expected_terms):
            raise ValueError("queries and expected_terms must be aligned")

        hit_count = 0
        top_one_hit_count = 0
        reciprocal_rank_scores: list[float] = []
        for index, query in enumerate(queries):
            results = self.search(query, top_k=5)
            if not results:
                reciprocal_rank_scores.append(0.0)
                continue

            expected = expected_terms[index]
            matched = [
                result for result in results
                if expected and any(term in _terms(result.content) for term in expected)
            ]
            if matched:
                hit_count += 1
            if results and any(term in _terms(results[0].content) for term in expected):
                top_one_hit_count += 1
                reciprocal_rank_scores.append(1.0)
            else:
                rank = next((position for position, result in enumerate(results, start=1) if expected and any(term in _terms(result.content) for term in expected)), None)
                reciprocal_rank_scores.append(1.0 / rank if rank is not None else 0.0)

        total = max(len(queries), 1)
        return {
            "hit_rate": hit_count / total,
            "top1_hit_rate": top_one_hit_count / total,
            "mrr": sum(reciprocal for reciprocal in reciprocal_rank_scores) / total,
        }
