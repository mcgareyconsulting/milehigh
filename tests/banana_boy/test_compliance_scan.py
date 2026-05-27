"""Tests for the fab-drawing compliance scan: loader, tool, prompt rule."""
from unittest.mock import MagicMock, patch

import pytest

from app.banana_boy import compliance, tools
from app.banana_boy.drawings import LocalDrawingLoader


PDF_BYTES = b"%PDF-1.7\n%fake-pdf-bytes-for-testing\n%%EOF"


@pytest.fixture
def drawings_dir(app, tmp_path):
    """Point the app's drawing loader at a tmp dir holding 480-299-fc.pdf."""
    (tmp_path / "480-299-fc.pdf").write_bytes(PDF_BYTES)
    app.extensions[tools.DRAWING_LOADER_KEY] = LocalDrawingLoader(tmp_path)
    return tmp_path


def test_local_loader_returns_pdf_bytes(tmp_path):
    (tmp_path / "480-299-fc.pdf").write_bytes(PDF_BYTES)
    loader = LocalDrawingLoader(tmp_path)
    loaded = loader.load(480, "299")

    assert loaded is not None
    pdf, meta = loaded
    assert pdf == PDF_BYTES
    assert meta["source"] == "local"
    assert meta["path"].endswith("480-299-fc.pdf")
    assert meta["size_bytes"] == len(PDF_BYTES)


def test_local_loader_returns_none_for_missing(tmp_path):
    loader = LocalDrawingLoader(tmp_path)
    assert loader.load(999, "999") is None


def test_local_loader_returns_none_for_blank_release(tmp_path):
    loader = LocalDrawingLoader(tmp_path)
    assert loader.load(480, "") is None
    assert loader.load(480, "   ") is None


def test_scan_tool_missing_pdf_returns_error(app, tmp_path):
    app.extensions[tools.DRAWING_LOADER_KEY] = LocalDrawingLoader(tmp_path)
    with app.app_context():
        result = tools.scan_drawing_compliance({}, job=999, release="999")

    assert "error" in result
    assert "no fab drawing on file" in result["error"]
    assert result["expected_filename"] == "999-999-fc.pdf"


def test_scan_tool_unconfigured_loader_errors(app):
    app.extensions.pop(tools.DRAWING_LOADER_KEY, None)
    with app.app_context():
        result = tools.scan_drawing_compliance({}, job=480, release="299")
    assert result == {"error": "drawing loader is not configured"}


def test_scan_tool_requires_job_and_release(app, drawings_dir):
    with app.app_context():
        assert "error" in tools.scan_drawing_compliance({}, job=None, release="299")
        assert "error" in tools.scan_drawing_compliance({}, job=480, release="")


def _fake_scan_response(text="## PASSING\n- ok (page 1)\n\n## FLAGGED\n\n## NOT_DETERMINABLE\n",
                        input_tokens=5000, output_tokens=400,
                        cache_read=0, cache_creation=2500,
                        stop_reason="end_turn"):
    resp = MagicMock()
    resp.content = [MagicMock(type="text", text=text)]
    resp.usage = MagicMock(
        input_tokens=input_tokens, output_tokens=output_tokens,
        cache_read_input_tokens=cache_read,
        cache_creation_input_tokens=cache_creation,
    )
    resp.stop_reason = stop_reason
    return resp


def test_scan_tool_invokes_sonnet_with_pdf_and_kb(app, drawings_dir):
    """Happy path: tool loads PDF, fires Sonnet with document block + KB."""
    fake_client = MagicMock()
    fake_client.messages.create.return_value = _fake_scan_response()

    with app.app_context(), \
         patch.object(compliance, "_get_anthropic_client", return_value=fake_client):
        result = tools.scan_drawing_compliance({}, job=480, release="299")

    assert result["job"] == 480
    assert result["release"] == "299"
    assert result["model"] == "claude-sonnet-4-6"
    assert "PASSING" in result["findings"]
    assert result["source"]["source"] == "local"

    kwargs = fake_client.messages.create.call_args.kwargs
    assert kwargs["model"] == "claude-sonnet-4-6"

    user_blocks = kwargs["messages"][0]["content"]
    doc_blocks = [b for b in user_blocks if b.get("type") == "document"]
    assert len(doc_blocks) == 1
    assert doc_blocks[0]["source"]["media_type"] == "application/pdf"
    assert doc_blocks[0]["source"]["type"] == "base64"
    assert doc_blocks[0]["cache_control"] == {"type": "ephemeral"}

    cached_system = [
        b for b in kwargs["system"]
        if isinstance(b, dict) and b.get("cache_control")
    ]
    assert len(cached_system) == 1
    assert cached_system[0]["text"].startswith("<knowledge_base>")
    assert "Division 05" in cached_system[0]["text"]


def test_scan_prompt_includes_no_hallucination_rules():
    """The system prompt MUST require page+callout citations and forbid inference."""
    p = compliance.SCAN_PROMPT
    assert "verbatim" in p.lower()
    assert "page" in p.lower()
    assert "NOT_DETERMINABLE" in p
    assert "do not estimate" in p.lower() or "do not infer" in p.lower()


def test_tool_definition_registered():
    names = {t["name"] for t in tools.TOOL_DEFINITIONS}
    assert tools.TOOL_SCAN_COMPLIANCE in names
    assert tools.TOOL_SCAN_COMPLIANCE in tools.TOOL_EXECUTORS


