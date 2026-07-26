"""Tests for the admin Submittal Matching tool (DRR -> release description matching).

Layers:
  - pure unit: matcher tokenizer + suggestion classes (no Flask/DB)
  - integration: HTTP routes via test_client + in-memory DB
"""
from datetime import date, datetime

import pytest

from app.brain.submittal_matching import matcher
from app.models import db, Releases, Submittals, SubmittalEvents


# ---------------------------------------------------------------------------
# Unit: tokenizer
# ---------------------------------------------------------------------------

class TestTokenize:
    def test_strips_job_release_prefix(self):
        # An embedded release number must not self-match.
        assert "942" not in matcher.tokenize("340-942 Stair Core C Top Remainder")

    def test_number_sign_expansion(self):
        assert "2" in matcher.tokenize("Building #02 - Structural Steel")

    def test_building_normalizes_to_bld(self):
        assert matcher.tokenize("Building 8") == matcher.tokenize("Bld 8")
        assert matcher.tokenize("Bldg 8") == matcher.tokenize("bld 8")

    def test_single_digit_tokens_kept(self):
        # Building/core numbers are the discriminating tokens.
        assert "8" in matcher.tokenize("Building 8 Pour Stop Angle")
        assert "5" in matcher.tokenize("Stair Core 5")

    def test_light_plural_stemming(self):
        assert matcher.tokenize("Balcony Rails") == matcher.tokenize("Balcony Rail")

    def test_stop_words_and_install_noise_dropped(self):
        toks = matcher.tokenize("Pour Stop Angle Install Bld 15")
        assert "install" not in toks
        assert {"pour", "stop", "angle", "bld", "15"} <= toks


# ---------------------------------------------------------------------------
# Unit: suggestion outcomes
# ---------------------------------------------------------------------------

def _pool(*descriptions):
    releases = [
        {"release_pk": i + 1, "job": 440, "release": str(300 + i), "description": d}
        for i, d in enumerate(descriptions)
    ]
    freq = matcher.build_token_frequency(d for d in descriptions)
    return releases, freq


class TestSuggest:
    def test_confident_on_discriminating_digit(self):
        # The validated sibling case: building number decides between near-identical rows.
        releases, freq = _pool(
            "Pour Stop Angle Install Bld 8",
            "Pour Stop Angle Install Bld 6",
        )
        result = matcher.suggest("Building 8 Pour Stop Angle", releases, freq)
        assert result["outcome"] == matcher.OUTCOME_CONFIDENT
        assert result["candidates"][0]["description"].endswith("Bld 8")
        assert "8" in result["candidates"][0]["shared_tokens"]

    def test_ambiguous_when_runner_up_close(self):
        releases, freq = _pool(
            "Bld B-D Structural Embeds",
            "Bld A Structural Embeds",
        )
        result = matcher.suggest("Remaining Structural Embeds", releases, freq)
        assert result["outcome"] == matcher.OUTCOME_AMBIGUOUS
        assert len(result["candidates"]) == 2

    def test_weak_on_single_shared_token(self):
        releases, freq = _pool("Roof Access Ladder", "Trash Room Gates")
        result = matcher.suggest("Ladder Modification Request", releases, freq)
        assert result["outcome"] == matcher.OUTCOME_WEAK

    def test_no_overlap(self):
        releases, freq = _pool("Trash Room Gates")
        result = matcher.suggest("Elevator Hoist Beams", releases, freq)
        assert result["outcome"] == matcher.OUTCOME_NO_OVERLAP
        assert result["candidates"] == []

    def test_no_pool(self):
        result = matcher.suggest("Anything", [], matcher.build_token_frequency([]))
        assert result["outcome"] == matcher.OUTCOME_NO_POOL

    def test_candidates_capped_at_top_n(self):
        descriptions = [f"Stair Core {i} Rail" for i in range(10)]
        releases, freq = _pool(*descriptions)
        result = matcher.suggest("Stair Core Rail", releases, freq)
        assert len(result["candidates"]) <= matcher.TOP_N


# ---------------------------------------------------------------------------
# Integration: routes
# ---------------------------------------------------------------------------

def _make_drr(submittal_id, project, title, *, status="Closed", rel=None,
              link_status="", linked_release_id=None):
    s = Submittals(
        submittal_id=submittal_id,
        project_number=project,
        project_name=f"Project {project}",
        title=title,
        status=status,
        type="Drafting Release Review",
        rel=rel,
        link_status=link_status,
        linked_release_id=linked_release_id,
    )
    db.session.add(s)
    return s


def _make_release(job, release, description, *, released=None, is_archived=False, is_active=True):
    r = Releases(
        job=job,
        release=release,
        job_name=f"Job {job}",
        description=description,
        released=released,
        is_archived=is_archived,
        is_active=is_active,
    )
    db.session.add(r)
    return r


@pytest.fixture
def seeded(app):
    with app.app_context():
        drr = _make_drr("SUB-1", "440", "Building 8 Pour Stop Angle")
        other = _make_drr("SUB-2", "440", "Clubhouse Rails")
        r8 = _make_release(440, "306", "Pour Stop Angle Install Bld 8", released=date(2026, 6, 20))
        r6 = _make_release(440, "304", "Pour Stop Angle Install Bld 6")
        archived = _make_release(440, "476", "Clubhouse Site Rails", is_archived=True)
        cross_job = _make_release(500, "685", "Stair Core 2 Part 2")
        db.session.commit()
        yield {
            "drr_id": drr.id,
            "other_id": other.id,
            "r8_id": r8.id,
            "archived_id": archived.id,
            "cross_job_id": cross_job.id,
        }


