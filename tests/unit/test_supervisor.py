from backend.orchestrator.supervisor import Supervisor, classify_request


def test_supervisor_routes_policy_requests_through_the_graph() -> None:
    result = Supervisor().handle("session-1", "What is the policy for this request?")

    assert "document agent" not in result
    assert "policy guidance" in result


def test_supervisor_routes_email_requests_to_the_email_agent() -> None:
    result = Supervisor().handle("session-2", "Draft an Outlook email to the customer")

    assert "email agent" not in result
    assert "MailMate could not access the mailbox" in result


def test_supervisor_routes_mailmate_and_latest_mail_requests_to_email() -> None:
    assert classify_request({"message": "MailMate: show the latest one"})["route"] == "email"
    assert classify_request({"message": "Read my latest mail"})["route"] == "email"


def test_supervisor_honors_explicit_confluence_agent_context() -> None:
    assert classify_request({"message": "Find the onboarding decision", "agent": "confluence"})["route"] == "confluence"


def test_supervisor_routes_retail_lending_questions_to_knowledge() -> None:
    assert classify_request({"message": "What are the rules of retail lending?"})["route"] == "document"


def test_supervisor_keeps_assistant_responses_user_facing() -> None:
    result = Supervisor().handle("session-3", "what are policies for home loan")

    assert "assistant agent responded" not in result
    assert "Approved knowledge used" not in result
    assert "home-loan" in result.lower()


def test_supervisor_includes_retrieved_approved_guidance() -> None:
    result = Supervisor().handle("session-4", "What are the identity checks for customer verification?")

    assert result.startswith("- ")
    assert "Source:" not in result
    assert any(term in result.lower() for term in ("identity", "passcode", "verification", "account detail"))
    assert "one-time passcode" in result


def test_supervisor_answers_retail_banking_typo_with_grounded_guidance() -> None:
    result = Supervisor().handle("session-5", "what is reail banking?")

    text = result.lower()
    assert "retail banking" in text
    assert "not available in the approved knowledge base" not in text
