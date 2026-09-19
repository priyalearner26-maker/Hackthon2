"""LangGraph supervisor for the employee request workflow."""

import re
from typing import TypedDict
from backend.app.config import settings

from langgraph.graph import END, START, StateGraph

from backend.agents.assistant_agent import AssistantAgent
from backend.agents.chat_agent import ChatAgent
from backend.agents.document_agent import DocumentAgent
from backend.agents.email_agent import EmailAgent
from backend.agents.jira_confluence_agent import JiraConfluenceAgent
from backend.agents.meeting_agent import MeetingAgent
from backend.knowledge.retriever import KnowledgeRetriever


class SupervisorState(TypedDict, total=False):
    session_id: str
    message: str
    agent: str | None
    route: str
    agent_name: str
    sources: list[str]
    passages: list[str]
    response: str


def classify_request(state: SupervisorState) -> SupervisorState:
    requested_agent = (state.get("agent") or "").casefold()
    explicit_routes = {
        "email": "email",
        "meeting": "meeting",
        "jira": "jira_confluence",
        "confluence": "confluence",
        "document": "document",
        "knowledge": "document",
        "assistant": "assistant",
    }
    if requested_agent in explicit_routes:
        return {"route": explicit_routes[requested_agent]}

    message = state["message"].lower()

    if any(term in message for term in ("email", "outlook", "mailmate", "mailbox", "inbox", "send", "reply", "draft")) or re.search(
        r"\b(?:read|show|find|check)\s+(?:my\s+)?(?:latest|newest|recent)\s+mail\b",
        message,
    ):
        route = "email"
    elif any(term in message for term in ("meeting", "calendar", "teams", "schedule", "agenda")):
        route = "meeting"
    elif any(term in message for term in ("jira", "confluence", "issue", "sprint", "roadmap", "project", "ourtool")) or (
        any(term in message for term in ("recent", "latest", "newest", "updated"))
        and any(term in message for term in ("task", "tasks", "backlog", "work item", "work items"))
    ):
        route = "jira_confluence"
    elif any(term in message for term in (
        "document", "file", "policy", "policies", "contract", "verification",
        "retail banking", "retail lending", "lending", "loan", "mortgage",
        "eligibility", "requirements", "rules", "procedure", "procedures",
    )):
        route = "document"
    else:
        route = "assistant"

    return {"route": route}


def retrieve_knowledge(state: SupervisorState) -> SupervisorState:
    if state.get("route") == "assistant" or (
        state.get("route") == "confluence"
        and "recent" in state["message"].casefold()
        and "page" in state["message"].casefold()
    ):
        return {"sources": [], "passages": []}
    chunks = KnowledgeRetriever().search(state["message"])
    return {
        "sources": [chunk.citation for chunk in chunks],
        "passages": [chunk.content for chunk in chunks],
    }


def _clean_passage(passage: str) -> str:
    cleaned = passage.strip()
    cleaned = re.sub(r"^#+\s*", "", cleaned, flags=re.MULTILINE)
    cleaned = cleaned.replace("```text", "").replace("```", "")
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def _summarize_passage(passage: str) -> str:
    cleaned = _clean_passage(passage)
    summary = re.split(r"(?<=[.!?])\s+", cleaned, maxsplit=1)[0]
    return summary.strip()


