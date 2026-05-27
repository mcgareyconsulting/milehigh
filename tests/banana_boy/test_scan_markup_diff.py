"""Tests for scan_markup_diff: tool wiring, defaults, Sonnet payload, usage."""
from unittest.mock import MagicMock, patch

import pytest

from app.banana_boy import markup_diff, tools
from app.brain.job_log.features.pdf_markup.storage import save_pdf
from app.models import ReleaseDrawingVersion, db
from tests.conftest import make_release, make_user


PDF_V1 = b"%PDF-1.4\n%v1-clean\n%%EOF\n"
PDF_V2 = b"%PDF-1.4\n%v2-with-redlines\n%%EOF\n"
PDF_V3 = b"%PDF-1.4\n%v3-more-redlines\n%%EOF\n"


@pytest.fixture
def storage_root(app, tmp_path):
    app.config['PDF_STORAGE_ROOT'] = str(tmp_path)
    return tmp_path


def _add_version(*, release_id, version_number, data, source_version_id=None,
                 uploader_id=1):
    storage_key = save_pdf(release_id, version_number, data)
    v = ReleaseDrawingVersion(
        release_id=release_id,
        version_number=version_number,
        storage_key=storage_key,
        original_filename=f"v{version_number}.pdf",
        mime_type='application/pdf',
        file_size_bytes=len(data),
        uploaded_by_user_id=uploader_id,
        source_version_id=source_version_id,
    )
    db.session.add(v)
    db.session.flush()
    return v


