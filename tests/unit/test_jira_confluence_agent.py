from types import SimpleNamespace

from backend.agents.jira_confluence_agent import JiraConfluenceAgent


class FakeResponse:
    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, object]:
        return {
            "issues": [
                {
                    "key": "DEMO-1",
                    "fields": {
                        "summary": "Fix Jira integration",
                        "project": {"key": "DEMO"},
                        "status": {"name": "To Do"},
                        "assignee": {"displayName": "Ravi"},
                        "updated": "2026-09-15T10:00:00.000+0000",
                    },
                }
            ]
        }


class CreatedResponse:
    status_code = 201

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, str]:
        return {"key": "DEMO-42"}


def test_jira_agent_uses_supported_jql_search_endpoint(monkeypatch) -> None:
    settings = SimpleNamespace(
        jira_base_url="https://example.atlassian.net",
        jira_email="user@example.com",
        jira_api_token="token",
        jira_project_key="DEMO",
    )
    request: dict[str, object] = {}

    def fake_get(url: str, **kwargs: object) -> FakeResponse:
        request["url"] = url
        request.update(kwargs)
        return FakeResponse()

    monkeypatch.setattr("backend.agents.jira_confluence_agent.settings", settings)
    monkeypatch.setattr("backend.agents.jira_confluence_agent.httpx.get", fake_get)

    result = JiraConfluenceAgent()._fetch_jira_information("integration")

    assert request["url"] == "https://example.atlassian.net/rest/api/3/search/jql"
    assert request["params"] == {
        "jql": 'project = DEMO AND ((summary ~ "integration" OR description ~ "integration" OR comment ~ "integration"))',
        "maxResults": 5,
        "fields": "summary,status,assignee,updated,project,description",
    }
    assert request["headers"] == {"Accept": "application/json"}
    assert "| DEMO-1 | Fix Jira integration | DEMO | To Do | Ravi | 2026-09-15 10:00:00 |" in result


def test_jira_agent_uses_assigned_issue_overview_for_generic_jira_request(monkeypatch) -> None:
    settings = SimpleNamespace(
        jira_base_url="https://example.atlassian.net",
        jira_email="user@example.com",
        jira_api_token="token",
        jira_project_key="",
    )
    request: dict[str, object] = {}

    def fake_get(url: str, **kwargs: object) -> FakeResponse:
        request.update(kwargs)
        return FakeResponse()

    monkeypatch.setattr("backend.agents.jira_confluence_agent.settings", settings)
    monkeypatch.setattr("backend.agents.jira_confluence_agent.httpx.get", fake_get)

    JiraConfluenceAgent()._fetch_jira_information("Show my recently updated Jira issues")

    assert request["params"] == {
        "jql": "assignee = currentUser() ORDER BY updated DESC",
        "maxResults": 5,
        "fields": "summary,status,assignee,updated,project,description",
    }


def test_jira_agent_treats_latest_story_request_as_overview(monkeypatch) -> None:
    settings = SimpleNamespace(
        jira_base_url="https://example.atlassian.net",
        jira_email="user@example.com",
        jira_api_token="token",
        jira_project_key="",
    )
    request: dict[str, object] = {}

    def fake_get(url: str, **kwargs: object) -> FakeResponse:
        request.update(kwargs)
        return FakeResponse()

    monkeypatch.setattr("backend.agents.jira_confluence_agent.settings", settings)
    monkeypatch.setattr("backend.agents.jira_confluence_agent.httpx.get", fake_get)

    JiraConfluenceAgent()._fetch_jira_information("tell me latest jira story")

    assert request["params"]["jql"] == "assignee = currentUser() ORDER BY updated DESC"


