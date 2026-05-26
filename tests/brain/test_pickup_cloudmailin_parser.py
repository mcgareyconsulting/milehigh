"""Unit tests for the CloudMailin inbound payload normalizer (no Flask/DB)."""
from datetime import datetime

from app.pickup_email.cloudmailin import parse_inbound


def _payload(**overrides):
    base = {
        "envelope": {"from": "shipping@dencol.com", "to": "pickup@inbound.cloudmailin.net"},
        "headers": {
            "subject": "Fwd: 380-456 parts ready",
            "from": "forwarder@mhmw.com",
            "to": "pickup@inbound.cloudmailin.net",
            "message_id": "<abc-123@dencol.com>",
            "date": "Tue, 26 May 2026 15:00:00 +0000",
        },
        "plain": "Your parts are ready.",
    }
    base.update(overrides)
    return base


def test_maps_core_fields():
    f = parse_inbound(_payload())
    assert f["subject"] == "Fwd: 380-456 parts ready"
    assert f["body"] == "Your parts are ready."
    assert f["message_id"] == "<abc-123@dencol.com>"


def test_envelope_sender_wins_over_header_from():
    # The forwarder's display From differs from the SMTP envelope; envelope is authoritative.
    f = parse_inbound(_payload())
    assert f["sender"] == "shipping@dencol.com"
    assert f["to"] == "pickup@inbound.cloudmailin.net"


def test_header_lookup_is_case_insensitive_and_variant_tolerant():
    f = parse_inbound({
        "headers": {"Subject": "280-235 ready", "Message-ID": "<x@y>", "Date": "Tue, 26 May 2026 15:00:00 +0000"},
        "plain": "b",
    })
    assert f["subject"] == "280-235 ready"
    assert f["message_id"] == "<x@y>"


def test_date_parsed_to_datetime():
    f = parse_inbound(_payload())
    assert isinstance(f["received_at"], datetime)
    assert f["received_at"].year == 2026 and f["received_at"].month == 5


def test_missing_date_is_none():
    p = _payload()
    p["headers"].pop("date")
    assert parse_inbound(p)["received_at"] is None


def test_body_falls_back_to_reply_plain():
    p = _payload(plain="")
    p["reply_plain"] = "reply text"
    assert parse_inbound(p)["body"] == "reply text"


def test_empty_payload_is_all_none_not_crash():
    f = parse_inbound({})
    assert f["subject"] is None and f["message_id"] is None and f["body"] == ""