def _fallback_guidance(message: str, passages: list[str]) -> str:
    query_terms = set(re.findall(r"[a-z0-9]{3,}", message.casefold()))
    lending_query = bool(query_terms & {"lend", "lending", "loan", "mortgage", "credit"})
    lending_terms = {"lend", "lending", "loan", "mortgage", "credit", "eligibility", "affordability"}
    candidates: list[tuple[int, str]] = []
    for passage in passages[:3]:
        cleaned = _clean_passage(passage)
        for sentence in re.split(r"(?<=[.!?])\s+", cleaned):
            sentence = sentence.strip(" -")
            if (
                not sentence
                or not (sentence[0].isupper() or sentence[0].isdigit())
                or (not sentence.endswith((".", "!", "?")) and len(sentence) < 80)
            ):
                continue
            sentence_terms = set(re.findall(r"[a-z0-9]{3,}", sentence.casefold()))
            if lending_query and not (sentence_terms & lending_terms):
                continue
            score = len(query_terms & sentence_terms)
            if any(term in sentence.casefold() for term in ("lending", "loan", "mortgage", "eligibility")):
                score += 2
            candidates.append((score, sentence))
    selected: list[str] = []
    for _score, sentence in sorted(candidates, key=lambda item: item[0], reverse=True):
        if sentence not in selected:
            selected.append(sentence)
        if len(selected) == 3:
            break
    return "\n".join(f"- {sentence}" for sentence in selected)


def _exact_source_guidance(message: str, passages: list[str]) -> str:
    query_terms = set(re.findall(r"[a-z0-9]{3,}", message.casefold()))
    candidates: list[tuple[int, str]] = []
    for passage in passages[:5]:
        units = re.split(r"\s+(?=-\s|`(?:GET|POST|PUT|PATCH|DELETE)\s)", _clean_passage(passage))
        for unit in units:
            for sentence in re.split(r"(?<=[.!?])\s+", unit):
                sentence = sentence.strip(" -")
                if not sentence or len(sentence.split()) < 4:
                    continue
                if not (sentence[0].isupper() or sentence[0].isdigit() or sentence.startswith("`")):
                    continue
                if not sentence.endswith((".", "!", "?")) and "`" not in sentence:
                    continue
                sentence_terms = set(re.findall(r"[a-z0-9]{3,}", sentence.casefold()))
                overlap = len(query_terms & sentence_terms)
                if overlap:
                    candidates.append((overlap, sentence))

    selected: list[str] = []
    for _score, sentence in sorted(candidates, key=lambda item: item[0], reverse=True):
        if sentence not in selected:
            selected.append(sentence)
        if len(selected) == 3:
            break
    return "\n".join(f"- {sentence}" for sentence in selected)


def _evidence_overlap(message: str, passages: list[str]) -> int:
    query_terms = set(re.findall(r"[a-z0-9]{3,}", message.casefold()))
    if not query_terms:
        return 0
    total_overlap = 0
    for passage in passages[:5]:
        passage_terms = set(re.findall(r"[a-z0-9]{3,}", _clean_passage(passage).casefold()))
        total_overlap += len(query_terms & passage_terms)
    return total_overlap


def _not_available_message() -> str:
    return (
        "The information you are searching for is not available in the approved knowledge base. "
        "Please contact the relevant team for further clarification."
    )