def test_jira_agent_falls_back_to_recent_accessible_project_issues(monkeypatch) -> None:
    settings = SimpleNamespace(
        jira_base_url="https://example.atlassian.net",
        jira_email="user@example.com",
        jira_api_token="token",
        jira_project_key="",
    )
    requests: list[dict[str, object]] = []

    class EmptyResponse(FakeResponse):
        def json(self) -> dict[str, object]:
            return {"issues": []}

    class ProjectsResponse(FakeResponse):
        def json(self) -> dict[str, object]:
            return {"values": [{"key": "DEMO"}]}

    def fake_get(url: str, **kwargs: object) -> FakeResponse:
        requests.append({"url": url, **kwargs})
        if url.endswith("/project/search"):
            return ProjectsResponse()
        if len(requests) == 1:
            return EmptyResponse()
        return FakeResponse()

    monkeypatch.setattr("backend.agents.jira_confluence_agent.settings", settings)
    monkeypatch.setattr("backend.agents.jira_confluence_agent.httpx.get", fake_get)

    result = JiraConfluenceAgent()._fetch_jira_information("Jira")

    assert requests[1]["url"] == "https://example.atlassian.net/rest/api/3/project/search"
    assert requests[2]["params"] == {
        "jql": "project in (DEMO) ORDER BY updated DESC",
        "maxResults": 5,
        "fields": "summary,status,assignee,updated,project,description",
    }
    assert "| DEMO-1 | Fix Jira integration | DEMO | To Do | Ravi | 2026-09-15 10:00:00 |" in result


def test_jira_agent_creates_task_from_natural_language(monkeypatch) -> None:
    settings = SimpleNamespace(
        jira_base_url="https://example.atlassian.net",
        jira_email="user@example.com",
        jira_api_token="token",
        jira_project_key="DEMO",
    )
    request: dict[str, object] = {}

    def fake_post(url: str, **kwargs: object) -> CreatedResponse:
        request["url"] = url
        request.update(kwargs)
        return CreatedResponse()

    monkeypatch.setattr("backend.agents.jira_confluence_agent.settings", settings)
    monkeypatch.setattr("backend.agents.jira_confluence_agent.httpx.post", fake_post)

    result = JiraConfluenceAgent().run(SimpleNamespace(message="Create a task: Add audit logging"))

    assert request["url"] == "https://example.atlassian.net/rest/api/3/issue"
    assert request["json"]["fields"]["project"] == {"key": "DEMO"}
    assert request["json"]["fields"]["issuetype"] == {"name": "Task"}
    assert request["json"]["fields"]["summary"] == "Add audit logging"
    assert "DEMO-42" in result


def test_jira_agent_analyzes_story_text() -> None:
    context = SimpleNamespace(
        message="Analyze story: As a banker, I want to review KYC alerts so that I can approve safe accounts. Given an alert, when I review it, then the decision is recorded."
    )

    result = JiraConfluenceAgent().run(context)

    assert "User story format: Ready" in result
    assert "Acceptance criteria: Present" in result
    assert "Expected behavior: Defined" in result


def test_jira_agent_creates_story_from_confluence_context(monkeypatch) -> None:
    settings = SimpleNamespace(
        jira_base_url="https://example.atlassian.net",
        jira_email="user@example.com",
        jira_api_token="token",
        jira_project_key="DEMO",
        llm_api_key="",
        llm_provider="openai",
        openai_base_url="https://example.openai.com/v1",
        llm_model="gpt-4o-mini",
    )
    request: dict[str, object] = {}

    def fake_post(url: str, **kwargs: object) -> CreatedResponse:
        request["url"] = url
        request.update(kwargs)
        return CreatedResponse()

    monkeypatch.setattr("backend.agents.jira_confluence_agent.settings", settings)
    monkeypatch.setattr("backend.agents.jira_confluence_agent.httpx.post", fake_post)

    result = JiraConfluenceAgent().run(
        SimpleNamespace(
            message="Create a story in Jira: Review Confluence page: Customer Verification | Context: Employees must complete two approved identity checks. Use a one-time passcode.",
            agent="jira",
        )
    )

    assert request["url"] == "https://example.atlassian.net/rest/api/3/issue"
    assert request["json"]["fields"]["issuetype"] == {"name": "Story"}
    assert "Customer Verification" in request["json"]["fields"]["summary"]
    assert "one-time passcode" in str(request["json"]["fields"]["description"]).lower()
    assert "DEMO-42" in result


