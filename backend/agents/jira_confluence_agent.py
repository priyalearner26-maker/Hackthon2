"""Jira and Confluence workflow agent."""

from __future__ import annotations

import json
import re
from typing import Any

import httpx

from backend.agents.base import Agent
from backend.app.config import settings
from backend.core.models import AgentContext
from backend.core.ai_controls import guard_input, guard_output, track_llm_run
from backend.knowledge.loaders import html_to_text


class JiraConfluenceAgent(Agent):
    name = "jira_confluence"

    def run(self, context: AgentContext) -> str:
        query = context.message.strip() or "recent project activity"
        confluence_only = getattr(context, "agent", None) == "confluence"
        confluence_action = self._parse_confluence_write_request(query)
        if confluence_action:
            return self._write_confluence_page(*confluence_action)

        action = self._parse_create_request(query)
        if action:
            return self._create_issue(action[0], action[1])

        if self._is_story_analysis_request(query):
            return self._analyze_story(query)

        jira_specific = self._is_jira_specific_query(query)
        confluence_specific = self._is_confluence_specific_query(query)

        parts: list[str] = []

        if jira_specific and not confluence_specific:
            jira_payload = self._fetch_jira_information(query)
            if jira_payload:
                return jira_payload
            return "Jira: No matching issues were found for the provided request."

        if confluence_specific and not jira_specific:
            confluence_payload = self._fetch_confluence_information(query)
            if confluence_payload:
                return confluence_payload
            return "Confluence: No matching pages were found for the provided request."

        confluence_payload = self._fetch_confluence_information(query)
        if confluence_payload:
            parts.append(confluence_payload)

        if not confluence_only:
            jira_payload = self._fetch_jira_information(query)
            if jira_payload:
                parts.append(jira_payload)

            ourtool_payload = self._fetch_ourtool_information(query)
            if ourtool_payload:
                parts.append(ourtool_payload)

        knowledge = self._format_knowledge_context(
            getattr(context, "retrieved_chunks", []),
            getattr(context, "retrieved_sources", []),
        )
        if confluence_only and knowledge:
            parts.append(knowledge)

        if parts:
            if confluence_only:
                if self._is_confluence_page_listing_request(query):
                    return "\n\n".join(parts)
                return self._summarize_confluence(query, "\n\n".join(parts))
            return "\n\n".join(parts)

        return (
            "Live Jira, Confluence, or OurTool information is unavailable because the required "
            "external integration settings are not configured. Add JIRA_BASE_URL, JIRA_EMAIL, "
            "JIRA_API_TOKEN, JIRA_PROJECT_KEY, CONFLUENCE_BASE_URL, OURTOOL_BASE_URL, and OURTOOL_API_KEY to the environment."
        )

    @staticmethod
    def _parse_confluence_write_request(query: str) -> tuple[str, str, str | None] | None:
        create_match = re.match(
            r"^\s*(?:please\s+)?create\s+(?:a\s+)?confluence\s+page\s*[:\-]?\s*(.+?)\s*\|\s*(.+?)\s*$",
            query,
            flags=re.IGNORECASE,
        )
        if create_match:
            return "create", create_match.group(1).strip(), create_match.group(2).strip()

        update_match = re.match(
            r"^\s*(?:please\s+)?update\s+confluence\s+page\s+(\d+)\s*[:\-]?\s*(?:.+?\s*\|\s*)?(.+?)\s*$",
            query,
            flags=re.IGNORECASE,
        )
        if update_match:
            return "update", update_match.group(2).strip(), update_match.group(1)
        return None

    def _write_confluence_page(self, action: str, title_or_body: str, body_or_page_id: str | None) -> str:
        base_url = (getattr(settings, "confluence_base_url", "") or "").rstrip("/")
        if not base_url or not settings.jira_email or not settings.jira_api_token:
            return "Confluence page changes are unavailable. Configure CONFLUENCE_BASE_URL, JIRA_EMAIL, and JIRA_API_TOKEN."

        if action == "create":
            title, body, page_id = title_or_body, body_or_page_id or "", None
            method = "post"
            url = f"{base_url}/rest/api/content"
            payload = {
                "type": "page",
                "title": title,
                "space": {"key": getattr(settings, "confluence_space_key", "")},
                "body": {"storage": {"value": f"<p>{self._escape_html(body)}</p>", "representation": "storage"}},
            }
        else:
            page_id, body = body_or_page_id, title_or_body
            if not page_id:
                return "A Confluence page ID is required for updates."
            method = "put"
            url = f"{base_url}/rest/api/content/{page_id}"
            current = self._get_confluence_page(page_id)
            if not current:
                return f"Confluence page {page_id} could not be loaded for update."
            payload = {
                "id": page_id,
                "type": "page",
                "title": current.get("title", "Updated Confluence page"),
                "version": {"number": int(current.get("version", {}).get("number", 1)) + 1},
                "body": {"storage": {"value": f"<p>{self._escape_html(body)}</p>", "representation": "storage"}},
            }

        requested_summary, context = self._split_story_context(summary)
        story_summary, story_description = self._format_story_with_llm(requested_summary, context)

        try:
            response = getattr(httpx, method)(
                url,
                headers={"Accept": "application/json", "Content-Type": "application/json"},
                auth=(settings.jira_email, settings.jira_api_token),
                json=payload,
                timeout=10.0,
            )
            response.raise_for_status()
            result = response.json()
            return f"Confluence page {action}d successfully: {result.get('id', page_id or 'new page')} - {payload['title']}"
        except httpx.HTTPStatusError as error:
            return f"Confluence page {action} failed (HTTP {error.response.status_code})."
        except httpx.HTTPError:
            return "Confluence page change failed because Confluence could not be reached."

    def _get_confluence_page(self, page_id: str) -> dict[str, Any] | None:
        base_url = (getattr(settings, "confluence_base_url", "") or "").rstrip("/")
        try:
            response = httpx.get(
                f"{base_url}/rest/api/content/{page_id}",
                params={"expand": "version,body.storage"},
                headers={"Accept": "application/json"},
                auth=(settings.jira_email, settings.jira_api_token),
                timeout=10.0,
            )
            response.raise_for_status()
            return response.json()
        except (httpx.HTTPError, ValueError):
            return None

    @staticmethod
    def _escape_html(value: str) -> str:
        return value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    @staticmethod
    def _split_story_context(raw_text: str) -> tuple[str, str]:
        cleaned = " ".join(raw_text.split()).strip()
        if not cleaned:
            return "Review requested work item", ""

        if "|" in cleaned:
            before, after = cleaned.split("|", 1)
            summary = before.strip()
            context = after.strip()
            if context.lower().startswith("context:"):
                context = context.split(":", 1)[1].strip()
            return summary.strip() or "Review requested work item", context.strip()

        if "context:" in cleaned.lower():
            body, context = re.split(r"\bcontext\s*:\s*", cleaned, maxsplit=1, flags=re.IGNORECASE)
            return body.strip() or "Review requested work item", context.strip()

        return cleaned, ""

    @classmethod
    def _format_story_with_llm(cls, summary: str, context: str) -> tuple[str, str]:
        base_summary = " ".join(summary.split()).strip() or "Review requested work item"
        base_context = " ".join(context.split()).strip()

        if not base_context and not getattr(settings, "llm_api_key", ""):
            cleaned_summary = base_summary.replace("Review Confluence page:", "").strip()
            if not cleaned_summary:
                cleaned_summary = "Review requested work item"
            return cleaned_summary[:120], f"Summary: {cleaned_summary}\n\nRequested action: assess the page content and prepare the follow-up work."

        api_key = getattr(settings, "llm_api_key", "") or getattr(settings, "openai_api_key", "")
        provider = getattr(settings, "llm_provider", "openai").casefold().strip()
        if not api_key and provider != "ollama":
            return cls._fallback_story_text(base_summary, base_context)

        prompt = (
            "Convert the Confluence page context into a concise Jira story title and a meaningful description.\n\n"
            f"Requested summary: {base_summary}\n\n"
            f"Page context: {base_context[:6000]}\n\n"
            "Output valid JSON with exactly two keys: 'summary' and 'description'.\n"
            "- summary: a short issue title, under 120 characters\n"
            "- description: a clear Jira-ready description with 2 to 4 sentences or bullets, grounded in the supplied context only"
        )

        try:
            if provider == "ollama":
                response = httpx.post(
                    f"{settings.ollama_base_url.rstrip('/')}/api/chat",
                    json={
                        "model": settings.ollama_model,
                        "stream": False,
                        "messages": [
                            {"role": "system", "content": "You are a Jira planning assistant. Return JSON only."},
                            {"role": "user", "content": prompt},
                        ],
                    },
                    timeout=60.0,
                )
                response.raise_for_status()
                content = str(response.json()["message"]["content"]).strip()
                answer = guard_output(content)
                track_llm_run(
                    "jira.story.format",
                    provider="ollama",
                    model=settings.ollama_model,
                    input_text=prompt,
                    output_text=answer,
                )
            else:
                base_url = (getattr(settings, "openai_base_url", "") or "https://api.openai.com/v1").rstrip("/")
                response = httpx.post(
                    f"{base_url}/chat/completions",
                    headers={"Authorization": f"Bearer {api_key}"},
                    json={
                        "model": getattr(settings, "llm_model", "gpt-4o-mini") or "gpt-4o-mini",
                        "messages": [
                            {"role": "system", "content": "You are a Jira planning assistant. Return valid JSON with keys summary and description only."},
                            {"role": "user", "content": prompt},
                        ],
                        "max_completion_tokens": 300,
                    },
                    timeout=60.0,
                )
                response.raise_for_status()
                content = str(response.json()["choices"][0]["message"]["content"]).strip()
                answer = guard_output(content)
                track_llm_run(
                    "jira.story.format",
                    provider="openai",
                    model=getattr(settings, "llm_model", "gpt-4o-mini"),
                    input_text=prompt,
                    output_text=answer,
                )

            json_text = answer.strip()
            if json_text.startswith("```"):
                json_text = re.sub(r"^```(?:json)?\s*", "", json_text, flags=re.IGNORECASE)
                json_text = re.sub(r"\s*```$", "", json_text)
            parsed = json.loads(json_text)
            if isinstance(parsed, dict):
                summary_value = str(parsed.get("summary") or base_summary).strip()
                description_value = str(parsed.get("description") or base_context or base_summary).strip()
                if not summary_value:
                    summary_value = base_summary
                if not description_value:
                    description_value = base_context or f"Review and validate the requested work based on: {base_summary}"
                return summary_value[:120], description_value[:4000]
        except (httpx.HTTPError, KeyError, TypeError, ValueError, json.JSONDecodeError):
            pass

        return cls._fallback_story_text(base_summary, base_context)

    @staticmethod
    def _fallback_story_text(summary: str, context: str) -> tuple[str, str]:
        cleaned_summary = summary.replace("Review Confluence page:", "").strip()
        if not cleaned_summary:
            cleaned_summary = "Review requested work item"
        cleaned_summary = " ".join(cleaned_summary.split())[:120]
        description = context.strip() or cleaned_summary
        description = description[:4000]
        if not description:
            description = f"Review and validate the requested work based on the selected Confluence page: {cleaned_summary}"
        return cleaned_summary, description

    @staticmethod
    def _format_knowledge_context(passages: list[Any], sources: list[str] | None = None) -> str:
        if not passages:
            return ""
        content = []
        for index, passage in enumerate(passages[:2]):
            text = getattr(passage, "content", passage)
            if text:
                citation = sources[index] if sources and index < len(sources) else "[indexed Confluence context]"
                content.append(f"{citation}\n{str(text).strip()[:700]}")
        return "### Indexed Confluence and workspace context\n\n" + "\n\n".join(content)

    def _summarize_confluence(self, query: str, context: str) -> str:
        query = guard_input(query)
        api_key = getattr(settings, "llm_api_key", "") or getattr(settings, "openai_api_key", "")
        if not api_key and getattr(settings, "llm_provider", "openai").casefold() != "ollama":
            return context

        prompt = (
            f"User request: {query}\n\n"
            f"Confluence source material:\n{context[:8000]}\n\n"
            "Answer using only the source material. Give a concise summary with key facts and actions. "
            "Keep page citations such as [source] next to the claims they support. "
            "If the source does not answer the request, say so clearly."
        )
        try:
            provider = getattr(settings, "llm_provider", "openai").casefold().strip()
            system_prompt = "You are Confluence Coach. Produce a grounded, professional answer with citations. Do not invent facts."
            if provider == "ollama":
                response = httpx.post(
                    f"{settings.ollama_base_url.rstrip('/')}/api/chat",
                    json={"model": settings.ollama_model, "stream": False, "messages": [{"role": "system", "content": system_prompt}, {"role": "user", "content": prompt}]},
                    timeout=60.0,
                )
                response.raise_for_status()
                answer = guard_output(str(response.json()["message"]["content"]))
                track_llm_run(
                    "confluence.summarize",
                    provider="ollama",
                    model=settings.ollama_model,
                    input_text=query,
                    output_text=answer,
                )
                return answer

            base_url = (getattr(settings, "openai_base_url", "") or "https://api.openai.com/v1").rstrip("/")
            response = httpx.post(
                f"{base_url}/chat/completions",
                headers={"Authorization": f"Bearer {api_key}"},
                json={
                    "model": getattr(settings, "llm_model", "gpt-4o-mini") or "gpt-4o-mini",
                    "messages": [{"role": "system", "content": system_prompt}, {"role": "user", "content": prompt}],
                    "max_completion_tokens": 500,
                },
                timeout=60.0,
            )
            response.raise_for_status()
            answer = guard_output(str(response.json()["choices"][0]["message"]["content"]))
            track_llm_run(
                "confluence.summarize",
                provider="openai",
                model=getattr(settings, "llm_model", "gpt-4o-mini"),
                input_text=query,
                output_text=answer,
            )
            return answer
        except (httpx.HTTPError, KeyError, TypeError, ValueError):
            return context

    @staticmethod
    def _is_jira_specific_query(query: str) -> bool:
        normalized = " ".join(query.split()).casefold()
        if not normalized:
            return False
        jira_markers = (
            "jira",
            "story",
            "stories",
            "task",
            "tasks",
            "issue",
            "issues",
            "backlog",
            "sprint",
            "roadmap",
            "work item",
            "work items",
            "project",
        )
        return any(marker in normalized for marker in jira_markers)

    @staticmethod
    def _is_confluence_specific_query(query: str) -> bool:
        normalized = " ".join(query.split()).casefold()
        if not normalized:
            return False
        return "confluence" in normalized or "page" in normalized and "workspace" in normalized

    @staticmethod
    def _parse_create_request(query: str) -> tuple[str, str] | None:
        match = re.match(
            r"^\s*(?:please\s+)?create\s+(?:a\s+)?(?:jira\s+)?(task|user\s+story|story)"
            r"(?:\s+in\s+jira)?\s*[:\-]?\s*(.+?)\s*$",
            query,
            flags=re.IGNORECASE,
        )
        if not match or not match.group(2).strip():
            return None
        issue_type = "Task" if match.group(1).casefold() == "task" else "Story"
        return issue_type, match.group(2).strip()

    def _create_issue(self, issue_type: str, summary: str) -> str:
        if not settings.jira_base_url or not settings.jira_api_token or not settings.jira_email:
            return "Jira creation is unavailable. Configure JIRA_BASE_URL, JIRA_EMAIL, and JIRA_API_TOKEN."
        if not settings.jira_project_key:
            return "Jira creation is unavailable because JIRA_PROJECT_KEY is not configured."

        requested_summary, context = self._split_story_context(summary)
        story_summary, story_description = self._format_story_with_llm(requested_summary, context)

        try:
            response = httpx.post(
                f"{settings.jira_base_url.rstrip('/')}/rest/api/3/issue",
                headers={"Accept": "application/json", "Content-Type": "application/json"},
                auth=(settings.jira_email, settings.jira_api_token),
                json={
                    "fields": {
                        "project": {"key": settings.jira_project_key},
                        "summary": story_summary,
                        "description": {
                            "type": "doc",
                            "version": 1,
                            "content": [
                                {
                                    "type": "paragraph",
                                    "content": [{"type": "text", "text": story_description}],
                                }
                            ],
                        },
                        "issuetype": {"name": issue_type},
                    }
                },
                timeout=10.0,
            )
            response.raise_for_status()
            payload = response.json()
            issue_key = payload.get("key", "the new issue")
            return f"Jira {issue_type} created successfully: {issue_key} - {story_summary}"
        except httpx.HTTPStatusError as error:
            return f"Jira issue creation failed (HTTP {error.response.status_code})."
        except httpx.HTTPError:
            return "Jira issue creation failed because Jira could not be reached."

    @staticmethod
    def _is_story_analysis_request(query: str) -> bool:
        normalized = query.casefold()
        return "analy" in normalized and "stor" in normalized

    def _analyze_story(self, query: str) -> str:
        issue_key_match = re.search(r"\b([A-Z][A-Z0-9]+-\d+)\b", query)
        story_text = query
        if issue_key_match and settings.jira_base_url and settings.jira_api_token and settings.jira_email:
            try:
                response = httpx.get(
                    f"{settings.jira_base_url.rstrip('/')}/rest/api/3/issue/{issue_key_match.group(1)}",
                    params={"fields": "summary,description,issuetype"},
                    headers={"Accept": "application/json"},
                    auth=(settings.jira_email, settings.jira_api_token),
                    timeout=10.0,
                )
                response.raise_for_status()
                fields = response.json().get("fields", {})
                story_text = f"{fields.get('summary', '')} {self._flatten_description(fields.get('description'))}"
            except httpx.HTTPError:
                return f"Jira story analysis failed because {issue_key_match.group(1)} could not be loaded."
        elif issue_key_match:
            return "Jira story analysis needs Jira credentials to load the requested issue."

        return self._format_story_analysis(story_text)

    @staticmethod
    def _flatten_description(description: Any) -> str:
        if isinstance(description, str):
            return description
        if not isinstance(description, dict):
            return ""
        text: list[str] = []
        for block in description.get("content", []):
            for item in block.get("content", []):
                if item.get("text"):
                    text.append(item["text"])
        return " ".join(text)

    @staticmethod
    def _format_story_analysis(story_text: str) -> str:
        normalized = " ".join(story_text.split())
        has_user_story = bool(re.search(r"\bas\s+(?:a|an|the)\b.+\bi\s+(?:want|need)\b.+\bso\s+that\b", normalized, re.IGNORECASE))
        has_acceptance = bool(re.search(r"acceptance criteria|given\b.+when\b.+then\b", normalized, re.IGNORECASE))
        has_action = bool(re.search(r"must|should|can|shall", normalized, re.IGNORECASE))
        gaps = []
        if not has_user_story:
            gaps.append("Use an As a / I want / So that statement")
        if not has_acceptance:
            gaps.append("Add Given / When / Then acceptance criteria")
        if not has_action:
            gaps.append("Define the expected behavior or outcome")
        result = [
            "Jira story analysis:",
            f"- User story format: {'Ready' if has_user_story else 'Needs improvement'}",
            f"- Acceptance criteria: {'Present' if has_acceptance else 'Missing'}",
            f"- Expected behavior: {'Defined' if has_action else 'Unclear'}",
        ]
        result.append("- Recommended next steps: " + ("; ".join(gaps) if gaps else "Ready for refinement and estimation"))
        return "\n".join(result)

    def _fetch_confluence_information(self, query: str) -> str:
        base_url = (getattr(settings, "confluence_base_url", "") or settings.jira_base_url or "").rstrip("/")
        if not base_url:
            return ""

        page_id_match = re.search(r"(?:/pages/|[?&]pageId=|\bpage\s+)(\d+)", query, flags=re.IGNORECASE)
        if page_id_match:
            page_id = page_id_match.group(1)
            page = self._get_confluence_page(page_id)
            if not page:
                return f"Confluence: Page {page_id} could not be retrieved."
            title = str(page.get("title") or "Untitled page")
            text = self._extract_confluence_text(page)
            result = [f"### Confluence Page", f"- {title} (Page ID: {page_id})"]
            if text:
                result.append(text)
            return "\n".join(result)

        title_query = self._clean_confluence_query(query)
        if not title_query:
            return ""

        try:
            if self._is_recent_workspace_update_query(query):
                cql = 'type = page ORDER BY lastmodified DESC'
            else:
                escaped_query = self._escape_cql(title_query)
                cql = f'title ~ "{escaped_query}" OR text ~ "{escaped_query}"'
            response = httpx.get(
                f"{base_url}/rest/api/content/search",
                params={
                    "cql": cql,
                    "limit": 25 if self._is_recent_workspace_update_query(query) else 5,
                    "expand": "version,metadata.labels",
                },
                headers={"Accept": "application/json"},
                auth=(settings.jira_email, settings.jira_api_token) if settings.jira_email and settings.jira_api_token else None,
                timeout=10.0,
            )
            response.raise_for_status()
            payload = response.json()
            results = self._filter_relevant_confluence_results(query, payload.get("results", []))
            if not results:
                if self._is_recent_workspace_update_query(query):
                    return "Confluence: No relevant pages were found for recent workspace updates. The available Confluence pages appear to be marketing or trial-material rather than specific workspace change updates."
                return "Confluence: No matching pages were found for the provided request."

            lines: list[str] = ["### Confluence Pages"]
            result_limit = 10 if self._is_recent_workspace_update_query(query) else 3
            for result in results[:result_limit]:
                title = str(result.get("title") or "Untitled page")
                page_id = result.get("id", "")
                text = self._extract_confluence_text(result)
                lines.append(f"- {title} (Page ID: {page_id})")
                if text:
                    lines.append(text[:500] + ("..." if len(text) > 500 else ""))
                elif page_id:
                    detail = self._get_confluence_page(str(page_id))
                    detail_text = self._extract_confluence_text(detail or {})
                    if detail_text:
                        lines.append(detail_text[:500] + ("..." if len(detail_text) > 500 else ""))
            return "\n".join(lines)
        except httpx.HTTPStatusError as error:
            if error.response.status_code == 401:
                return (
                    "Confluence: Access denied (401). Verify that your Atlassian account has Confluence access "
                    "and set CONFLUENCE_BASE_URL to the Confluence site if it is different from JIRA_BASE_URL."
                )
            return f"Confluence: Live Confluence data could not be retrieved (HTTP {error.response.status_code})."
        except httpx.HTTPError:
            return "Confluence: Live Confluence data could not be retrieved right now."

    @staticmethod
    def _extract_confluence_text(result: dict[str, Any]) -> str:
        body = result.get("body") or {}
        storage = body.get("storage") or {}
        value = storage.get("value") or ""
        if not value:
            return ""
        return html_to_text(value)

    @staticmethod
    def _is_recent_workspace_update_query(query: str) -> bool:
        lowered = query.casefold()
        return "recent" in lowered and ("workspace" in lowered or "workspaces" in lowered) and ("update" in lowered or "updates" in lowered)

    @staticmethod
    def _is_confluence_page_listing_request(query: str) -> bool:
        normalized = " ".join(query.casefold().split())
        return (
            "confluence" in normalized
            and "page" in normalized
            and any(term in normalized for term in ("search", "find", "show", "recent", "latest", "updated"))
        )

    @classmethod
    def _is_trial_or_marketing_page(cls, title: str, text: str) -> bool:
        combined = f"{title}\n{text}".casefold()
        trial_markers = (
            "trial period",
            "available during a trial",
            "loom video",
            "mission control",
            "atlassian intelligence",
            "workspace insights",
            "during the trial period",
            "features available during a trial",
            "introducing features",
            "overview of features",
        )
        if any(marker in combined for marker in trial_markers):
            return True
        return bool(re.search(r"\btrial\b.*\bperiod\b|\bloom\b.*\bvideo\b", combined))

    @classmethod
    def _filter_relevant_confluence_results(cls, query: str, results: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if not cls._is_recent_workspace_update_query(query):
            return results
        filtered: list[dict[str, Any]] = []
        for result in results:
            title = str(result.get("title") or "")
            text = cls._extract_confluence_text(result)
            if not cls._is_trial_or_marketing_page(title, text):
                filtered.append(result)
        return filtered

    @staticmethod
    def _clean_confluence_query(query: str) -> str:
        cleaned = re.sub(r"\b(?:search|find|show|summarize|summarise|recent|latest|updated)\b", " ", query, flags=re.IGNORECASE)
        return " ".join(cleaned.split()) or query.strip()

    @staticmethod
    def _escape_cql(value: str) -> str:
        return value.replace("\\", "\\\\").replace('"', '\\"')

    def _fetch_jira_information(self, query: str) -> str:
        if not settings.jira_base_url or not settings.jira_api_token or not settings.jira_email:
            return ""

        try:
            search_jql = self._build_jira_query(query)
            if settings.jira_project_key:
                search_jql = self._apply_project_filter(search_jql, settings.jira_project_key)

            response = httpx.get(
                f"{settings.jira_base_url.rstrip('/')}/rest/api/3/search/jql",
                params={
                    "jql": search_jql,
                    "maxResults": 5,
                    "fields": "summary,status,assignee,updated,project,description",
                },
                headers={"Accept": "application/json"},
                auth=(settings.jira_email, settings.jira_api_token),
                timeout=10.0,
            )
            response.raise_for_status()
            payload = response.json()
            issues = payload.get("issues", [])
            if not issues and self._is_sprint_query(query):
                issues = self._fetch_sprint_issues()
            if not issues and self._is_overview_query(query):
                issues = self._fetch_recent_accessible_issues()
            if not issues:
                return "Jira: No matching issues were found for the provided request."

            return self._format_jira_issues(issues[:5], sort_results=not self._is_overview_query(query))
        except httpx.HTTPStatusError as error:
            if error.response.status_code == 400:
                return "Jira: No matching issues were found for the provided request or the configured project key is invalid."
            return f"Jira: Live Jira data could not be retrieved (HTTP {error.response.status_code})."
        except httpx.HTTPError:
            return "Jira: Live Jira data could not be retrieved right now."

    @staticmethod
    def _format_jira_issues(issues: list[dict[str, Any]], sort_results: bool = True) -> str:
        rows: list[tuple[str, str, str, str, str, str]] = []
        for issue in issues:
            fields = issue.get("fields", {})
            assignee = fields.get("assignee") or {}
            project = fields.get("project") or {}
            status = fields.get("status") or {}
            rows.append(
                (
                    str(issue.get("key") or "N/A"),
                    str(fields.get("summary") or "N/A"),
                    str(project.get("key") or "N/A"),
                    str(status.get("name") or "N/A"),
                    str(assignee.get("displayName") or "N/A"),
                    JiraConfluenceAgent._format_timestamp(fields.get("updated")),
                )
            )

        if sort_results:
            rows.sort(key=lambda row: row[0])
        lines = [
            f"### Jira Issues — {len(rows)} Results",
            "",
            "| Issue Key | Summary | Project | Status | Assignee | Updated |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
        lines.extend(f"| {' | '.join(row)} |" for row in rows)
        return "\n".join(lines)

    @staticmethod
    def _format_timestamp(value: Any) -> str:
        if not value:
            return "N/A"
        timestamp = str(value)
        match = re.match(r"^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})", timestamp)
        return match.group(1).replace("T", " ") if match else timestamp

    @staticmethod
    def _apply_project_filter(jql: str, project_key: str) -> str:
        project_key = project_key.strip()
        if not project_key:
            return jql
        if re.search(r"\bproject\s*=\s*", jql, flags=re.IGNORECASE):
            return jql
        if re.search(r"\bORDER\s+BY\b", jql, flags=re.IGNORECASE):
            base, order_clause = re.split(r"\s+ORDER\s+BY\s+", jql, flags=re.IGNORECASE, maxsplit=1)
            return f"project = {project_key} AND ({base}) ORDER BY {order_clause}"
        return f"project = {project_key} AND ({jql})"

    @staticmethod
    def _build_jira_query(query: str) -> str:
        normalized = " ".join(query.split()).casefold()

        if JiraConfluenceAgent._is_overview_query(query):
            if "assigned" in normalized or "my" in normalized and "assigned" in normalized:
                return "assignee = currentUser() ORDER BY updated DESC"
            return "assignee = currentUser() ORDER BY updated DESC"

        if "assigned" in normalized and "jira" in normalized:
            return "assignee = currentUser() ORDER BY updated DESC"
        if "my assigned" in normalized or "assigned to me" in normalized:
            return "assignee = currentUser() ORDER BY updated DESC"
        if "story" in normalized or "stories" in normalized:
            return "issuetype = Story ORDER BY updated DESC"
        if "task" in normalized or "tasks" in normalized:
            return "issuetype = Task ORDER BY updated DESC"
        if "bug" in normalized or "bugs" in normalized:
            return "issuetype = Bug ORDER BY updated DESC"
        if "blocker" in normalized or "blockers" in normalized:
            return "priority = Highest AND statusCategory != Done ORDER BY updated DESC"
        if "sprint" in normalized:
            return "sprint in openSprints() ORDER BY updated DESC"

        escaped_query = JiraConfluenceAgent._escape_jql_text(query)
        return (
            f'(summary ~ "{escaped_query}" OR description ~ "{escaped_query}" OR comment ~ "{escaped_query}")'
        )

    @staticmethod
    def _escape_jql_text(value: str) -> str:
        cleaned = " ".join(value.split())
        return cleaned.replace('"', '\\"')

    @staticmethod
    def _is_overview_query(query: str) -> bool:
        normalized_query = " ".join(query.casefold().split())
        if normalized_query in {
            "jira",
            "jira issues",
            "show jira issues",
            "show my jira issues",
            "show my recently updated jira issues",
            "recent project activity",
        }:
            return True

        has_jira_subject = (
            "jira" in normalized_query
            or "issue" in normalized_query
            or "story" in normalized_query
            or "task" in normalized_query
            or "backlog" in normalized_query
            or "work item" in normalized_query
        )
        has_recent_marker = any(marker in normalized_query for marker in ("latest", "recent", "newest", "updated"))
        return has_jira_subject and has_recent_marker

    @staticmethod
    def _is_sprint_query(query: str) -> bool:
        return "sprint" in " ".join(query.casefold().split())

    def _fetch_sprint_issues(self) -> list[dict[str, Any]]:
        """Return project issues linked to any sprint when no active sprint is available."""
        try:
            response = httpx.get(
                f"{settings.jira_base_url.rstrip('/')}/rest/api/3/search/jql",
                params={
                    "jql": "sprint is not EMPTY ORDER BY updated DESC",
                    "maxResults": 5,
                    "fields": "summary,status,assignee,updated,project,description",
                },
                headers={"Accept": "application/json"},
                auth=(settings.jira_email, settings.jira_api_token),
                timeout=10.0,
            )
            response.raise_for_status()
            return response.json().get("issues", [])
        except (httpx.HTTPError, ValueError, TypeError):
            return []

    def _fetch_recent_accessible_issues(self) -> list[dict[str, Any]]:
        """Return recent issues from projects visible to the authenticated user."""
        try:
            base_url = settings.jira_base_url.rstrip("/")
            auth = (settings.jira_email, settings.jira_api_token)
            projects_response = httpx.get(
                f"{base_url}/rest/api/3/project/search",
                params={"maxResults": 50},
                headers={"Accept": "application/json"},
                auth=auth,
                timeout=10.0,
            )
            projects_response.raise_for_status()
            project_keys = [
                project.get("key")
                for project in projects_response.json().get("values", [])
                if project.get("key")
            ]
            if not project_keys:
                return []

            project_jql = f"project in ({', '.join(project_keys)}) ORDER BY updated DESC"
            issues_response = httpx.get(
                f"{base_url}/rest/api/3/search/jql",
                params={
                    "jql": project_jql,
                    "maxResults": 5,
                    "fields": "summary,status,assignee,updated,project,description",
                },
                headers={"Accept": "application/json"},
                auth=auth,
                timeout=10.0,
            )
            issues_response.raise_for_status()
            return issues_response.json().get("issues", [])
        except (httpx.HTTPError, ValueError, TypeError):
            return []

    def _fetch_ourtool_information(self, query: str) -> str:
        if not settings.ourtool_base_url:
            return ""

        try:
            request_url = settings.ourtool_base_url.rstrip("/")
            separator = "&" if "?" in request_url else "?"
            request_url = f"{request_url}{separator}q={query}"

            headers: dict[str, str] = {"Accept": "application/json"}
            if settings.ourtool_api_key:
                headers["Authorization"] = f"Bearer {settings.ourtool_api_key}"

            response = httpx.get(request_url, headers=headers, timeout=10.0)
            response.raise_for_status()
            payload = response.json()
            return self._format_tools_payload(payload)
        except Exception:
            return "OurTool: Live external tool data could not be retrieved right now."

    def _format_tools_payload(self, payload: Any) -> str:
        if isinstance(payload, dict):
            if "items" in payload and isinstance(payload["items"], list):
                items = payload["items"]
            elif "results" in payload and isinstance(payload["results"], list):
                items = payload["results"]
            else:
                items = [payload]
        elif isinstance(payload, list):
            items = payload
        else:
            items = []

        if not items:
            return "OurTool: No matching items were returned by the connected tool."

        lines = ["OurTool exact results:"]
        for item in items[:5]:
            if isinstance(item, dict):
                title = item.get("title") or item.get("name") or item.get("id") or "Untitled"
                description = item.get("description") or item.get("summary") or item.get("status") or "No additional detail"
                lines.append(f"- {title}: {description}")
            else:
                lines.append(f"- {item}")

        return "\n".join(lines)
