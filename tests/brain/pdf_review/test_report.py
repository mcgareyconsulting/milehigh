"""Unit tests for the BB review report assembler (app/brain/pdf_review/report.py).

Pure — no DB, no Flask. Fixture mirrors the validated 590-674 review, graded so each
urgency bucket has exactly one finding (critical/high/moderate/low) plus the six cleared
rules.
"""
from app.brain.pdf_review.report import (
    build_report, urgency_for, notification_message,
)


# 590-674: 1 violation + 3 needs_field_verification (graded high/medium/low) + 6 ok.
FINDINGS_590_674 = [
    {"rule_id": "stair-terminal-rise-over-max", "verdict": "violation", "severity": "high",
     "issue": "terminal rise > 7\""},
    {"rule_id": "guard-opening-limits", "verdict": "needs_field_verification", "severity": "high",
     "issue": "landing guard bottom opening ~6-1/4\""},
    {"rule_id": "guard-handrail-loads", "verdict": "needs_field_verification", "severity": "medium",
     "issue": "cane-rail post 2-anchor base"},
    {"rule_id": "stair-width-and-headroom", "verdict": "needs_field_verification", "severity": "low",
     "issue": "clear width ~37\""},
] + [{"rule_id": f"cleared-{i}", "verdict": "ok", "severity": "low", "issue": "passed"}
     for i in range(6)]


def test_urgency_for_mapping():
    assert urgency_for("violation", "high") == "critical"
    assert urgency_for("violation", "low") == "critical"       # violation always critical
    assert urgency_for("needs_field_verification", "high") == "high"
    assert urgency_for("needs_field_verification", "medium") == "moderate"
    assert urgency_for("needs_field_verification", "low") == "low"
    assert urgency_for("ok", "high") == "cleared"
    assert urgency_for("needs_field_verification", None) == "low"   # unknown severity -> low
    assert urgency_for("weird_verdict", "medium") == "moderate"     # non-ok grades by severity


def test_build_report_tally_and_hold():
    r = build_report(FINDINGS_590_674, "590-674")
    assert r["tally"] == {"critical": 1, "high": 1, "moderate": 1, "low": 1, "cleared": 6}
    assert r["hold_recommended"] is True
    assert r["job_release"] == "590-674"


def test_build_report_ranks_by_urgency():
    r = build_report(FINDINGS_590_674, "590-674")
    assert [f["urgency"] for f in r["findings"]] == ["critical", "high", "moderate", "low"]
    assert [f["urgency_rank"] for f in r["findings"]] == [0, 1, 2, 3]
    # cleared findings are split out, not ranked
    assert len(r["cleared"]) == 6
    assert all(f["verdict"] == "ok" for f in r["cleared"])
    # each ranked finding keeps its original fields plus the urgency annotations
    assert r["findings"][0]["rule_id"] == "stair-terminal-rise-over-max"


def test_headline_and_notification_message():
    r = build_report(FINDINGS_590_674, "590-674")
    assert r["headline"] == "1 code violation + 3 to confirm — review before fabrication."
    assert notification_message(r) == (
        "BB reviewed 590-674: 1 code violation + 3 to confirm — review before fabrication."
    )


def test_clean_review_is_quiet():
    r = build_report([{"verdict": "ok", "severity": "low"}], "700-100")
    assert r["hold_recommended"] is False
    assert r["findings"] == []
    assert r["tally"]["cleared"] == 1
    assert "clear" in r["headline"].lower()


def test_confirm_only_review_uses_confirm_wording():
    findings = [{"verdict": "needs_field_verification", "severity": "medium", "rule_id": "x"}]
    r = build_report(findings, "700-101")
    assert r["hold_recommended"] is False
    assert r["headline"] == "1 to confirm — confirm before fabrication."


def test_empty_findings():
    r = build_report([], "700-102")
    assert r["tally"] == {"critical": 0, "high": 0, "moderate": 0, "low": 0, "cleared": 0}
    assert r["findings"] == [] and r["cleared"] == []
    assert r["hold_recommended"] is False
