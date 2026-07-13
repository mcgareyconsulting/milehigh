"""The tool-agent loop: tool execution, metrics accumulation, no-key stub — all offline."""
from unittest.mock import patch

from app.brain.bb_chat import agent


def test_no_api_key_returns_stub(app):
    with app.app_context(), patch.object(agent.cfg, "ANTHROPIC_API_KEY", None):
        result = agent.run_chat([], "which submittals are in Colton's court?")
    assert result["configured"] is False
    assert result["metrics"]["model"] == "stub"


def test_tool_loop_runs_search_submittals_and_accumulates_metrics(app):
    """First API call asks for search_submittals(ball_in_court=Colton); the real read-only
    tool runs against the in-memory DB; the second call gives the final answer."""
    from app.models import Submittals, db
    with app.app_context():
        db.session.add(Submittals(submittal_id="S1", project_number="290",
                                  ball_in_court="Colton Reyes", status="Open",
                                  title="Anchor bolts", submittal_drafting_status=""))
        db.session.flush()

        body_tool = {
            "model": "claude-sonnet-5", "stop_reason": "tool_use",
            "usage": {"input_tokens": 200, "output_tokens": 30},
            "content": [{"type": "tool_use", "id": "t1", "name": "search_submittals",
                         "input": {"ball_in_court": "Colton"}}],
        }
        body_final = {
            "model": "claude-sonnet-5", "stop_reason": "end_turn",
            "usage": {"input_tokens": 260, "output_tokens": 40},
            "content": [{"type": "text", "text": "Colton has 1 open submittal: Anchor bolts (290)."}],
        }
        with patch.object(agent.cfg, "ANTHROPIC_API_KEY", "k"), \
                patch.object(agent, "_post", side_effect=[(body_tool, "r1"), (body_final, "r2")]):
            result = agent.run_chat([], "what's in Colton's court?", user_id=1)

    assert result["answer"].startswith("Colton has 1 open submittal")
    m = result["metrics"]
    assert m["tool_calls"] == 1
    assert m["input_tokens"] == 460          # summed across both calls
    assert m["request_ids"] == ["r1", "r2"]
    assert m["cost_usd"] > 0


def test_user_scoped_tool_gets_user_id(app):
    """get_my_notifications is user-scoped — the loop must pass the session user_id, not a
    model-supplied one."""
    with app.app_context():
        captured = {}

        def fake_execute(name, args, context=None):
            captured["name"] = name
            captured["ctx"] = context
            return {"results": []}

        body_tool = {"model": "claude-sonnet-5", "stop_reason": "tool_use",
                     "usage": {"input_tokens": 10, "output_tokens": 5},
                     "content": [{"type": "tool_use", "id": "t1", "name": "get_my_notifications", "input": {}}]}
        body_final = {"model": "claude-sonnet-5", "stop_reason": "end_turn",
                      "usage": {"input_tokens": 10, "output_tokens": 5},
                      "content": [{"type": "text", "text": "Nothing new."}]}
        with patch.object(agent.cfg, "ANTHROPIC_API_KEY", "k"), \
                patch.object(agent.tools, "execute_tool", side_effect=fake_execute), \
                patch.object(agent, "_post", side_effect=[(body_tool, "r1"), (body_final, "r2")]):
            agent.run_chat([], "any notifications for me?", user_id=42)

    assert captured["name"] == "get_my_notifications"
    assert captured["ctx"] == {"user_id": 42}
