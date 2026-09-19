from backend.app.api.routes.jira import _fallback_test_cases


def test_fallback_generates_exactly_five_complete_test_cases() -> None:
    cases = _fallback_test_cases(
        {
            "title": "Customer verification",
            "description": "Customers must complete identity checks.",
            "acceptance_criteria": "The verification result is recorded.",
        }
    )

    assert len(cases) == 5
    required = {"name", "objective", "preconditions", "steps", "test_data", "expected_result", "priority"}
    assert all(required.issubset(case) and case["steps"] for case in cases)