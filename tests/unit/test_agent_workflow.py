from types import SimpleNamespace

from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from app.agent import (
    REVIEW_THRESHOLD,
    ExpenseReport,
    app,
    auto_approve,
    request_human_approval,
    route_expense,
)


def make_expense(amount: float) -> ExpenseReport:
    return ExpenseReport(
        amount=amount,
        submitter="alex@example.com",
        category="travel",
        description="Conference travel",
        date="2026-11-20",
    )


def test_expense_below_threshold_routes_to_auto_approval() -> None:
    ctx = SimpleNamespace(state={})

    routed = route_expense(make_expense(REVIEW_THRESHOLD - 0.01), ctx)
    approved = auto_approve(routed.output)

    assert routed.actions.route == "AUTO_APPROVE"
    assert approved.output["status"] == "approved"
    assert approved.output["amount"] == REVIEW_THRESHOLD - 0.01


def test_expense_at_threshold_routes_to_review() -> None:
    ctx = SimpleNamespace(state={})

    routed = route_expense(make_expense(REVIEW_THRESHOLD), ctx)

    assert routed.actions.route == "REVIEW"
    assert ctx.state["expense_report"]["amount"] == REVIEW_THRESHOLD


def test_low_value_json_event_completes_without_model_access() -> None:
    session_service = InMemorySessionService()
    session = session_service.create_session_sync(user_id="test", app_name="test")
    runner = Runner(
        app=app,
        session_service=session_service,
        app_name="test",
    )
    message = types.Content(
        role="user",
        parts=[types.Part.from_text(text=make_expense(42.5).model_dump_json())],
    )

    events = list(
        runner.run(
            user_id="test",
            session_id=session.id,
            new_message=message,
        )
    )

    assert any(
        event.output == {"status": "approved", **make_expense(42.5).model_dump()}
        for event in events
    )


def test_review_path_requests_human_approval() -> None:
    expense = make_expense(REVIEW_THRESHOLD).model_dump()
    risk_assessment = {"risk_level": "medium", "risk_factors": [], "summary": "Review"}
    ctx = SimpleNamespace(
        state={"expense_report": expense, "risk_assessment": risk_assessment}
    )

    request = next(request_human_approval(ctx))

    assert request.payload == {
        "expense_report": expense,
        "risk_assessment": risk_assessment,
    }
