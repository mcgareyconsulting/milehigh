"""Pure unit tests for backup tier selection and R2 key layout.

No Flask, no DB, no network. These guard the two things that would silently
break retention: the tier a run belongs to, and the key prefix that the R2
lifecycle rules match on. A typo in either means objects never expire (cost) or
expire on the wrong clock (data loss).
"""
from datetime import datetime, timezone

import pytest

from scripts._r2 import backup_key, tiers_for
from scripts.backup_postgres import ENV_SEGMENT, key_for


def _utc(iso: str) -> datetime:
    return datetime.fromisoformat(iso).replace(tzinfo=timezone.utc)


class TestTiers:
    def test_weekday_is_daily_only(self):
        assert tiers_for(_utc("2026-08-10")) == ["daily"]  # Monday

    def test_sunday_adds_weekly(self):
        assert tiers_for(_utc("2026-08-09")) == ["daily", "weekly"]  # Sunday

    def test_first_of_month_adds_monthly(self):
        assert tiers_for(_utc("2026-09-01")) == ["daily", "monthly"]  # Tuesday

    def test_first_of_month_on_a_sunday_hits_all_three(self):
        assert tiers_for(_utc("2026-11-01")) == ["daily", "weekly", "monthly"]

    def test_daily_is_always_first(self):
        # The primary upload is tiers[0]; extra tiers are server-side copies of it.
        for day in ("2026-08-09", "2026-08-10", "2026-09-01", "2026-11-01"):
            assert tiers_for(_utc(day))[0] == "daily"


class TestKeys:
    def test_key_matches_lifecycle_rule_prefix(self):
        key = key_for("prod", "daily", _utc("2026-08-09"), "mhmw-prod-x.dump")
        assert key.startswith("backups/postgres/prod/daily/")
        assert key == "backups/postgres/prod/daily/2026/08/09/mhmw-prod-x.dump"

    def test_month_and_day_are_zero_padded(self):
        # Unpadded segments would still match the prefix rule, but sort wrong in
        # the bucket listing, which is what a human browses during an incident.
        key = key_for("prod", "monthly", _utc("2026-09-01"), "f.dump")
        assert "/2026/09/01/" in key

    def test_each_tier_gets_a_distinct_key(self):
        now = _utc("2026-11-01")
        keys = {key_for("prod", t, now, "f.dump") for t in tiers_for(now)}
        assert len(keys) == 3

    def test_production_maps_to_the_prod_segment(self):
        # The lifecycle rules are written against 'prod', not 'production'.
        assert ENV_SEGMENT["production"] == "prod"
        assert key_for(ENV_SEGMENT["production"], "daily", _utc("2026-08-09"), "f").startswith(
            "backups/postgres/prod/"
        )

    def test_sandbox_keys_are_not_covered_by_prod_rules(self):
        key = key_for(ENV_SEGMENT["sandbox"], "daily", _utc("2026-08-09"), "f")
        assert not key.startswith("backups/postgres/prod/")


class TestShrinkGuard:
    """A dump can exit zero having captured far less than it should.

    Reduced privileges are the usual cause: valid archive, readable table of
    contents, most of the database missing. Every other check passes it. Size
    versus the previous artifact is the only signal that catches it.
    """

    def _guard(self, monkeypatch, previous_size, new_size, allow_shrink=False):
        from scripts import _r2, backup_postgres

        monkeypatch.setattr(
            _r2,
            "latest_object",
            lambda prefix, s3=None: (
                None
                if previous_size is None
                else {"Size": previous_size, "Key": "prev.dump"}
            ),
        )
        backup_postgres.check_not_shrunk(
            None, "prod", new_size, allow_shrink=allow_shrink
        )

    def test_first_run_has_nothing_to_compare(self, monkeypatch):
        self._guard(monkeypatch, None, 5_000_000)  # must not raise

    def test_same_size_passes(self, monkeypatch):
        self._guard(monkeypatch, 5_000_000, 5_000_000)

    def test_modest_shrink_passes(self, monkeypatch):
        # Real databases fluctuate; the guard is a tripwire, not a trend monitor.
        self._guard(monkeypatch, 5_000_000, 3_000_000)  # 60%

    def test_growth_passes(self, monkeypatch):
        self._guard(monkeypatch, 5_000_000, 9_000_000)

    def test_collapse_blocks_the_upload(self, monkeypatch):
        with pytest.raises(SystemExit):
            self._guard(monkeypatch, 5_000_000, 1_000_000)  # 20%

    def test_collapse_can_be_overridden(self, monkeypatch):
        # A genuine purge or dropped table is a legitimate reason to shrink.
        self._guard(monkeypatch, 5_000_000, 1_000_000, allow_shrink=True)


class TestBlobKeys:
    """Blob archives use the same scheme under a different category."""

    def test_matches_the_disk_lifecycle_prefix(self):
        key = backup_key("disk", "prod", "daily", _utc("2026-08-09"), "blobs-x.tar.gz")
        assert key == "backups/disk/prod/daily/2026/08/09/blobs-x.tar.gz"

    def test_blobs_have_no_monthly_rule_so_drop_that_tier(self):
        # Only five delete rules exist; backups/disk/prod/monthly/ is not one of
        # them, so a monthly blob object would never expire.
        now = _utc("2026-11-01")  # a Sunday and the 1st — all three tiers
        blob_tiers = [t for t in tiers_for(now) if t != "monthly"]
        assert blob_tiers == ["daily", "weekly"]

    def test_postgres_and_disk_categories_do_not_collide(self):
        now = _utc("2026-08-09")
        assert backup_key("disk", "prod", "daily", now, "f") != backup_key(
            "postgres", "prod", "daily", now, "f"
        )
