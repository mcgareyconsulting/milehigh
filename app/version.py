"""
@milehigh-header
schema_version: 1
purpose: Resolve the current build SHA and process start time so the backend can advertise its version to clients.
exports:
  BUILD_SHA: 7-char build identifier (Render commit, local git HEAD, or "dev")
  RELEASED_AT: ISO-8601 timestamp captured at process start
imports_from: [os, subprocess, datetime]
imported_by: [app/api/routes.py]
invariants:
  - Resolved once at import time. Restarting the process is the only way to refresh.
  - Never raises: shells out to git but swallows failures and falls back to "dev".
"""
import os
import subprocess
from datetime import datetime, timezone


def _resolve_build_sha() -> str:
    sha = os.environ.get("RENDER_GIT_COMMIT")
    if sha:
        return sha[:7]
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short=7", "HEAD"],
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        pass
    return "dev"


BUILD_SHA = _resolve_build_sha()
RELEASED_AT = datetime.now(timezone.utc).isoformat()
