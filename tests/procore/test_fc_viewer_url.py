"""Unit tests for FC drawing viewer_url collection (BUG-1).

Covers Final PDF Pack resolution + type matching without live Procore calls.
"""
from unittest.mock import patch

from app.procore.procore import (
    _final_pdf_approver_ids,
    _is_for_construction,
    _normalize_viewer_url,
    get_final_pdf_viewers,
    submittals_for_release,
)


class TestTypeMatching:
    def test_type_dict_for_construction(self):
        assert _is_for_construction({"type": {"name": "For Construction"}}) is True

    def test_type_string_for_construction(self):
        assert _is_for_construction({"type": "For Construction"}) is True

    def test_type_other_rejected(self):
        assert _is_for_construction({"type": {"name": "Drafting Release Review"}}) is False


class TestNormalizeViewerUrl:
    def test_absolute_https_passthrough(self):
        url = "https://app.procore.com/webclients/host/companies/1/projects/2/tools/submittals"
        assert _normalize_viewer_url(url) == url

    def test_relative_path_prefixed(self):
        assert _normalize_viewer_url("/webclients/host/foo") == (
            "https://app.procore.com/webclients/host/foo"
        )

    def test_empty_is_none(self):
        assert _normalize_viewer_url("") is None
        assert _normalize_viewer_url(None) is None


class TestFinalPdfApproverIds:
    def test_exact_name(self):
        sub = {
            "last_distributed_submittal": {
                "distributed_responses": [
                    {"response_name": "Final PDF Pack", "submittal_approver_id": 99},
                    {"response_name": "Approved", "submittal_approver_id": 1},
                ]
            }
        }
        assert _final_pdf_approver_ids(sub) == [99]

    def test_tolerant_name_after_fc_update(self):
        sub = {
            "last_distributed_submittal": {
                "distributed_responses": [
                    {"response_name": "Final PDF Pack - Revised", "submittal_approver_id": 42},
                ]
            }
        }
        assert _final_pdf_approver_ids(sub) == [42]

    def test_missing_distribution(self):
        assert _final_pdf_approver_ids({}) == []
        assert _final_pdf_approver_ids({"last_distributed_submittal": None}) == []


class TestGetFinalPdfViewers:
    def test_list_payload_with_pack(self):
        sub = {
            "id": 1001,
            "title": "410-108 Stairs",
            "last_distributed_submittal": {
                "distributed_responses": [
                    {"response_name": "Final PDF Pack", "submittal_approver_id": 7},
                ]
            },
        }
        wf = {
            "attachments": [
                {"approver_id": 7, "name": "set.pdf", "viewer_url": "/viewer/abc"},
                {"approver_id": 9, "name": "other.pdf", "viewer_url": "/viewer/no"},
            ]
        }
        with patch("app.procore.procore.get_workflow_data", return_value=wf):
            results = get_final_pdf_viewers(55, [sub])
        assert len(results) == 1
        assert results[0]["viewer_url"] == "https://app.procore.com/viewer/abc"
        assert results[0]["submittal_id"] == 1001

    def test_detail_refetch_when_list_lacks_distribution(self):
        """BUG-1: list payload after FC update often omits last_distributed_submittal."""
        thin = {"id": 2002, "title": "410-109 Handrail"}
        detail = {
            "id": 2002,
            "title": "410-109 Handrail",
            "last_distributed_submittal": {
                "distributed_responses": [
                    {"response_name": "Final PDF Pack", "submittal_approver_id": 11},
                ]
            },
        }
        wf = {
            "attachments": [
                {"approver_id": 11, "name": "fc.pdf", "viewer_url": "/v/11"},
            ]
        }
        with patch("app.procore.procore.get_submittal_by_id", return_value=detail) as detail_fn, \
             patch("app.procore.procore.get_workflow_data", return_value=wf):
            results = get_final_pdf_viewers(55, [thin])
        detail_fn.assert_called_once_with(55, 2002)
        assert len(results) == 1
        assert results[0]["viewer_url"].endswith("/v/11")

    def test_workflow_fallback_when_no_approver_match(self):
        sub = {
            "id": 3003,
            "title": "410-110",
            "last_distributed_submittal": {
                "distributed_responses": [
                    {"response_name": "Final PDF Pack", "submittal_approver_id": 99},
                ]
            },
        }
        # Approver ids don't match and detail refetch doesn't help — fall
        # back to the final-named PDF attachment.
        wf = {
            "attachments": [
                {
                    "approver_id": 1,
                    "name": "Final Set.pdf",
                    "viewer_url": "/fallback/1",
                },
            ]
        }
        with patch("app.procore.procore.get_submittal_by_id", return_value=None), \
             patch("app.procore.procore.get_workflow_data", return_value=wf):
            results = get_final_pdf_viewers(55, [sub])
        assert len(results) >= 1
        assert results[0]["viewer_url"] == "https://app.procore.com/fallback/1"

    def test_detail_refetch_when_list_approver_ids_stale(self):
        """After an FC re-distribute the list payload can carry the OLD
        approver ids; the detail has the fresh ones that match workflow."""
        stale = {
            "id": 4004,
            "title": "410-111",
            "last_distributed_submittal": {
                "distributed_responses": [
                    {"response_name": "Final PDF Pack", "submittal_approver_id": 5},
                ]
            },
        }
        detail = {
            "id": 4004,
            "title": "410-111",
            "last_distributed_submittal": {
                "distributed_responses": [
                    {"response_name": "Final PDF Pack", "submittal_approver_id": 21},
                ]
            },
        }
        wf = {
            "attachments": [
                {"approver_id": 21, "name": "fc set.pdf", "viewer_url": "/v/21"},
            ]
        }
        with patch("app.procore.procore.get_submittal_by_id", return_value=detail) as detail_fn, \
             patch("app.procore.procore.get_workflow_data", return_value=wf):
            results = get_final_pdf_viewers(55, [stale])
        detail_fn.assert_called_once_with(55, 4004)
        assert len(results) == 1
        assert results[0]["viewer_url"] == "https://app.procore.com/v/21"
        assert results[0]["approver_id"] == 21

    def test_fallback_refuses_non_pdf_attachments(self):
        """Fallback must never link arbitrary attachments (photos, markups)."""
        thin = {"id": 5005, "title": "410-112"}
        wf = {
            "attachments": [
                {"approver_id": 1, "name": "site photo.jpg", "viewer_url": "/v/photo"},
            ]
        }
        with patch("app.procore.procore.get_submittal_by_id", return_value=None), \
             patch("app.procore.procore.get_workflow_data", return_value=wf):
            results = get_final_pdf_viewers(55, [thin])
        assert results == []


class TestSubmittalsForRelease:
    def test_filters_fc_and_identifier(self):
        all_subs = [
            {"id": 1, "title": "410-108 Stairs FC", "type": {"name": "For Construction"}},
            {"id": 2, "title": "410-108 Stairs DRR", "type": {"name": "Drafting Release Review"}},
            {"id": 3, "title": "411-108 Other", "type": {"name": "For Construction"}},
        ]
        matches = submittals_for_release(all_subs, 410, 108)
        assert len(matches) == 1
        assert matches[0]["id"] == 1
