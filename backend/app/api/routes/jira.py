"""Jira issue and test-case endpoints."""

import json
import logging
import re
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
import httpx

from backend.agents.jira_confluence_agent import JiraConfluenceAgent
from backend.app.config import settings

router = APIRouter(prefix="/jira", tags=["jira"])
logger = logging.getLogger(__name__)


class JiraIssueCreateRequest(BaseModel):
    issue_type: str = Field(pattern="^(Task|Story)$")
    summary: str = Field(min_length=1)


class JiraTestCase(BaseModel):
    name: str = Field(min_length=1)
    objective: str = Field(min_length=1)
    preconditions: str = Field(min_length=1)
    steps: list[str] = Field(min_length=1)
    test_data: str = "Not applicable"
    expected_result: str = Field(min_length=1)
    priority: str = Field(pattern="^(Highest|High|Medium|Low)$")


class JiraTestCaseRequest(BaseModel):
    story_key: str = Field(pattern=r"^[A-Z][A-Z0-9]+-\d+$")
    test_cases: list[JiraTestCase] = Field(default_factory=list, max_length=5)


def _jira_auth() -> tuple[str, str]:
    return settings.jira_email, settings.jira_api_token


def _story_details(story_key: str) -> dict[str, Any]:
    if not settings.jira_base_url or not settings.jira_email or not settings.jira_api_token:
        raise HTTPException(status_code=503, detail="Jira integration is not configured.")
    response = httpx.get(
        f"{settings.jira_base_url.rstrip('/')}/rest/api/3/issue/{story_key}",
        params={"fields": "summary,description,issuetype,priority,assignee,status,updated,labels,project"},
        headers={"Accept": "application/json"},
        auth=_jira_auth(),
        timeout=15.0,
    )
    if response.status_code == 404:
        raise HTTPException(status_code=404, detail=f"Jira story {story_key} could not be found or is not visible.")
    try:
        response.raise_for_status()
    except httpx.HTTPStatusError as error:
        raise HTTPException(status_code=502, detail=f"Jira story lookup failed (HTTP {error.response.status_code}).") from error
    fields = response.json().get("fields", {})
    description = JiraConfluenceAgent._flatten_description(fields.get("description"))
    acceptance_match = re.search(r"acceptance criteria\s*[:\-]?\s*(.*)", description, flags=re.IGNORECASE | re.DOTALL)
    return {
        "key": story_key,
        "title": str(fields.get("summary") or ""),
        "description": description,
        "acceptance_criteria": acceptance_match.group(1).strip() if acceptance_match else "Not explicitly provided",
        "metadata": {
            "issue_type": (fields.get("issuetype") or {}).get("name", ""),
            "priority": (fields.get("priority") or {}).get("name", ""),
            "assignee": (fields.get("assignee") or {}).get("displayName", "Unassigned"),
            "status": (fields.get("status") or {}).get("name", ""),
            "updated": fields.get("updated", ""),
            "project": (fields.get("project") or {}).get("key", settings.jira_project_key),
            "labels": fields.get("labels") or [],
        },
    }


def _fallback_test_cases(story: dict[str, Any]) -> list[dict[str, Any]]:
    title = story["title"]
    context = story["description"] or story["acceptance_criteria"]
    return [
        {"name": f"Happy path - {title}", "objective": "Verify the user story works for valid input.", "preconditions": "User has the required access and the feature is available.", "steps": ["Open the feature described by the story.", "Enter valid test data.", "Submit the request."], "test_data": context[:500] or "Valid data", "expected_result": "The request completes successfully and the expected outcome is displayed.", "priority": "High"},
        {"name": f"Required validation - {title}", "objective": "Verify required fields and business rules are enforced.", "preconditions": "The feature is available and the user can submit a request.", "steps": ["Open the feature.", "Leave a required value blank or violate a stated rule.", "Submit the request."], "test_data": "Missing or invalid required value", "expected_result": "A clear validation message is shown and invalid data is not accepted.", "priority": "High"},
        {"name": f"Unauthorized access - {title}", "objective": "Verify users without the required permission cannot complete the action.", "preconditions": "A user account without the required permission is available.", "steps": ["Sign in as the restricted user.", "Open the feature or direct URL.", "Attempt the story action."], "test_data": "Restricted user account", "expected_result": "Access is denied and no unauthorized change is made.", "priority": "High"},
        {"name": f"Boundary and error handling - {title}", "objective": "Verify boundary values and service errors are handled safely.", "preconditions": "The feature is available and boundary data can be supplied.", "steps": ["Submit the smallest and largest supported values.", "Repeat with an invalid or unavailable dependency.", "Observe the response."], "test_data": "Boundary values and simulated dependency error", "expected_result": "Supported boundaries work and failures show an actionable message without corrupting data.", "priority": "Medium"},
        {"name": f"Persistence and regression - {title}", "objective": "Verify the result is persisted and remains correct after reload.", "preconditions": "The happy-path action can be completed.", "steps": ["Complete the story action with valid data.", "Reload or reopen the relevant record.", "Verify the saved result and related workflow."], "test_data": "Valid story data", "expected_result": "The result is saved, traceable to the story, and remains correct after reload.", "priority": "Medium"},
    ]


