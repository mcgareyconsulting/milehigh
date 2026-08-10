"""Storage roots must all resolve onto the mounted disk when one is configured.

Regression guard for a live bug found 2026-08-09: MATERIAL_ORDER_STORAGE_ROOT and
LOOKAHEAD_PDF_STORAGE_ROOT were read by their features but never defined in
Config, so config.get() returned None and both fell back to <repo>/app/storage/,
inside the deployed code tree. On Render that directory is wiped every deploy, so
supplier-order attachments and ingested lookahead PDFs were being destroyed while
their DB rows survived pointing at missing files.

Config is evaluated at import, so these reload the module under a patched env.
"""
import importlib

import pytest

import app.config

DISK = "/var/data/pdfs"


@pytest.fixture(autouse=True)
def _restore_config():
    """Config is module-level state — put it back for everything downstream."""
    yield
    importlib.reload(app.config)


def _config_with(monkeypatch, **env):
    for key in (
        "PDF_STORAGE_ROOT",
        "PHOTO_STORAGE_ROOT",
        "MATERIAL_ORDER_STORAGE_ROOT",
        "LOOKAHEAD_PDF_STORAGE_ROOT",
    ):
        monkeypatch.delenv(key, raising=False)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    importlib.reload(app.config)
    return app.config.Config


class TestDerivedFromMountedDisk:
    def test_every_root_lands_on_the_disk(self, monkeypatch):
        cfg = _config_with(monkeypatch, PDF_STORAGE_ROOT=DISK)
        assert cfg.PDF_STORAGE_ROOT == "/var/data/pdfs"
        assert cfg.PHOTO_STORAGE_ROOT == "/var/data/photos"
        assert cfg.MATERIAL_ORDER_STORAGE_ROOT == "/var/data/order_attachments"
        assert cfg.LOOKAHEAD_PDF_STORAGE_ROOT == "/var/data/lookahead"

    def test_no_root_escapes_the_mount(self, monkeypatch):
        # The actual invariant: nothing may resolve outside the mounted disk.
        cfg = _config_with(monkeypatch, PDF_STORAGE_ROOT=DISK)
        roots = [
            cfg.PDF_STORAGE_ROOT,
            cfg.PHOTO_STORAGE_ROOT,
            cfg.MATERIAL_ORDER_STORAGE_ROOT,
            cfg.LOOKAHEAD_PDF_STORAGE_ROOT,
        ]
        assert all(r.startswith("/var/data/") for r in roots)

    def test_derived_paths_match_the_render_env_vars(self, monkeypatch):
        # These exact values are set on the Render service. If the derivation
        # ever disagrees, prod and local would write to different directories.
        cfg = _config_with(monkeypatch, PDF_STORAGE_ROOT=DISK)
        assert cfg.MATERIAL_ORDER_STORAGE_ROOT == "/var/data/order_attachments"
        assert cfg.LOOKAHEAD_PDF_STORAGE_ROOT == "/var/data/lookahead"

    def test_trailing_slash_on_the_pdf_root_is_tolerated(self, monkeypatch):
        cfg = _config_with(monkeypatch, PDF_STORAGE_ROOT="/var/data/pdfs/")
        assert cfg.MATERIAL_ORDER_STORAGE_ROOT == "/var/data/order_attachments"
        assert cfg.LOOKAHEAD_PDF_STORAGE_ROOT == "/var/data/lookahead"


class TestExplicitOverrides:
    def test_explicit_values_win_over_derivation(self, monkeypatch):
        cfg = _config_with(
            monkeypatch,
            PDF_STORAGE_ROOT=DISK,
            MATERIAL_ORDER_STORAGE_ROOT="/mnt/other/orders",
            LOOKAHEAD_PDF_STORAGE_ROOT="/mnt/other/look",
        )
        assert cfg.MATERIAL_ORDER_STORAGE_ROOT == "/mnt/other/orders"
        assert cfg.LOOKAHEAD_PDF_STORAGE_ROOT == "/mnt/other/look"


class TestLocalDev:
    def test_without_a_disk_everything_stays_unset(self, monkeypatch):
        # No disk configured: the feature modules apply their own
        # <repo>/app/storage/... fallback. Nothing should be invented here.
        cfg = _config_with(monkeypatch)
        assert cfg.PDF_STORAGE_ROOT is None
        assert cfg.PHOTO_STORAGE_ROOT is None
        assert cfg.MATERIAL_ORDER_STORAGE_ROOT is None
        assert cfg.LOOKAHEAD_PDF_STORAGE_ROOT is None