def test_jira_agent_fetches_confluence_page_content(monkeypatch) -> None:
    settings = SimpleNamespace(
        jira_base_url="https://example.atlassian.net",
        jira_email="user@example.com",
        jira_api_token="token",
        jira_project_key="",
    )
    request: dict[str, object] = {}

    class ConfluenceResponse(FakeResponse):
        def json(self) -> dict[str, object]:
            return {
                "results": [
                    {
                        "title": "Customer Verification Policy",
                        "id": "101",
                        "body": {"storage": {"value": "<p>Employees must complete two approved identity checks.</p><p>Use a one-time passcode.</p>"}},
                    }
                ]
            }

    def fake_get(url: str, **kwargs: object) -> FakeResponse:
        request["url"] = url
        request.update(kwargs)
        return ConfluenceResponse()

    monkeypatch.setattr("backend.agents.jira_confluence_agent.settings", settings)
    monkeypatch.setattr("backend.agents.jira_confluence_agent.httpx.get", fake_get)

    result = JiraConfluenceAgent()._fetch_confluence_information("Customer Verification Policy")

    assert request["url"] == "https://example.atlassian.net/rest/api/content/search"
    assert "Customer Verification Policy" in result
    assert "two approved identity checks" in result
    assert "one-time passcode" in result


def test_confluence_agent_filters_trial_and_marketing_pages_for_recent_updates(monkeypatch) -> None:
    settings = SimpleNamespace(
        confluence_base_url="https://example.atlassian.net/wiki",
        jira_base_url="",
        jira_email="user@example.com",
        jira_api_token="token",
    )

    class SearchResponse(FakeResponse):
        def json(self) -> dict[str, object]:
            return {
                "results": [
                    {
                        "title": "Mission Control",
                        "id": "201",
                        "body": {"storage": {"value": "<p>Access workspace insights and controls from a single location.</p><p>Available during the trial period.</p>"}},
                    },
                    {
                        "title": "Atlassian Intelligence",
                        "id": "202",
                        "body": {"storage": {"value": "<p>Summarize pages and assist with writing.</p><p>Demonstrated in a Loom video during the trial period.</p>"}},
                    },
                ]
            }

    def fake_get(url: str, **kwargs: object) -> FakeResponse:
        return SearchResponse()

    monkeypatch.setattr("backend.agents.jira_confluence_agent.settings", settings)
    monkeypatch.setattr("backend.agents.jira_confluence_agent.httpx.get", fake_get)

    result = JiraConfluenceAgent()._fetch_confluence_information("Search Confluence pages for recent workspace updates")

    assert "No relevant pages were found" in result


def test_confluence_agent_reads_exact_page_from_pasted_url(monkeypatch) -> None:
    settings = SimpleNamespace(
        confluence_base_url="https://example.atlassian.net/wiki",
        jira_base_url="",
        jira_email="user@example.com",
        jira_api_token="token",
    )

    class PageResponse(FakeResponse):
        def json(self) -> dict[str, object]:
            return {
                "title": "Customer Verification Policy",
                "body": {"storage": {"value": "<p>Use two approved identity checks.</p>"}},
                "version": {"number": 3},
            }

    request: dict[str, object] = {}

    def fake_get(url: str, **kwargs: object) -> FakeResponse:
        request["url"] = url
        request.update(kwargs)
        return PageResponse()

    monkeypatch.setattr("backend.agents.jira_confluence_agent.settings", settings)
    monkeypatch.setattr("backend.agents.jira_confluence_agent.httpx.get", fake_get)

    result = JiraConfluenceAgent()._fetch_confluence_information(
        "https://example.atlassian.net/wiki/pages/101/Customer-Verification-Policy"
    )

    assert request["url"] == "https://example.atlassian.net/wiki/rest/api/content/101"
    assert "Customer Verification Policy" in result
    assert "two approved identity checks" in result