class TestMatchingRoutes:
    def test_admin_required(self, non_admin_client, seeded):
        assert non_admin_client.get("/brain/submittal-matching/projects").status_code == 403
        assert non_admin_client.get("/brain/submittal-matching/drrs?project=440").status_code == 403
        assert non_admin_client.post(
            f"/brain/submittal-matching/{seeded['drr_id']}/link", json={"release_id": 1}
        ).status_code == 403

    def test_projects_summary(self, admin_client, seeded):
        resp = admin_client.get("/brain/submittal-matching/projects")
        assert resp.status_code == 200
        projects = resp.get_json()["projects"]
        p440 = next(p for p in projects if p["project_number"] == "440")
        assert p440["drr_total"] == 2
        assert p440["unreviewed"] == 2
        assert p440["linked"] == 0
        # Archived releases count toward the matchable pool.
        assert p440["release_pool"] == 3

    def test_drrs_suggestions_include_archived(self, admin_client, seeded):
        resp = admin_client.get("/brain/submittal-matching/drrs?project=440")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["release_pool"] == 3

        by_title = {d["title"]: d for d in data["drrs"]}
        bld8 = by_title["Building 8 Pour Stop Angle"]
        assert bld8["suggestion"]["outcome"] == "confident"
        assert bld8["suggestion"]["candidates"][0]["release"] == "306"

        clubhouse = by_title["Clubhouse Rails"]
        top = clubhouse["suggestion"]["candidates"][0]
        assert top["release"] == "476"
        assert top["is_archived"] is True

    def test_drrs_requires_project_param(self, admin_client, seeded):
        assert admin_client.get("/brain/submittal-matching/drrs").status_code == 400

    def test_link_happy_path_writes_audit_event(self, admin_client, app, seeded):
        resp = admin_client.post(
            f"/brain/submittal-matching/{seeded['drr_id']}/link",
            json={"release_id": seeded["r8_id"]},
        )
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["link_status"] == "linked"
        assert body["linked_release"]["release"] == "306"

        with app.app_context():
            s = db.session.get(Submittals, seeded["drr_id"])
            assert s.link_status == "linked"
            assert s.linked_release_id == seeded["r8_id"]
            events = SubmittalEvents.query.filter_by(submittal_id="SUB-1", source="Brain").all()
            assert len(events) == 1
            assert events[0].payload["link_status"]["new"] == "linked"
            assert events[0].payload["linked_release_id"]["new"] == seeded["r8_id"]

    def test_link_rejects_cross_job(self, admin_client, app, seeded):
        resp = admin_client.post(
            f"/brain/submittal-matching/{seeded['drr_id']}/link",
            json={"release_id": seeded["cross_job_id"]},
        )
        assert resp.status_code == 400
        assert resp.get_json()["error"] == "cross_job_link"
        with app.app_context():
            s = db.session.get(Submittals, seeded["drr_id"])
            assert s.link_status == ""

    def test_link_validates_body_and_target(self, admin_client, seeded):
        no_body = admin_client.post(f"/brain/submittal-matching/{seeded['drr_id']}/link", json={})
        assert no_body.status_code == 400
        missing = admin_client.post(
            f"/brain/submittal-matching/{seeded['drr_id']}/link", json={"release_id": 99999}
        )
        assert missing.status_code == 404
        not_a_drr = admin_client.post("/brain/submittal-matching/99999/link",
                                      json={"release_id": seeded["r8_id"]})
        assert not_a_drr.status_code == 404

    def test_no_match_and_unlink_transitions(self, admin_client, app, seeded):
        pk = seeded["other_id"]
        assert admin_client.post(f"/brain/submittal-matching/{pk}/no-match").status_code == 200
        with app.app_context():
            assert db.session.get(Submittals, pk).link_status == "no_match"

        assert admin_client.post(f"/brain/submittal-matching/{pk}/unlink").status_code == 200
        with app.app_context():
            s = db.session.get(Submittals, pk)
            assert s.link_status == ""
            assert s.linked_release_id is None

    def test_fc_span_inferred_from_close_event_and_release_date(self, admin_client, app, seeded):
        # Seed the DRR's Closed event; the linked release carries released=2026-06-20.
        with app.app_context():
            db.session.add(SubmittalEvents(
                submittal_id="SUB-1",
                action="updated",
                payload={"status": {"old": "Open", "new": "Closed"}},
                payload_hash="test-closed-hash",
                source="Procore",
                created_at=datetime(2026, 6, 18, 12, 0, 0),
            ))
            db.session.commit()

        admin_client.post(
            f"/brain/submittal-matching/{seeded['drr_id']}/link",
            json={"release_id": seeded["r8_id"]},
        )
        resp = admin_client.get("/brain/submittal-matching/drrs?project=440")
        bld8 = next(d for d in resp.get_json()["drrs"] if d["title"] == "Building 8 Pour Stop Angle")
        assert bld8["link_status"] == "linked"
        assert bld8["closed_at"].startswith("2026-06-18")
        # FC span: release date (6/20) minus DRR close (6/18) = 2 days.
        assert bld8["fc_inferred_days"] == 2

    def test_reviewed_counts_update(self, admin_client, seeded):
        admin_client.post(
            f"/brain/submittal-matching/{seeded['drr_id']}/link",
            json={"release_id": seeded["r8_id"]},
        )
        admin_client.post(f"/brain/submittal-matching/{seeded['other_id']}/no-match")
        projects = admin_client.get("/brain/submittal-matching/projects").get_json()["projects"]
        p440 = next(p for p in projects if p["project_number"] == "440")
        assert p440["linked"] == 1
        assert p440["no_match"] == 1
        assert p440["unreviewed"] == 0
