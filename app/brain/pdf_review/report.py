"""Assemble a Banana Boy review into a PM-facing report.

`service.review()` returns a flat list of findings; this module is the single source
of truth for turning that list into something a Project Manager acts on: it maps each
finding to an URGENCY, ranks them, tallies the counts, and writes the one-line headline
and bell message.

Kept pure (no DB, no Flask) so it can be unit-tested against a fixture and reused by
both the worker (to write the notification) and the report endpoint (to render the panel).
The frontend mirror of URGENCY lives in frontend/src/components/bbReview/shared.jsx — keep
the two in sync.

Urgency is derived from (verdict, severity):
  violation                              -> critical  (a real code violation; hold fab)
  needs_field_verification + high        -> high      (confirm before fabrication)
  needs_field_verification + medium      -> moderate
  needs_field_verification + low         -> low
  ok                                     -> cleared   (rule ran and passed; not a finding)
Anything unrecognized is treated as `low` so it still surfaces rather than vanishing.
"""

# Ordered most-urgent first. rank drives sort order; label is what the PM sees.
URGENCY_ORDER = ["critical", "high", "moderate", "low", "cleared"]
_RANK = {name: i for i, name in enumerate(URGENCY_ORDER)}


def urgency_for(verdict: str, severity: str) -> str:
    """Map one finding's (verdict, severity) to an urgency bucket name."""
    if verdict == "violation":
        return "critical"
    if verdict == "ok":
        return "cleared"
    # needs_field_verification (or anything else non-ok) grades by severity.
    return {"high": "high", "medium": "moderate", "low": "low"}.get(severity, "low")


def _empty_tally() -> dict:
    return {name: 0 for name in URGENCY_ORDER}


def _plural(n: int, word: str) -> str:
    return f"{n} {word}" + ("" if n == 1 else "s")


def _headline(tally: dict) -> str:
    """One human sentence summarizing the report for the top of the panel."""
    violations = tally["critical"]
    to_confirm = tally["high"] + tally["moderate"] + tally["low"]
    if not violations and not to_confirm:
        return "No code issues found — the set is clear against BB's rules."
    parts = []
    if violations:
        parts.append(_plural(violations, "code violation"))
    if to_confirm:
        parts.append(f"{to_confirm} to confirm")
    tail = "review before fabrication" if violations else "confirm before fabrication"
    return f"{' + '.join(parts)} — {tail}."


def build_report(findings, job_release: str) -> dict:
    """Turn a findings list into a ranked, tallied, PM-facing report.

    Returns:
        {
          job_release, headline, hold_recommended,
          tally: {critical, high, moderate, low, cleared},
          findings: [<finding + urgency + urgency_rank>, ...]  # non-cleared, ranked
          cleared:  [<finding>, ...]                            # verdict == ok
        }
    """
    findings = findings or []
    tally = _empty_tally()
    ranked = []
    cleared = []

    for f in findings:
        urgency = urgency_for(f.get("verdict"), f.get("severity"))
        tally[urgency] += 1
        if urgency == "cleared":
            cleared.append(f)
        else:
            ranked.append({**f, "urgency": urgency, "urgency_rank": _RANK[urgency]})

    # Stable sort by rank keeps the model's within-bucket ordering.
    ranked.sort(key=lambda f: f["urgency_rank"])

    return {
        "job_release": job_release,
        "headline": _headline(tally),
        "hold_recommended": tally["critical"] > 0,
        "tally": tally,
        "findings": ranked,
        "cleared": cleared,
    }


def notification_message(report: dict) -> str:
    """The one-liner dropped into the PM's notification bell."""
    return f"BB reviewed {report['job_release']}: {report['headline']}"