def _generate_test_cases(story: dict[str, Any]) -> list[dict[str, Any]]:
    fallback = _fallback_test_cases(story)
    api_key = settings.llm_api_key or settings.openai_api_key
    if not api_key or settings.llm_provider.casefold() == "ollama":
        return fallback
    prompt = (
        "Generate exactly 5 Jira test cases for this user story. Return JSON only as an array. "
        "Each object must have name, objective, preconditions, steps (array), test_data, expected_result, priority. "
        "Priority must be Highest, High, Medium, or Low. Do not invent requirements.\n\n"
        f"Title: {story['title']}\nDescription: {story['description'][:6000]}\nAcceptance criteria: {story['acceptance_criteria'][:3000]}"
    )
    try:
        response = httpx.post(
            f"{settings.openai_base_url.rstrip('/')}/chat/completions",
            headers={"Authorization": f"Bearer {api_key}"},
            json={"model": settings.llm_model, "messages": [{"role": "user", "content": prompt}], "max_completion_tokens": 2400},
            timeout=60.0,
        )
        response.raise_for_status()
        text = str(response.json()["choices"][0]["message"]["content"]).strip()
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.IGNORECASE)
        generated = json.loads(text)
        if isinstance(generated, list) and len(generated) == 5:
            return [JiraTestCase.model_validate(item).model_dump() for item in generated]
    except (httpx.HTTPError, KeyError, TypeError, ValueError, json.JSONDecodeError):
        pass
    return fallback


@router.post("/issues")
def create_jira_issue(request: JiraIssueCreateRequest) -> dict[str, str]:
    result = JiraConfluenceAgent()._create_issue(request.issue_type, request.summary.strip())
    if not result.startswith(f"Jira {request.issue_type} created successfully:"):
        raise HTTPException(status_code=502, detail=result)
    issue_url = result.split("Open issue: ", 1)[-1].strip()
    return {"status": "created", "message": result, "url": issue_url}


@router.get("/issues/{story_key}")
def get_jira_story(story_key: str) -> dict[str, Any]:
    return _story_details(story_key)


@router.post("/test-cases/generate")
def generate_jira_test_cases(request: JiraTestCaseRequest) -> dict[str, Any]:
    story = _story_details(request.story_key)
    return {"story": story, "test_cases": _generate_test_cases(story)}


@router.post("/test-cases")
def create_jira_test_cases(request: JiraTestCaseRequest) -> dict[str, Any]:
    if not request.test_cases:
        raise HTTPException(status_code=400, detail="At least one test case is required.")
    story = _story_details(request.story_key)
    base_url = settings.jira_base_url.rstrip("/")
    created: list[dict[str, str]] = []
    failures: list[str] = []
    for test_case in request.test_cases:
        description = "\n".join([
            f"Traceability: generated from {request.story_key}",
            f"Objective: {test_case.objective}",
            f"Preconditions: {test_case.preconditions}",
            "Test steps:",
            *[f"{index}. {step}" for index, step in enumerate(test_case.steps, 1)],
            f"Test data: {test_case.test_data}",
            f"Expected result: {test_case.expected_result}",
            f"Priority: {test_case.priority}",
        ])
        try:
            response = httpx.post(
                f"{base_url}/rest/api/3/issue",
                headers={"Accept": "application/json", "Content-Type": "application/json"},
                auth=_jira_auth(),
                json={"fields": {"project": {"key": story["metadata"].get("project", settings.jira_project_key)}, "summary": f"[Test Case] {test_case.name}", "description": {"type": "doc", "version": 1, "content": [{"type": "paragraph", "content": [{"type": "text", "text": description}]}]}, "issuetype": {"name": "Task"}}},
                timeout=15.0,
            )
            response.raise_for_status()
            issue_key = str(response.json().get("key") or "").strip()
            if not issue_key:
                raise ValueError("Jira returned no issue key")
            link_response = httpx.post(
                f"{base_url}/rest/api/3/issueLink",
                headers={"Accept": "application/json", "Content-Type": "application/json"},
                auth=_jira_auth(),
                json={"type": {"name": "Relates"}, "inwardIssue": {"key": request.story_key}, "outwardIssue": {"key": issue_key}},
                timeout=15.0,
            )
            link_response.raise_for_status()
            created.append({"key": issue_key, "url": f"{base_url}/browse/{issue_key}"})
        except (httpx.HTTPError, ValueError) as error:
            logger.warning("Jira test case creation failed for %s (%s): %s", request.story_key, test_case.name, error)
            failures.append(f"{test_case.name}: {error}")
    if failures:
        raise HTTPException(status_code=502, detail=f"Created {len(created)} test cases, but some operations failed: {'; '.join(failures)}")
    return {"status": "created", "story_key": request.story_key, "created": created}