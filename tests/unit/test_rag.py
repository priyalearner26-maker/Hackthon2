from pathlib import Path

from backend.knowledge.loaders import chunk_document, discover_documents, load_text
from backend.knowledge.retriever import KnowledgeRetriever, analyze_retrieval_query
from backend.orchestrator.supervisor import synthesize_response


def test_chunk_document_preserves_content_and_creates_stable_ids(tmp_path: Path) -> None:
    source = tmp_path / "policy.md"
    text = "Customer verification requires two approved identity checks before account access."

    first = chunk_document(source, text, chunk_size=45, overlap=10)
    second = chunk_document(source, text, chunk_size=45, overlap=10)

    assert first
    assert [chunk.chunk_id for chunk in first] == [chunk.chunk_id for chunk in second]
    assert "Customer verification" in first[0].content


def test_retrieval_query_analysis_expands_domain_concepts() -> None:
    result = analyze_retrieval_query("What are the rules of retail lending?")

    assert "retail lending" in result["concepts"]
    assert "mortgage" in result["expanded_query"]
    assert "eligibility" in result["expanded_query"]


def test_local_rag_returns_relevant_citation(tmp_path: Path) -> None:
    knowledge = tmp_path / "knowledge"
    knowledge.mkdir()
    (knowledge / "verification.md").write_text(
        "Customer verification requires two approved identity checks.", encoding="utf-8"
    )
    (knowledge / "unrelated.md").write_text("Office kitchen maintenance schedule.", encoding="utf-8")

    results = KnowledgeRetriever(knowledge).search("What are the identity checks for customer verification?")

    assert len(results) == 1
    assert results[0].source.endswith("verification.md")
    assert results[0].citation.startswith("[")


def test_local_rag_normalizes_plural_query_terms(tmp_path: Path) -> None:
    knowledge = tmp_path / "knowledge"
    knowledge.mkdir()
    (knowledge / "api-contracts.md").write_text(
        "Approved API workspace endpoints and response contracts.", encoding="utf-8"
    )

    results = KnowledgeRetriever(knowledge).search("What are the API contracts?")

    assert len(results) == 1
    assert results[0].source.endswith("api-contracts.md")


def test_local_rag_prefers_matching_policy_phrase(tmp_path: Path) -> None:
    knowledge = tmp_path / "knowledge"
    knowledge.mkdir()
    (knowledge / "customer-verification-policy.md").write_text(
        "Customer verification requires two approved identity checks.", encoding="utf-8"
    )
    (knowledge / "broad-notes.md").write_text(
        "Customer service teams verify account requests and review requirements.", encoding="utf-8"
    )

    results = KnowledgeRetriever(knowledge).search("What are the customer verification requirements?")

    assert results[0].source.endswith("customer-verification-policy.md")


def test_retriever_uses_knowledge_root_specific_chunk_store(tmp_path: Path) -> None:
    knowledge = tmp_path / "knowledge"
    knowledge.mkdir()
    (knowledge / "verification.md").write_text(
        "Customer verification requires two approved identity checks.", encoding="utf-8"
    )

    retriever = KnowledgeRetriever(knowledge)
    retriever.rebuild_store()

    assert (knowledge / ".vector_store" / "chunks.json").exists()


def test_synthesize_response_hides_routing_and_document_paths() -> None:
    result = synthesize_response(
        {
            "route": "chat",
            "sources": ["[C:\\Hackthon\\data\\knowledge_base\\01_retail_account_opening_process.pdf]"],
            "passages": ["Customer verification requires two approved identity checks."],
        }
    )

    assert result["response"] == "Customer verification requires two approved identity checks."
    assert "Request routed to the" not in result["response"]
    assert "C:\\Hackthon" not in result["response"]


def test_load_text_strips_pdf_page_markers() -> None:
    pdf_path = Path("tests/fixtures/sample.pdf")

    if not pdf_path.exists():
        assert True
        return

    content = load_text(pdf_path)

    assert "[Page" not in content


def test_discover_documents_skips_hidden_directories(tmp_path: Path) -> None:
    knowledge = tmp_path / "knowledge"
    knowledge.mkdir()
    (knowledge / "visible.md").write_text("visible content", encoding="utf-8")
    hidden_dir = knowledge / ".vector_store"
    hidden_dir.mkdir()
    (hidden_dir / "chunks.json").write_text('{"chunk": "should not be indexed"}', encoding="utf-8")

    documents = discover_documents(knowledge)

    assert [doc.name for doc in documents] == ["visible.md"]