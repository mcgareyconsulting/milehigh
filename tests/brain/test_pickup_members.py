"""Tests for pick-up card member resolution (always-on + release PM)."""
import pytest

from app.config import Config
from app.brain.job_log.features.pickup.members import parse_pm_map, resolve_member_ids

ALWAYS = "doug,fab,luis,jay"
PM_MAP = "RL:rich,GA:gary,DR:danny,WO:bill,WDO:bill"


@pytest.fixture(autouse=True)
def cfg(monkeypatch):
    monkeypatch.setattr(Config, "PICKUP_TRELLO_MEMBER_IDS", ALWAYS)
    monkeypatch.setattr(Config, "PICKUP_PM_TRELLO_IDS", PM_MAP)


def test_parse_pm_map():
    assert parse_pm_map("RL:rich, ga:gary , bad, :x, y:") == {"RL": "rich", "GA": "gary"}
    assert parse_pm_map("") == {}


@pytest.mark.parametrize("pm,expected_tail", [
    ("GA", "gary"),
    ("ga", "gary"),   # case-insensitive
    ("DR", "danny"),
    ("RL", "rich"),
    ("WDO", "bill"),
])
def test_pm_appended(pm, expected_tail):
    result = resolve_member_ids(pm)
    assert result == f"{ALWAYS},{expected_tail}"


def test_unknown_or_blank_pm_yields_always_list():
    assert resolve_member_ids("ZZ") == ALWAYS
    assert resolve_member_ids("") == ALWAYS
    assert resolve_member_ids(None) == ALWAYS


def test_pm_already_in_always_list_not_duplicated(monkeypatch):
    monkeypatch.setattr(Config, "PICKUP_TRELLO_MEMBER_IDS", "doug,gary")
    assert resolve_member_ids("GA") == "doug,gary"
