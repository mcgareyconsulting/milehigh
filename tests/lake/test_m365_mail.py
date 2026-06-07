"""Service tests for the m365_mail bronze connector.

Graph is always mocked (per the project testing strategy); the DB is the real
in-memory SQLite from tests/conftest.py. Covers normalization/hash stability,
idempotent landing, content-change updates, and watermark advancement.
"""
from unittest.mock import patch

from app.lake.ingest import m365_mail
from app.models import LakeIngestState, RawSourceRecord


def _msg(mid="AAA", subject="RFI 042", received="2026-06-06T18:30:00Z",
         body="Hello world", sender="gc@build.com"):
    """Build a Graph message JSON payload shaped like GRAPH_SELECT."""
    return {
        "id": mid,
        "subject": subject,
        "from": {"emailAddress": {"name": "GC", "address": sender}},
        "toRecipients": [{"emailAddress": {"name": "BB", "address": "BB@mhmw.com"}}],
        "ccRecipients": [],
        "receivedDateTime": received,
        "sentDateTime": received,
        "bodyPreview": body[:50],
        "body": {"contentType": "text", "content": body},
        "conversationId": "conv1",
        "internetMessageId": "<msg@x>",
        "hasAttachments": False,
        "webLink": "https://outlook.example/x",
    }


def test_normalize_maps_fields_and_stable_hash(app):
    payload, ptr, occurred, h1 = m365_mail._normalize(_msg(), "bb@mhmw.com")

    assert payload["subject"] == "RFI 042"
    assert payload["from"]["address"] == "gc@build.com"
    assert payload["to"][0]["address"] == "bb@mhmw.com"  # lowercased
    assert payload["body"] == "Hello world"
    assert payload["conversation_id"] == "conv1"
    assert ptr == {"mailbox": "bb@mhmw.com", "web_link": "https://outlook.example/x"}
    assert occurred.year == 2026 and occurred.month == 6 and occurred.day == 6 and occurred.hour == 18

    # Deterministic for identical content...
    _, _, _, h2 = m365_mail._normalize(_msg(), "bb@mhmw.com")
    assert h1 == h2
    # ...and changes when the body changes.
    _, _, _, h3 = m365_mail._normalize(_msg(body="Different"), "bb@mhmw.com")
    assert h3 != h1


def test_pull_lands_and_is_idempotent(app):
    resp = {"value": [
        _msg("A", body="one"),
        _msg("B", subject="RFI 9", body="two", received="2026-06-05T10:00:00Z"),
    ]}

    with patch.object(m365_mail, "graph_get", return_value=resp):
        r1 = m365_mail.pull(mailbox="bb@mhmw.com")
    assert r1["created"] == 2
    assert RawSourceRecord.query.count() == 2

    # Re-pulling the same window lands nothing new.
    with patch.object(m365_mail, "graph_get", return_value=resp):
        r2 = m365_mail.pull(mailbox="bb@mhmw.com")
    assert r2["created"] == 0
    assert r2["unchanged"] == 2
    assert RawSourceRecord.query.count() == 2

    rec = RawSourceRecord.query.filter_by(external_id="A").one()
    assert rec.source == "m365_mail"
    assert rec.record_type == "email"
    assert rec.source_account == "bb@mhmw.com"


def test_pull_updates_on_body_change(app):
    with patch.object(m365_mail, "graph_get", return_value={"value": [_msg("A", body="one")]}):
        m365_mail.pull(mailbox="bb@mhmw.com")

    with patch.object(m365_mail, "graph_get", return_value={"value": [_msg("A", body="EDITED")]}):
        r = m365_mail.pull(mailbox="bb@mhmw.com")

    assert r["updated"] == 1
    assert RawSourceRecord.query.count() == 1
    rec = RawSourceRecord.query.filter_by(external_id="A").one()
    assert rec.payload["body"] == "EDITED"


def test_poll_advances_watermark(app):
    resp = {"value": [
        _msg("A", received="2026-06-06T18:30:00Z"),
        _msg("B", received="2026-06-05T10:00:00Z"),
    ]}
    with patch.object(m365_mail, "graph_get", return_value=resp):
        agg = m365_mail.poll()

    assert agg["mailboxes"] == 1 and agg["created"] == 2

    state = LakeIngestState.query.filter_by(source="m365_mail", account="bb@mhmw.com").one()
    assert state.last_polled_at is not None
    assert state.last_occurred_at is not None
    # Watermark = max receivedDateTime seen.
    assert state.last_occurred_at.day == 6 and state.last_occurred_at.hour == 18


def test_poll_uses_watermark_filter_on_second_run(app):
    with patch.object(m365_mail, "graph_get", return_value={"value": [_msg("A")]}):
        m365_mail.poll()

    with patch.object(m365_mail, "graph_get", return_value={"value": []}) as gg:
        m365_mail.poll()

    params = gg.call_args.kwargs["params"]
    assert "$filter" in params and "receivedDateTime gt" in params["$filter"]


def test_resolve_mailboxes_from_explicit_list(app):
    app.config["BB_MAILBOXES"] = "a@mhmw.com, B@mhmw.com"
    assert m365_mail.resolve_mailboxes() == ["a@mhmw.com", "b@mhmw.com"]


def test_resolve_mailboxes_defaults_to_single(app):
    app.config["BB_MAILBOXES"] = None
    app.config["BB_INGEST_GROUP_ID"] = None
    assert m365_mail.resolve_mailboxes() == ["bb@mhmw.com"]


def test_resolve_mailboxes_from_group_discovery(app):
    app.config["BB_INGEST_GROUP_ID"] = "group-123"
    members = {"value": [
        {"mail": "Jane@mhmw.com", "userPrincipalName": "jane@mhmw.com"},
        {"mail": None, "userPrincipalName": "svc@mhmw.com"},  # falls back to UPN
        {"mail": "", "userPrincipalName": ""},                 # skipped
    ]}
    with patch.object(m365_mail, "graph_get", return_value=members):
        assert m365_mail.resolve_mailboxes() == ["jane@mhmw.com", "svc@mhmw.com"]


def test_poll_continues_when_one_mailbox_fails(app):
    app.config["BB_MAILBOXES"] = "good@mhmw.com, bad@mhmw.com"

    def fake_pull(since=None, query=None, max_results=25, mailbox=None):
        if mailbox == "bad@mhmw.com":
            raise RuntimeError("no access")
        return {"mailbox": mailbox, "fetched": 1, "created": 1, "updated": 0,
                "unchanged": 0, "landed_ids": ["X"], "max_occurred_at": None}

    with patch.object(m365_mail, "pull", side_effect=fake_pull):
        agg = m365_mail.poll()

    assert agg["mailboxes"] == 1 and agg["created"] == 1  # bad one skipped, good one landed