def _fake_diff_response(text="## ADDED ANNOTATIONS\n- Page 3 — text annotation: \"verify weld\"\n",
                        input_tokens=4000, output_tokens=300,
                        cache_read=0, cache_creation=2000,
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


def test_diff_tool_requires_two_versions(app, storage_root):
    with app.app_context():
        user = make_user("d", is_drafter=True)
        rel = make_release(480, "299")
        _add_version(release_id=rel.id, version_number=1, data=PDF_V1, uploader_id=user.id)
        db.session.commit()

        result = tools.scan_markup_diff({}, job=480, release="299")

    assert "error" in result
    assert "at least two" in result["error"].lower()


def test_diff_tool_unknown_release(app, storage_root):
    with app.app_context():
        result = tools.scan_markup_diff({}, job=999, release="999")
    assert "error" in result


def test_diff_tool_requires_inputs(app, storage_root):
    with app.app_context():
        assert "error" in tools.scan_markup_diff({}, job=None, release="299")
        assert "error" in tools.scan_markup_diff({}, job=480, release="")


def test_diff_defaults_to_latest_vs_predecessor(app, storage_root):
    """Default: 'to' = latest, 'from' = source_version_id of latest."""
    fake_client = MagicMock()
    fake_client.messages.create.return_value = _fake_diff_response()

    with app.app_context():
        user = make_user("d", first_name="Sam", last_name="Stark", is_drafter=True)
        rel = make_release(480, "299")
        v1 = _add_version(release_id=rel.id, version_number=1, data=PDF_V1, uploader_id=user.id)
        v2 = _add_version(release_id=rel.id, version_number=2, data=PDF_V2,
                          source_version_id=v1.id, uploader_id=user.id)
        _add_version(release_id=rel.id, version_number=3, data=PDF_V3,
                     source_version_id=v2.id, uploader_id=user.id)
        db.session.commit()

        with patch.object(markup_diff, "_get_anthropic_client", return_value=fake_client):
            result = tools.scan_markup_diff({}, job=480, release="299")

    assert result["from_version"] == 2
    assert result["to_version"] == 3
    assert result["model"] == "claude-sonnet-4-6"
    assert "Page 3" in result["findings"]


def test_diff_defaults_when_lineage_link_missing(app, storage_root):
    """When latest.source_version_id is NULL, diff against the prior version_number."""
    fake_client = MagicMock()
    fake_client.messages.create.return_value = _fake_diff_response()

    with app.app_context():
        user = make_user("d", is_drafter=True)
        rel = make_release(480, "299")
        _add_version(release_id=rel.id, version_number=1, data=PDF_V1, uploader_id=user.id)
        _add_version(release_id=rel.id, version_number=2, data=PDF_V2, uploader_id=user.id)
        db.session.commit()

        with patch.object(markup_diff, "_get_anthropic_client", return_value=fake_client):
            result = tools.scan_markup_diff({}, job=480, release="299")

    assert result["from_version"] == 1
    assert result["to_version"] == 2


def test_diff_explicit_versions_override_defaults(app, storage_root):
    fake_client = MagicMock()
    fake_client.messages.create.return_value = _fake_diff_response()

    with app.app_context():
        user = make_user("d", is_drafter=True)
        rel = make_release(480, "299")
        _add_version(release_id=rel.id, version_number=1, data=PDF_V1, uploader_id=user.id)
        _add_version(release_id=rel.id, version_number=2, data=PDF_V2, uploader_id=user.id)
        _add_version(release_id=rel.id, version_number=3, data=PDF_V3, uploader_id=user.id)
        db.session.commit()

        with patch.object(markup_diff, "_get_anthropic_client", return_value=fake_client):
            result = tools.scan_markup_diff(
                {}, job=480, release="299", from_version=1, to_version=3,
            )

    assert result["from_version"] == 1
    assert result["to_version"] == 3


def test_diff_sends_two_pdf_documents_in_order(app, storage_root):
    """Sonnet payload: two PDF document blocks, FROM first, TO second."""
    fake_client = MagicMock()
    fake_client.messages.create.return_value = _fake_diff_response()

    with app.app_context():
        user = make_user("d", is_drafter=True)
        rel = make_release(480, "299")
        _add_version(release_id=rel.id, version_number=1, data=PDF_V1, uploader_id=user.id)
        _add_version(release_id=rel.id, version_number=2, data=PDF_V2, uploader_id=user.id)
        db.session.commit()

        with patch.object(markup_diff, "_get_anthropic_client", return_value=fake_client):
            tools.scan_markup_diff({}, job=480, release="299")

    kwargs = fake_client.messages.create.call_args.kwargs
    assert kwargs["model"] == "claude-sonnet-4-6"
    user_blocks = kwargs["messages"][0]["content"]
    doc_blocks = [b for b in user_blocks if b.get("type") == "document"]
    assert len(doc_blocks) == 2
    import base64
    assert base64.b64decode(doc_blocks[0]["source"]["data"]) == PDF_V1  # FROM
    assert base64.b64decode(doc_blocks[1]["source"]["data"]) == PDF_V2  # TO


def test_diff_records_usage_with_cost_and_duration(app, storage_root):
    sink: list = []
    fake_client = MagicMock()
    fake_client.messages.create.return_value = _fake_diff_response(
        input_tokens=8000, output_tokens=600,
        cache_read=0, cache_creation=4000,
    )

    with app.app_context():
        user = make_user("d", is_drafter=True)
        rel = make_release(480, "299")
        _add_version(release_id=rel.id, version_number=1, data=PDF_V1, uploader_id=user.id)
        _add_version(release_id=rel.id, version_number=2, data=PDF_V2, uploader_id=user.id)
        db.session.commit()

        with patch.object(markup_diff, "_get_anthropic_client", return_value=fake_client):
            tools.scan_markup_diff({"usage_sink": sink}, job=480, release="299")

    assert len(sink) == 1
    rec = sink[0]
    assert rec["provider"] == "anthropic"
    assert rec["operation"] == "markup_diff_scan"
    assert rec["model"] == "claude-sonnet-4-6"
    assert rec["input_tokens"] == 8000
    assert rec["output_tokens"] == 600
    assert rec["cache_creation_tokens"] == 4000
    assert rec["duration_ms"] >= 0
    expected = (8000 * 3.0 + 600 * 15.0 + 4000 * 3.75) / 1_000_000
    assert abs(rec["cost_usd"] - expected) < 1e-9
    # PDF base64 must NOT leak into the recorded payload
    payload_str = str(rec["payload"])
    assert "from pdf" in payload_str
    assert rec["payload"]["from_size_bytes"] == len(PDF_V1)
    assert rec["payload"]["to_size_bytes"] == len(PDF_V2)


def test_diff_omits_usage_when_no_sink(app, storage_root):
    fake_client = MagicMock()
    fake_client.messages.create.return_value = _fake_diff_response()

    with app.app_context():
        user = make_user("d", is_drafter=True)
        rel = make_release(480, "299")
        _add_version(release_id=rel.id, version_number=1, data=PDF_V1, uploader_id=user.id)
        _add_version(release_id=rel.id, version_number=2, data=PDF_V2, uploader_id=user.id)
        db.session.commit()

        with patch.object(markup_diff, "_get_anthropic_client", return_value=fake_client):
            result = tools.scan_markup_diff({}, job=480, release="299")

    assert "findings" in result


def test_diff_prompt_has_no_hallucination_rules():
    p = markup_diff.DIFF_PROMPT
    assert "verbatim" in p.lower()
    assert "page" in p.lower()
    assert "do not infer" in p.lower() or "do not paraphrase" in p.lower()


def test_diff_tool_registered():
    names = {t["name"] for t in tools.TOOL_DEFINITIONS}
    assert tools.TOOL_SCAN_MARKUP_DIFF in names
    assert tools.TOOL_SCAN_MARKUP_DIFF in tools.TOOL_EXECUTORS
    assert tools.TOOL_SCAN_MARKUP_DIFF in tools.USER_SCOPED_TOOLS


def test_diff_unknown_explicit_version_errors(app, storage_root):
    with app.app_context():
        user = make_user("d", is_drafter=True)
        rel = make_release(480, "299")
        _add_version(release_id=rel.id, version_number=1, data=PDF_V1, uploader_id=user.id)
        _add_version(release_id=rel.id, version_number=2, data=PDF_V2, uploader_id=user.id)
        db.session.commit()

        result = tools.scan_markup_diff({}, job=480, release="299",
                                         from_version=1, to_version=99)

    assert "error" in result
    assert "99" in result["error"]
