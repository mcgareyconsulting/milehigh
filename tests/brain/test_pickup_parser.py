"""Unit tests for the pick-up email subject parser (no Flask/DB)."""
import pytest

from app.brain.job_log.features.pickup.parser import parse_subject, clean_subject


@pytest.mark.parametrize("subject,expected", [
    ("123-456 parts ready", (123, "456")),
    ("123-V4 ready for pickup", (123, "V4")),
    ("Fwd: 1234-V12 Dencol", (1234, "V12")),
    ("Re: Fwd: 555-7 pickup", (555, "7")),
    ("pickup for 88-V2 today", (88, "V2")),
    ("lowercase 200-v3 release", (200, "V3")),  # v normalized to V
])
def test_parse_subject_extracts_identifier(subject, expected):
    assert parse_subject(subject) == expected


@pytest.mark.parametrize("subject", [
    "",
    None,
    "no identifier here",
    "just some text 12345",
    "order shipped",
])
def test_parse_subject_returns_none_when_absent(subject):
    assert parse_subject(subject) is None


@pytest.mark.parametrize("raw,expected", [
    ("Fwd: 123-V4 parts", "123-V4 parts"),
    ("Re: Fwd: hello", "hello"),
    ("FW: order ready", "order ready"),
    ("  no prefix  ", "no prefix"),
    (None, ""),
])
def test_clean_subject_strips_prefixes(raw, expected):
    assert clean_subject(raw) == expected