def test_confluence_agent_summarizes_with_grounded_llm(monkeypatch) -> None:
    settings = SimpleNamespace(
        llm_provider="openai",
        llm_model="gpt-4o-mini",
        llm_api_key="test-key",
        openai_api_key="",
        openai_base_url="https://api.openai.com/v1",
    )

    class SummaryResponse(FakeResponse):
        def json(self) -> dict[str, object]:
            return {"choices": [{"message": {"content": "The page highlights workspace insights. [page 163981]"}}]}

    request: dict[str, object] = {}

    def fake_post(url: str, **kwargs: object) -> FakeResponse:
        request["url"] = url
        request.update(kwargs)
        return SummaryResponse()

    monkeypatch.setattr("backend.agents.jira_confluence_agent.settings", settings)
    monkeypatch.setattr("backend.agents.jira_confluence_agent.httpx.post", fake_post)

    result = JiraConfluenceAgent()._summarize_confluence(
        "Summarize page 163981",
        "[page 163981]\nMission control provides workspace insights.",
    )

    assert result == "The page highlights workspace insights. [page 163981]"
    assert request["url"] == "https://api.openai.com/v1/chat/completions"
    assert "Mission control" in request["json"]["messages"][1]["content"]
    assert request["json"]["max_completion_tokens"] == 500
    assert "temperature" not in request["json"]


def test_jira_query_uses_valid_summary_and_description_search() -> None:
    query = JiraConfluenceAgent._build_jira_query("Search Confluence pages for recent workspace updates")

    assert "summary" in query.lower()
    assert "description" in query.lower()
    assert "text ~" not in query.lower()


def test_jira_query_handles_story_task_bug_blocker_and_sprint_intent() -> None:
    assert "issuetype = story" in JiraConfluenceAgent._build_jira_query("Show Jira stories").lower()
    assert "issuetype = task" in JiraConfluenceAgent._build_jira_query("Show Jira tasks").lower()
    assert "issuetype = bug" in JiraConfluenceAgent._build_jira_query("Show Jira bugs").lower()
    assert "priority = highest" in JiraConfluenceAgent._build_jira_query("Show open Jira blockers").lower()
    assert "sprint in opensprints()" in JiraConfluenceAgent._build_jira_query("Show current sprint status").lower()
    assert "assignee = currentuser()" in JiraConfluenceAgent._build_jira_query("Show my assigned Jira issues").lower()


def test_jira_story_queries_ignore_confluence_results(monkeypatch) -> None:
    settings = SimpleNamespace(
        jira_base_url="https://example.atlassian.net",
        jira_email="user@example.com",
        jira_api_token="token",
        jira_project_key="DEMO",
        confluence_base_url="https://example.atlassian.net/wiki",
        llm_provider="openai",
        llm_model="gpt-4o-mini",
        llm_api_key="test-key",
        openai_api_key="",
        openai_base_url="https://api.openai.com/v1",
    )
    jira_calls: list[str] = []
    confluence_calls: list[str] = []

    class JiraResponse(FakeResponse):
        def json(self) -> dict[str, object]:
            return {"issues": [{"key": "DEMO-7", "fields": {"summary": "Add onboarding flow", "project": {"key": "DEMO"}, "status": {"name": "To Do"}, "assignee": {"displayName": "Ravi"}, "updated": "2026-09-17T09:00:00.000+0000"}}]}

    def fake_get(url: str, **kwargs: object) -> FakeResponse:
        if url.endswith("/rest/api/3/search/jql"):
            jira_calls.append(url)
            return JiraResponse()
        if url.endswith("/rest/api/content/search"):
            confluence_calls.append(url)
            return FakeResponse({"results": [{"title": "Product requirements", "id": "196765", "body": {"storage": {"value": "<p>Target date</p><p>Objective</p>"}}}]})
        return FakeResponse({})

    monkeypatch.setattr("backend.agents.jira_confluence_agent.settings", settings)
    monkeypatch.setattr("backend.agents.jira_confluence_agent.httpx.get", fake_get)

    result = JiraConfluenceAgent().run(SimpleNamespace(message="Show Jira stories", agent="jira_confluence"))

    assert jira_calls and not confluence_calls
    assert "DEMO-7" in result
    assert "Add onboarding flow" in result


def test_confluence_agent_parses_page_creation_request() -> None:
    assert JiraConfluenceAgent._parse_confluence_write_request("Create a Confluence page: Runbook | Restart the service") == (
        "create",
        "Runbook",
        "Restart the service",
    )


def test_confluence_agent_parses_page_update_request() -> None:
    assert JiraConfluenceAgent._parse_confluence_write_request("Update Confluence page 101: New approval flow | Use two checks") == (
        "update",
        "Use two checks",
        "101",
    )