def _concise_guidance(message: str, passages: list[str]) -> str:
    if not passages:
        return _not_available_message()

    overlap = _evidence_overlap(message, passages)
    if overlap == 0:
        return _not_available_message()

    lowered = message.casefold()
    generic_policy_query = bool(re.search(r"\b(?:policy|policies|procedure|procedures)\b", lowered)) and not any(
        term in lowered for term in ("retail banking", "loan", "mortgage", "eligibility", "verification", "customer", "lending")
    )
    if generic_policy_query:
        return DocumentAgent().run(type("Context", (), {"message": message})())

    source_text = "\n\n".join(_clean_passage(passage) for passage in passages[:3])
    exact_answer = _exact_source_guidance(message, passages)
    if exact_answer:
        return exact_answer
    fallback = _fallback_guidance(message, passages)
    if not settings.llm_api_key or not settings.llm_model:
        return fallback

    try:
        from langchain_core.output_parsers import StrOutputParser
        from langchain_core.prompts import ChatPromptTemplate
        from langchain_openai import ChatOpenAI

        prompt = ChatPromptTemplate.from_template(
            """You answer bank employee questions using only the approved passages below.
Return at most 3 concise bullet points, one per line, each starting with '- '.
Answer the question directly. Do not repeat the question, mention retrieval, or add unsupported details.
Preserve exact numbers, dates, names, thresholds, and required steps from the approved passages.
If the passages do not contain the answer, return exactly: "The information you are searching for is not available in the approved knowledge base. Please contact the relevant team for further clarification."

Question: {question}

Approved passages:
{passages}"""
        )
        chain = prompt | ChatOpenAI(
            api_key=settings.llm_api_key,
            base_url=(settings.openai_base_url or "https://api.openai.com/v1").rstrip("/"),
            model=settings.llm_model,
            max_completion_tokens=300,
        ) | StrOutputParser()
        answer = chain.invoke({"question": message, "passages": source_text})
        if "not available in the approved knowledge base" in str(answer).casefold():
            return fallback if overlap > 1 else _not_available_message()
        bullets = [
            re.sub(r"^\s*(?:[-*]|\d+[.)])\s*", "", line).strip()
            for line in str(answer).splitlines()
            if re.sub(r"^\s*(?:[-*]|\d+[.)])\s*", "", line).strip()
        ][:3]
        if bullets:
            return "\n".join(f"- {bullet}" for bullet in bullets)
    except Exception:
        pass
    return fallback if overlap > 1 else _not_available_message()


def route_agent(state: SupervisorState) -> SupervisorState:
    route = state.get("route", "assistant")
    agent_map = {
        "assistant": AssistantAgent(),
        "chat": ChatAgent(),
        "email": EmailAgent(),
        "meeting": MeetingAgent(),
        "jira_confluence": JiraConfluenceAgent(),
        "confluence": JiraConfluenceAgent(),
        "document": DocumentAgent(),
    }

    agent = agent_map.get(route, AssistantAgent())
    response = agent.run(
        type(
            "Context",
            (),
            {
                "session_id": state.get("session_id", ""),
                "message": state.get("message", ""),
                "agent": route,
                "retrieved_sources": state.get("sources", []),
                "retrieved_chunks": state.get("passages", []),
            },
        )()
    )

    if route == "document" and not state.get("passages"):
        response = (
            "The information you are searching for is not available in the approved knowledge base. "
            "Please contact the relevant team for further clarification."
        )
    elif route == "document" and state.get("passages"):
        citations = state.get("sources", [])
        citation = citations[0] if citations else ""
        primary_passages = [
            _clean_passage(passage)
            for source, passage in zip(citations, state["passages"])
            if source == citation
        ]
        if not primary_passages:
            primary_passages = [_clean_passage(state["passages"][0])]
        response = _concise_guidance(state["message"], primary_passages)

    return {
        "agent_name": agent.name,
        "response": response,
    }


def synthesize_response(state: SupervisorState) -> SupervisorState:
    passages = state.get("passages", [])
    if passages:
        answer = passages[0].strip()
    else:
        answer = "No approved source matched. Add approved documents to data/knowledge_base."

    return {"response": answer}


def build_graph():
    graph = StateGraph(SupervisorState)
    graph.add_node("classify", classify_request)
    graph.add_node("retrieve", retrieve_knowledge)
    graph.add_node("route", route_agent)
    graph.add_edge(START, "classify")
    graph.add_edge("classify", "retrieve")
    graph.add_edge("retrieve", "route")
    graph.add_edge("route", END)
    return graph.compile()


class Supervisor:
    def __init__(self) -> None:
        self.graph = build_graph()

    def handle(self, session_id: str, message: str, agent: str | None = None) -> str:
        result = self.graph.invoke({"session_id": session_id, "message": message, "agent": agent})
        return result.get("response", "")

    def handle_with_metadata(self, session_id: str, message: str, agent: str | None = None) -> dict[str, str]:
        result = self.graph.invoke({"session_id": session_id, "message": message, "agent": agent})
        return {
            "route": result.get("agent_name", "assistant"),
            "response": result.get("response", ""),
        }


supervisor = Supervisor()
