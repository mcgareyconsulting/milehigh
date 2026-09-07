"""The findings contract of the Opus review call.

Regression cover for a live failure: a finding reading `terminal rise 8" exceeds 7"` put
raw quotes inside a JSON string, and the old regex-then-json.loads path died with
`Expecting ',' delimiter`. The fix is `output_config.format` — the API enforces the schema
— so these pin down the request shape and the parse's remaining fallbacks.
"""
import json
from unittest.mock import patch

import pytest

from app.brain.pdf_review import service


def _resp(text, *, stop_reason="end_turn", status=200):
    class R:
        status_code = status

        @staticmethod
        def raise_for_status():
            return None

        @staticmethod
        def json():
            return {"model": "claude-opus-4-8", "stop_reason": stop_reason,
                    "content": [{"type": "text", "text": text}],
                    "usage": {"input_tokens": 10, "output_tokens": 5}}
    return R()


def test_request_asks_the_api_to_enforce_the_schema():
    payload = json.dumps({"findings": []})
    with patch("app.brain.pdf_review.service.requests.post",
               return_value=_resp(payload)) as post:
        service.review(b"%PDF-fake", "590-674")
    body = post.call_args.kwargs["json"]
    fmt = body["output_config"]["format"]
    assert fmt["type"] == "json_schema"
    assert fmt["schema"]["required"] == ["findings"]
    # Adaptive thinking rides alongside it — the deep pass still reasons across sheets.
    assert body["thinking"] == {"type": "adaptive"}


def test_inch_marks_in_a_finding_no_longer_break_the_parse():
    """The exact shape that failed in production, now escaped by the API."""
    payload = json.dumps({"findings": [{
        "rule_id": "stair-terminal-rise-over-max",
        "issue": 'Terminal rise measures 8" against a 7" maximum.',
        "verdict": "violation",
        "computation": '8" - 7" = 1" over',
    }]})
    with patch("app.brain.pdf_review.service.requests.post", return_value=_resp(payload)):
        result = service.review(b"%PDF-fake", "590-674")
    assert result["findings"][0]["issue"] == 'Terminal rise measures 8" against a 7" maximum.'


def test_ok_findings_may_omit_the_optional_fields():
    """The prompt asks for bare rule_id + issue on cleared checks, so the schema must not
    force computation/values_used/page onto them."""
    item = service.FINDINGS_SCHEMA["properties"]["findings"]["items"]
    assert item["required"] == ["rule_id", "issue", "verdict"]
    for optional in ("page", "severity", "computation", "values_used", "location"):
        assert optional in item["properties"]
        assert optional not in item["required"]


def test_prose_wrapped_json_still_parses():
    """Fallback for a truncated or otherwise non-schema-shaped reply."""
    assert _findings("Here you go:\n{\"findings\": []}\nHope that helps.") == []


def _findings(text):
    with patch("app.brain.pdf_review.service.requests.post", return_value=_resp(text)):
        return service.review(b"%PDF-fake", "590-674")["findings"]


def test_unparseable_response_returns_none_and_logs_the_text():
    """review() swallows failures by contract; the raw text must reach the log, because
    without it this class of bug cannot be diagnosed at all."""
    with patch("app.brain.pdf_review.service.requests.post",
               return_value=_resp("I can't help with that.", stop_reason="refusal")), \
         patch("app.brain.pdf_review.service.logger") as log:
        assert service.review(b"%PDF-fake", "590-674") is None
    logged = [c for c in log.error.call_args_list if c[0][0] == "bb_pdf_review_unparseable"]
    assert logged, "the raw response text was not logged"
    assert logged[0].kwargs["response_text"] == "I can't help with that."
    assert logged[0].kwargs["stop_reason"] == "refusal"


def test_parse_helper_raises_on_garbage():
    with pytest.raises(ValueError):
        service._parse_findings("not json at all", "end_turn")
