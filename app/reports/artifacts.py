"""
@milehigh-header
schema_version: 1
purpose: Short-lived PDF and CSV files for a release report Carmen built. The bytes
  are the report render. Download is gated on the route.
exports:
  save_release_report, read_release_report, load_meta
imports_from: [json, os, secrets, pathlib, flask]
imported_by: [app.brain.carmen_chat.release_report, app.reports.carmen_routes, tests]
invariants:
  - Artifact ids are token-only. Path separators are rejected.
  - The PDF and the CSV share one id and one filter set.
"""
from __future__ import annotations

import json
import os
import secrets
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from flask import current_app

from app.logging_config import get_logger
from app.reports.release_query import report_filename

logger = get_logger(__name__)

_EXTS = {"pdf": ".pdf", "csv": ".csv", "json": ".json"}


def storage_root() -> Path:
    override = current_app.config.get("REPORT_ARTIFACT_STORAGE_ROOT")
    if override:
        return Path(override)
    return Path(current_app.root_path) / "storage" / "release_reports"


def _check_id(artifact_id: str) -> str:
    if (
        not artifact_id
        or ".." in artifact_id
        or "/" in artifact_id
        or "\\" in artifact_id
        or artifact_id != artifact_id.strip()
    ):
        raise ValueError("invalid artifact id")
    return artifact_id


def _path(artifact_id: str, ext: str) -> Path:
    if ext not in _EXTS:
        raise ValueError("invalid artifact type")
    return storage_root() / f"{_check_id(artifact_id)}{_EXTS[ext]}"


def save_release_report(
    pdf_bytes: bytes,
    csv_text: str,
    *,
    report: dict,
    user_id: Optional[int] = None,
) -> dict[str, Any]:
    """Write the PDF, the CSV, and a sidecar. Returns the download envelope."""
    if not pdf_bytes or not csv_text:
        raise ValueError("empty report file")

    root = storage_root()
    root.mkdir(parents=True, exist_ok=True)
    artifact_id = secrets.token_urlsafe(18)
    pdf_path = _path(artifact_id, "pdf")
    csv_path = _path(artifact_id, "csv")
    meta_path = _path(artifact_id, "json")
    totals = report.get("totals") or {}
    title = "Release report"
    summary = report.get("summary") or ""
    if summary:
        title = f"Release report — {summary}"[:180]

    meta = {
        "artifact_id": artifact_id,
        "title": title,
        "summary": summary,
        "scope": report.get("scope"),
        "group_by": report.get("group_by"),
        "releases": totals.get("releases"),
        "fab_hrs": totals.get("fab_hrs"),
        "install_hrs": totals.get("install_hrs"),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "user_id": user_id,
        "pdf_download_path": f"/brain/reports/artifacts/{artifact_id}.pdf",
        "csv_download_path": f"/brain/reports/artifacts/{artifact_id}.csv",
        "pdf_filename": report_filename(report, "pdf"),
        "csv_filename": report_filename(report, "csv"),
    }

    written: list[Path] = []
    try:
        _write_bytes(pdf_path, pdf_bytes, root)
        written.append(pdf_path)
        _write_bytes(csv_path, csv_text.encode("utf-8"), root)
        written.append(csv_path)
        meta_path.write_text(json.dumps(meta), encoding="utf-8")
    except Exception:
        for path in written:
            path.unlink(missing_ok=True)
        meta_path.unlink(missing_ok=True)
        raise

    logger.debug(
        "release_report_saved",
        artifact_id=artifact_id,
        releases=totals.get("releases"),
        user_id=user_id,
    )
    return meta


def _write_bytes(path: Path, payload: bytes, root: Path) -> None:
    fd, tmp = tempfile.mkstemp(prefix="rr_", dir=str(root))
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(payload)
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def read_release_report(artifact_id: str, ext: str) -> bytes:
    path = _path(artifact_id, ext)
    if not path.is_file():
        raise FileNotFoundError(artifact_id)
    return path.read_bytes()


def load_meta(artifact_id: str) -> Optional[dict[str, Any]]:
    path = _path(artifact_id, "json")
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
