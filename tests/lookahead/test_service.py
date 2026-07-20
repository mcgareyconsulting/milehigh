"""Mock lookahead service: reads the vendored sample PDF and cross-checks it against models."""
from datetime import date
from types import SimpleNamespace

from app.brain.lookahead import service


def R(**kw):
    base = dict(release=None, description="", stage="Released", start_install=None,
                comp_eta=None, job_comp=None, invoiced=None)
    base.update(kw)
    return SimpleNamespace(**base)


def S(**kw):
    base = dict(rel=None, title="", type="Drafting Release Review", status="Open")
    base.update(kw)
    return SimpleNamespace(**base)


RELEASES = [
    R(release="923", description="Bld C Structural Steel", start_install=date(2026, 7, 24), comp_eta=date(2026, 7, 30)),
    R(release="526", description="Bld B-D Structural Embeds", stage="Complete", job_comp="X"),
]
SUBMITTALS = [S(rel=944, title="Building D Structural Steel", type="Drafting Release Review", status="Open")]


def test_unwired_job_returns_none():
    assert service.crosscheck_for_job("999", [], []) is None


def test_560_reads_sample_pdf_and_crosschecks():
    out = service.crosscheck_for_job("560", RELEASES, SUBMITTALS)
    assert out is not None
    assert out["gc"] == "Wood Partners"
    assert out["issued"] == "2026-07-17"
    assert len(out["activities"]) == 6

    by_key = {(a["building"], a["scope"]): a for a in out["activities"]}
    # Dates are JSON-safe strings after serialization.
    c_steel = by_key[("Building C", "steel")]
    assert c_steel["status"] == "slip" and c_steel["slip_days"] == 3
    assert c_steel["gc_need"] == "2026-07-21" and c_steel["our_date"] == "2026-07-24"

    d_steel = by_key[("Building D", "steel")]
    assert d_steel["status"] == "in_drafting" and d_steel["matched_ref"] == 944
