"""Tests for update_mirror_card_content — pushing a regenerated primary card
title/description onto its linked mirror card (the mirror is a full clone at
creation time, per copy_trello_card's keepFromSource="all", but nothing else
keeps the two in sync afterward)."""
from unittest.mock import patch

from app.trello import api as trello_api


def _attachments_ok(short_link="mShort"):
    return {"success": True, "attachments": [{"name": "Linked card", "fileName": short_link}]}


def _attachments_no_mirror():
    return {"success": True, "attachments": [{"name": "FC Drawing", "fileName": "other"}]}


def test_uses_provided_mirror_card_id_without_extra_lookup():
    with patch.object(trello_api, "get_card_attachments_by_card_id") as mock_attachments, \
         patch.object(trello_api, "update_trello_card_name") as mock_name, \
         patch.object(trello_api, "update_trello_card_description") as mock_desc:
        result = trello_api.update_mirror_card_content(
            "primary-1", new_title="New Title", new_description="New Desc", mirror_card_id="mirror-999",
        )

    mock_attachments.assert_not_called()
    mock_name.assert_called_once_with("mirror-999", "New Title")
    mock_desc.assert_called_once_with("mirror-999", "New Desc")
    assert result == "mirror-999"


def test_falls_back_to_attachment_resolution_when_no_hint():
    with patch.object(trello_api, "get_card_attachments_by_card_id", return_value=_attachments_ok()), \
         patch.object(trello_api, "update_trello_card_name") as mock_name, \
         patch.object(trello_api, "update_trello_card_description") as mock_desc:
        result = trello_api.update_mirror_card_content("primary-1", new_title="New Title")

    mock_name.assert_called_once_with("mShort", "New Title")
    mock_desc.assert_not_called()
    assert result == "mShort"


def test_noop_when_no_mirror_linked():
    with patch.object(trello_api, "get_card_attachments_by_card_id", return_value=_attachments_no_mirror()), \
         patch.object(trello_api, "update_trello_card_name") as mock_name, \
         patch.object(trello_api, "update_trello_card_description") as mock_desc:
        result = trello_api.update_mirror_card_content("primary-1", new_title="New Title")

    mock_name.assert_not_called()
    mock_desc.assert_not_called()
    assert result is None


def test_noop_when_nothing_to_push():
    with patch.object(trello_api, "get_card_attachments_by_card_id") as mock_attachments:
        result = trello_api.update_mirror_card_content("primary-1")

    mock_attachments.assert_not_called()
    assert result is None


def test_pushes_only_description_when_only_description_given():
    with patch.object(trello_api, "get_card_attachments_by_card_id", return_value=_attachments_ok()), \
         patch.object(trello_api, "update_trello_card_name") as mock_name, \
         patch.object(trello_api, "update_trello_card_description") as mock_desc:
        trello_api.update_mirror_card_content("primary-1", new_description="New Desc")

    mock_name.assert_not_called()
    mock_desc.assert_called_once_with("mShort", "New Desc")
