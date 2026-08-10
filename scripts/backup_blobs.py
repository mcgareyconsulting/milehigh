"""Blob-asset backup to Cloudflare R2 — the mounted disk, tarred nightly.

Postgres PITR does not cover a mounted filesystem, so the binaries need their
own job: marked-up PDFs, release/board/T&M photos, supplier-order attachments
and ingested lookahead PDFs all live on the Render persistent disk under
/var/data.

TEMPORARY BY DESIGN. The end state is the app writing blobs straight to object
storage (K3), at which point they are already offsite and versioned and this
script should be deleted. Until that lands, a nightly tarball is the cheap thing
that keeps the binaries recoverable.

Tars the MOUNT, not an enumerated list of subdirectories. The runbook originally
listed `pdfs photos order-attachments`, which is exactly how app/storage/lookahead
got missed — enumerate and you will forget the next one. One tar of the mount
covers everything on the disk today and anything added later.

Uses Python's tarfile rather than shelling out to tar/zstd so the job has no
external binary dependencies to go missing on a Render cron image.

Usage
-----
    python -m scripts.backup_blobs                        # /var/data (default)
    python -m scripts.backup_blobs --root /var/data
    python -m scripts.backup_blobs --skip-upload          # archive locally only

Exits non-zero on any failure so the Render cron surfaces a broken run.
"""
from __future__ import annotations

import argparse
import os
import shutil
import sys
import tarfile
import tempfile
from datetime import datetime, timezone

try:  # allow both `python -m scripts.backup_blobs` and direct execution
    from scripts import _r2
except ImportError:  # pragma: no cover - path fixup for direct execution
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from scripts import _r2

# The Render persistent disk mount. Every *_STORAGE_ROOT resolves beneath it
# once PDF_STORAGE_ROOT is set (see app/config.py).
DEFAULT_ROOT = "/var/data"


def archive(root: str, out_path: str) -> tuple[int, int]:
    """tar.gz the whole mount. Returns (file_count, uncompressed_bytes)."""
    files = 0
    raw_bytes = 0
    print(f"  archiving {root} ...")
    with tarfile.open(out_path, "w:gz") as tar:
        for dirpath, _dirnames, filenames in os.walk(root):
            for name in filenames:
                full = os.path.join(dirpath, name)
                if not os.path.isfile(full) or os.path.islink(full):
                    continue
                try:
                    raw_bytes += os.path.getsize(full)
                    tar.add(full, arcname=os.path.relpath(full, root))
                    files += 1
                except OSError as exc:  # unreadable/vanished mid-walk
                    print(f"  warning: skipped {os.path.relpath(full, root)}: {exc}")
    return files, raw_bytes


def verify(archive_path: str, expected_files: int) -> None:
    """An archive that will not list is worthless — gate before uploading."""
    print("  verifying archive is readable...")
    try:
        with tarfile.open(archive_path, "r:gz") as tar:
            found = sum(1 for m in tar.getmembers() if m.isfile())
    except (tarfile.TarError, OSError) as exc:
        sys.exit(f"error: CORRUPT ARCHIVE — cannot read it back. Not uploading.\n{exc}")
    if found != expected_files:
        sys.exit(
            f"error: archive holds {found} files but {expected_files} were added. "
            f"Not uploading."
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--root", default=DEFAULT_ROOT, help=f"disk mount to back up (default: {DEFAULT_ROOT})"
    )
    parser.add_argument(
        "--env",
        choices=("prod", "sandbox"),
        default="prod",
        help="key namespace (default: prod)",
    )
    parser.add_argument(
        "--skip-upload",
        action="store_true",
        help="archive and verify locally without touching R2 (implies --keep-local)",
    )
    parser.add_argument(
        "--keep-local", action="store_true", help="do not delete the local archive"
    )
    args = parser.parse_args()

    if not os.path.isdir(args.root):
        sys.exit(
            f"error: {args.root} does not exist or is not a directory.\n"
            f"On Render this is the persistent disk mount; locally pass --root."
        )

    now = datetime.now(timezone.utc)
    stamp = f"{now:%Y-%m-%dT%H%MZ}"
    filename = f"blobs-{stamp}.tar.gz"

    print(f"backup_blobs: {args.root} -> {args.env} @ {stamp}")

    workdir = tempfile.mkdtemp(prefix="mhmw-blobs-")
    out_path = os.path.join(workdir, filename)
    keep = args.keep_local or args.skip_upload

    try:
        files, raw_bytes = archive(args.root, out_path)
        if files == 0:
            # An empty disk is far more likely to mean a broken mount or a wrong
            # --root than a genuinely empty one. Do not upload a useless archive.
            sys.exit(
                f"error: no files found under {args.root}. Refusing to upload an "
                f"empty archive — check the mount path."
            )

        size_mb = os.path.getsize(out_path) / (1024 * 1024)
        raw_mb = raw_bytes / (1024 * 1024)
        print(f"  archived {files:,} files, {raw_mb:.1f} MB -> {size_mb:.1f} MB compressed")
        verify(out_path, files)

        tiers = [t for t in _r2.tiers_for(now) if t != "monthly"]  # blobs: no monthly tier
        print(f"  tiers: {', '.join(tiers)}")

        if args.skip_upload:
            print("  --skip-upload set; would have written:")
            for tier in tiers:
                print(f"    s3://<bucket>/{_r2.backup_key('disk', args.env, tier, now, filename)}")
            print(f"  local archive kept at {out_path}")
            return 0

        s3 = _r2.client()
        primary = _r2.backup_key("disk", args.env, tiers[0], now, filename)
        _r2.upload(out_path, primary, s3=s3)
        for tier in tiers[1:]:
            _r2.copy(primary, _r2.backup_key("disk", args.env, tier, now, filename), s3=s3)

        print("backup_blobs: OK")
        return 0
    finally:
        if keep:
            print(f"  (local archive retained: {out_path})")
        else:
            shutil.rmtree(workdir, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
