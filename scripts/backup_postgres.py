"""Logical Postgres backup to Cloudflare R2 — layer 2 of the backup design.

Render's managed PITR is layer 1 (3-day window, same account as the database).
This is the independent, portable copy: a self-contained `pg_dump -Fc` that can
be restored into any Postgres, anywhere, including during a Render-wide outage.
See docs/backup-and-dr-runbook.md.

Retention is enforced by R2 lifecycle rules, not by this script — nothing here
ever deletes a remote object. The tier lives in the key prefix so each tier ages
on its own clock:

    backups/postgres/prod/daily/2026/08/09/mhmw-prod-2026-08-09T1700Z.dump
    backups/postgres/prod/weekly/...      (also written on Sundays)
    backups/postgres/prod/monthly/...     (also written on the 1st)

A Sunday run writes the same dump to daily/ and weekly/ as two independent
objects, which is what produces a real backup ladder without any cleanup code.

Usage
-----
    python -m scripts.backup_postgres                      # production (default)
    python -m scripts.backup_postgres --env sandbox
    python -m scripts.backup_postgres --skip-upload        # dump + verify only
    python -m scripts.backup_postgres --database-url postgresql://...

Exits non-zero on any failure so the Render cron surfaces a broken run.
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone

try:  # allow both `python -m scripts.backup_postgres` and direct execution
    from scripts import _r2
    from scripts._db_urls import mask, prod_url, sandbox_url
except ImportError:  # pragma: no cover - path fixup for direct execution
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from scripts import _r2
    from scripts._db_urls import mask, prod_url, sandbox_url

# Path segment per environment. Must match the R2 lifecycle rule prefixes
# exactly (backups/postgres/prod/daily/ etc.) or retention silently won't apply.
ENV_SEGMENT = {"production": "prod", "sandbox": "sandbox"}


def resolve_url(env: str, override: str | None) -> str:
    if override:
        return override
    return prod_url() if env == "production" else sandbox_url()


def key_for(env_segment: str, tier: str, now: datetime, filename: str) -> str:
    return _r2.backup_key("postgres", env_segment, tier, now, filename)


def require_tool(name: str) -> None:
    if shutil.which(name) is None:
        sys.exit(
            f"error: {name} not found on PATH.\n"
            f"Install the Postgres client tools (macOS: brew install libpq, then "
            f"add its bin to PATH). The major version must be >= the server's — "
            f"newer is fine, older is refused."
        )


def tool_version(name: str) -> str:
    """Best-effort `<tool> --version`, for the run log.

    Worth a line in every run: Render's cron image ships whatever pg_dump it
    ships, and a client older than the server fails the dump outright. Logging it
    means the first Trigger Run answers "is this image compatible?" without a
    shell, and every later run leaves a record.
    """
    try:
        result = subprocess.run(
            [name, "--version"], capture_output=True, text=True, timeout=10
        )
        return (result.stdout or result.stderr).strip() or "unknown"
    except (OSError, subprocess.SubprocessError):
        return "unknown"


def dump(url: str, out_path: str) -> None:
    """pg_dump in custom format — same flags as migrations/copy_prod_to_sandbox.sh."""
    print("  running pg_dump...")
    result = subprocess.run(
        ["pg_dump", "--no-owner", "--no-acl", "-Fc", url, "-f", out_path],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        stderr = (result.stderr or "").strip()
        if "server version" in stderr and "pg_dump version" in stderr:
            sys.exit(
                f"error: pg_dump version mismatch.\n{stderr}\n\n"
                f"Install a pg_dump whose major version is >= the server's."
            )
        sys.exit(f"error: pg_dump failed.\n{stderr}")


def verify(dump_path: str) -> None:
    """A dump that will not list is worthless — gate before uploading it."""
    print("  verifying dump is readable...")
    result = subprocess.run(
        ["pg_restore", "--list", dump_path], capture_output=True, text=True
    )
    if result.returncode != 0:
        sys.exit(
            "error: CORRUPT DUMP — pg_restore --list failed. Not uploading.\n"
            f"{(result.stderr or '').strip()}"
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--env",
        choices=sorted(ENV_SEGMENT),
        default="production",
        help="which database to back up (default: production)",
    )
    parser.add_argument("--database-url", help="explicit URL, overrides --env")
    parser.add_argument(
        "--skip-upload",
        action="store_true",
        help="dump and verify locally without touching R2 (implies --keep-local)",
    )
    parser.add_argument(
        "--keep-local", action="store_true", help="do not delete the local dump"
    )
    args = parser.parse_args()

    require_tool("pg_dump")
    require_tool("pg_restore")

    now = datetime.now(timezone.utc)
    env_segment = ENV_SEGMENT[args.env]
    url = resolve_url(args.env, args.database_url)
    stamp = f"{now:%Y-%m-%dT%H%MZ}"
    filename = f"mhmw-{env_segment}-{stamp}.dump"

    print(f"backup_postgres: {args.env} ({mask(url)}) @ {stamp}")
    print(f"  client: {tool_version('pg_dump')}")

    workdir = tempfile.mkdtemp(prefix="mhmw-backup-")
    out_path = os.path.join(workdir, filename)
    keep = args.keep_local or args.skip_upload

    try:
        dump(url, out_path)
        size_mb = os.path.getsize(out_path) / (1024 * 1024)
        print(f"  dump written: {size_mb:.1f} MB")
        verify(out_path)

        tiers = _r2.tiers_for(now)
        print(f"  tiers: {', '.join(tiers)}")

        if args.skip_upload:
            print("  --skip-upload set; would have written:")
            for tier in tiers:
                print(f"    s3://<bucket>/{key_for(env_segment, tier, now, filename)}")
            print(f"  local dump kept at {out_path}")
            return 0

        s3 = _r2.client()
        primary = key_for(env_segment, tiers[0], now, filename)
        _r2.upload(out_path, primary, s3=s3)
        # Extra tiers are server-side copies — the payload only crosses the wire once.
        for tier in tiers[1:]:
            _r2.copy(primary, key_for(env_segment, tier, now, filename), s3=s3)

        print("backup_postgres: OK")
        return 0
    finally:
        if keep:
            print(f"  (local dump retained: {out_path})")
        else:
            # A dump contains every row in the database. Never leave it on disk.
            try:
                os.unlink(out_path)
            except FileNotFoundError:
                pass
            shutil.rmtree(workdir, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
