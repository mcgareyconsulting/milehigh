"""The agent makes one grounded call per turn (offline via a mocked _post)."""
from unittest.mock import patch

from app.brain.bb_chat import agent


def test_no_api_key_returns_stub(app):
    with app.app_context(), patch.object(agent.cfg, "ANTHROPIC_API_KEY", None):
        result = agent.run_chat([], "summarize 290-153", bundle={"found": True})
    assert result["configured"] is False
    assert result["metrics"]["model"] == "stub"


def test_single_shot_answer_and_metrics(app):
    body = {
        "model": "claude-sonnet-5",
        "stop_reason": "end_turn",
        "usage": {"input_tokens": 1200, "output_tokens": 180},
        "content": [{"type": "text", "text": "Release 290-153 is in Cut Start; one submittal is with the GC."}],
    }
    bundle = {"found": True, "releases": [{"job_release": "290-153"}], "timeline": []}

    with app.app_context(), \
            patch.object(agent.cfg, "ANTHROPIC_API_KEY", "k"), \
            patch.object(agent, "_post", return_value=(body, "req_xyz")) as post:
        result = agent.run_chat([], "summarize 290-153", bundle=bundle, user_id=3)

    # The bundle was attached to the user turn inside a <lifecycle_data> block.
    sent_messages = post.call_args[0][0]
    assert "<lifecycle_data>" in sent_messages[-1]["content"]
    assert "290-153" in sent_messages[-1]["content"]

    assert result["configured"] is True
    assert "Cut Start" in result["answer"]
    m = result["metrics"]
    assert m["input_tokens"] == 1200 and m["output_tokens"] == 180
    assert m["request_ids"] == ["req_xyz"]
    assert m["cost_usd"] > 0


def test_no_bundle_notes_missing_entity(app):
    body = {"model": "claude-sonnet-5", "stop_reason": "end_turn",
            "usage": {"input_tokens": 10, "output_tokens": 5},
            "content": [{"type": "text", "text": "Which release or submittal?"}]}
    with app.app_context(), \
            patch.object(agent.cfg, "ANTHROPIC_API_KEY", "k"), \
            patch.object(agent, "_post", return_value=(body, "r1")) as post:
        agent.run_chat([], "hey there", bundle=None)
    assert "none" in post.call_args[0][0][-1]["content"].lower()