def test_system_prompt_dispatches_compliance_to_tool():
    """SYSTEM_PROMPT must steer specific-job compliance Qs to scan_drawing_compliance."""
    from app.banana_boy.client import SYSTEM_PROMPT
    assert "scan_drawing_compliance" in SYSTEM_PROMPT
    assert "COMPLIANCE" in SYSTEM_PROMPT


def test_scan_appends_usage_record_with_cost_and_duration(app, drawings_dir):
    """Sonnet sub-agent call must record one usage row with tokens, cost, duration."""
    sink: list = []
    fake_client = MagicMock()
    fake_client.messages.create.return_value = _fake_scan_response(
        input_tokens=10_000, output_tokens=500,
        cache_read=0, cache_creation=8_000,
    )

    with app.app_context(), \
         patch.object(compliance, "_get_anthropic_client", return_value=fake_client):
        tools.scan_drawing_compliance({"usage_sink": sink}, job=480, release="299")

    assert len(sink) == 1
    rec = sink[0]
    assert rec["provider"] == "anthropic"
    assert rec["operation"] == "compliance_scan"
    assert rec["model"] == "claude-sonnet-4-6"
    assert rec["input_tokens"] == 10_000
    assert rec["output_tokens"] == 500
    assert rec["cache_creation_tokens"] == 8_000
    assert rec["duration_ms"] >= 0
    # Cost matches Sonnet 4.6 pricing: $3/M input + $15/M output + $3.75/M cache_creation
    expected = (10_000 * 3.0 + 500 * 15.0 + 8_000 * 3.75) / 1_000_000
    assert abs(rec["cost_usd"] - expected) < 1e-9
    # PDF base64 must NOT leak into the recorded payload (would bloat the table).
    payload_str = str(rec["payload"])
    assert "pdf document block" in payload_str
    assert rec["payload"]["pdf_size_bytes"] == len(PDF_BYTES)


def test_scan_omits_usage_record_when_no_sink(app, drawings_dir):
    """When usage_sink is missing/None, scan still works and records nothing."""
    fake_client = MagicMock()
    fake_client.messages.create.return_value = _fake_scan_response()

    with app.app_context(), \
         patch.object(compliance, "_get_anthropic_client", return_value=fake_client):
        result = tools.scan_drawing_compliance({}, job=480, release="299")

    assert "findings" in result
    # No exception, no sink interaction expected — implicit pass.


def test_generate_reply_propagates_usage_sink_to_tool_context(app):
    """client.generate_reply must inject usage_sink into tool_context so the
    compliance tool can record its sub-agent call into the same sink the
    chat route persists."""
    from app.banana_boy import client as bb_client

    captured = {}

    fake_response = MagicMock()
    fake_response.stop_reason = "end_turn"
    fake_response.content = [MagicMock(type="text", text="ok")]
    fake_response.usage = MagicMock(
        input_tokens=1, output_tokens=1,
        cache_read_input_tokens=0, cache_creation_input_tokens=0,
    )

    fake_client = MagicMock()
    fake_client.messages.create.return_value = fake_response

    sink: list = []
    original = bb_client.generate_reply.__wrapped__ if hasattr(bb_client.generate_reply, "__wrapped__") else None  # noqa
    # Patch execute_tool to capture the context the chat loop hands tools.
    with app.app_context(), \
         patch.object(bb_client, "_get_client", return_value=fake_client):
        # Monkey-patch the module-level reference used inside generate_reply
        # to confirm context.usage_sink is the same list.
        from app.banana_boy import tools as bb_tools
        real_execute = bb_tools.execute_tool

        def spy(name, args, context=None):
            captured["context"] = context
            return real_execute(name, args, context=context)

        with patch.object(bb_client, "execute_tool", side_effect=spy):
            bb_client.generate_reply(
                [{"role": "user", "content": "hi"}],
                tool_context={"user_id": 1},
                usage_sink=sink,
            )

    # No tool was called in this happy-path stub (response was plain text), so
    # captured may be empty — but the important invariant is that generate_reply
    # built a tool_context with the sink. Re-derive by inspecting the call:
    # we trust the code path via the assertion below using a tool-use response.

    # Second pass: force a tool_use stop_reason so execute_tool actually runs
    # and we can verify context["usage_sink"] is sink.
    tool_use_block = MagicMock(
        type="tool_use", id="t1",
        name=tools.TOOL_SCAN_COMPLIANCE,
        input={"job": 480, "release": "299"},
    )
    text_after = MagicMock(type="text", text="done")
    tool_response = MagicMock(stop_reason="tool_use", content=[tool_use_block])
    final_response = MagicMock(
        stop_reason="end_turn", content=[text_after],
        usage=MagicMock(input_tokens=1, output_tokens=1,
                        cache_read_input_tokens=0, cache_creation_input_tokens=0),
    )
    tool_response.usage = final_response.usage
    fake_client.messages.create.side_effect = [tool_response, final_response]

    with app.app_context(), \
         patch.object(bb_client, "_get_client", return_value=fake_client), \
         patch.object(bb_client, "execute_tool") as spy_exec:
        spy_exec.return_value = {"error": "no fab drawing on file for 480-299"}
        bb_client.generate_reply(
            [{"role": "user", "content": "compliance check 480-299"}],
            tool_context={"user_id": 1},
            usage_sink=sink,
        )
        ctx = spy_exec.call_args.kwargs["context"]
        assert ctx["user_id"] == 1
        assert ctx["usage_sink"] is sink
