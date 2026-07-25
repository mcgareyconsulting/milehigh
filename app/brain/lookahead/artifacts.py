"""
@milehigh-header
schema_version: 1
purpose: Short-lived filesystem store for rendered look-ahead PDFs. Artifact ids are
  unguessable tokens; download is gated by carmen_chat auth on the route, not by
  guessing the path.
exports:
  storage_root, save_lookahead_pdf, read_lookahead_pdf, artifact_meta_path, load_meta
imports_from: [json, os, secrets, tempfile, pathlib, flask]
imported_by: [app.brain.lookahead.routes, app.brain.carmen_chat.tools, tests]
invariants:
  - Atomic write (tmp + replace).
  - Keys are token-only; never include job numbers in the filename for enumeration safety.
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

logger = get_logger(__name__)

META_SUFFIX = ".json"


def storage_root() -> Path:
    override = current_app.config.get("LOOKAHEAD_PDF_STORAGE_ROOT")
    if override:
        return Path(override)
    return Path(current_app.root_path) / "storage" / "lookahead"


def artifact_pdf_path(artifact_id: str) -> Path:
    # Guard path traversal — id is token alphabet only.
    if not artifact_id or ".." in artifact_id or "/" in artifact_id or "\\" in artifact_id:
        raise ValueError("invalid artifact id")
    return storage_root() / f"{artifact_id}.pdf"


def artifact_meta_path(artifact_id: str) -> Path:
    if not artifact_id or ".." in artifact_id or "/" in artifact_id or "\\" in artifact_id:
        raise ValueError("invalid artifact id")
    return storage_root() / f"{artifact_id}{META_SUFFIX}"


def save_lookahead_pdf(
    pdf_bytes: bytes,
    *,
    schedule: dict[str, Any],
    user_id: Optional[int] = None,
) -> dict[str, Any]:
    """Persist PDF + sidecar metadata. Returns artifact envelope for the client/tool."""
    if not pdf_bytes:
        raise ValueError("empty pdf")

    root = storage_root()
    root.mkdir(parents=True, exist_ok=True)

    artifact_id = secrets.token_urlsafe(18)
    # token_urlsafe can include - and _; still no path sep.
    final_pdf = artifact_pdf_path(artifact_id)
    final_meta = artifact_meta_path(artifact_id)

    job = schedule.get("job")
    project_name = schedule.get("project_name") or (f"Job {job}" if job is not None else "Look-ahead")
    window = schedule.get("window") or {}
    title = f"MHMW Look-Ahead — {project_name}"
    if job is not None:
        title += f" ({job})"

    meta = {
        "artifact_id": artifact_id,
        "title": title,
        "job": job,
        "project_name": project_name,
        "weeks": window.get("weeks"),
        "window_start": window.get("start"),
        "window_end": window.get("end"),
        "generated_on": schedule.get("generated_on"),
        "row_count": (schedule.get("summary") or {}).get("row_count"),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "user_id": user_id,
        "bytes": len(pdf_bytes),
        "page_size": "letter-landscape",
        "download_path": f"/brain/lookahead/artifacts/{artifact_id}.pdf",
    }

    fd, tmp_path = tempfile.mkstemp(prefix="la_", suffix=".pdf.tmp", dir=str(root))
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(pdf_bytes)
        os.replace(tmp_path, final_pdf)
        final_meta.write_text(json.dumps(meta, indent=2), encoding="utf-8")
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        try:
            final_pdf.unlink(missing_ok=True)
        except OSError:
            pass
        raise

    logger.debug(
        "lookahead_pdf_saved",
        artifact_id=artifact_id,
        job=job,
        bytes=len(pdf_bytes),
        user_id=user_id,
    )
    return meta


def read_lookahead_pdf(artifact_id: str) -> bytes:
    path = artifact_pdf_path(artifact_id)
    if not path.is_file():
        raise FileNotFoundError(artifact_id)
    return path.read_bytes()


def load_meta(artifact_id: str) -> Optional[dict[str, Any]]:
    path = artifact_meta_path(artifact_id)
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
