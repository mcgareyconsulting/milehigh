"""Cloudflare R2 (S3-compatible) client helper for backup scripts.

Credentials come from the environment only — never from this repo (it is public):

    R2_ENDPOINT           https://<account-id>.r2.cloudflarestorage.com
    R2_BUCKET             mhmw-data
    R2_ACCESS_KEY_ID      from the bucket-scoped R2 API token
    R2_SECRET_ACCESS_KEY  from the same token (shown once at creation)

In production these are set on the Render Cron Job service. Locally, export them
or add them to .env when you need to exercise a real upload.

Swapping providers means changing R2_ENDPOINT — every call here is plain S3.
"""
from __future__ import annotations

import os
import sys
from datetime import datetime

from dotenv import load_dotenv

load_dotenv()

# R2 hard-codes this; S3 would use a real region. Signing needs *a* value.
_REGION = "auto"

# The standing backup bucket. R2_BUCKET overrides it.
DEFAULT_BUCKET = "mhmw-data"


def _require(name: str) -> str:
    value = (os.environ.get(name) or "").strip()
    if not value:
        sys.exit(
            f"error: {name} is not set.\n"
            f"Backup uploads need R2_ENDPOINT, R2_BUCKET, R2_ACCESS_KEY_ID and "
            f"R2_SECRET_ACCESS_KEY. Set them in the environment, or pass "
            f"--skip-upload to dump and verify locally without uploading."
        )
    return value


def tiers_for(now: datetime) -> list[str]:
    """Which retention tiers a run belongs to.

    Always daily; Sundays are also weekly; the 1st is also monthly. A run writes
    the same artifact to each tier as an independent object, so each ages on its
    own lifecycle clock — that is what produces a backup ladder with no cleanup
    code. Daily is always first; callers upload that one and server-side copy
    the rest.
    """
    tiers = ["daily"]
    if now.weekday() == 6:  # Monday=0 ... Sunday=6
        tiers.append("weekly")
    if now.day == 1:
        tiers.append("monthly")
    return tiers


def backup_key(
    category: str, env_segment: str, tier: str, now: datetime, filename: str
) -> str:
    """Object key for a backup artifact.

    The first three segments must match the R2 lifecycle rule prefixes exactly
    (backups/postgres/prod/daily/, backups/disk/prod/daily/, ...) or retention
    silently will not apply and objects accumulate forever.
    """
    return f"backups/{category}/{env_segment}/{tier}/{now:%Y/%m/%d}/{filename}"


def bucket() -> str:
    """Target bucket name.

    Defaults to the standing backup bucket so a deploy cannot silently lose it.
    Environments share the bucket on purpose — they are namespaced by the key
    prefix (backups/postgres/prod/... vs .../sandbox/...), not by bucket.
    """
    return (os.environ.get("R2_BUCKET") or "").strip() or DEFAULT_BUCKET


def client():
    """boto3 S3 client pointed at R2. Exits with a clear message if unusable."""
    try:
        import boto3
    except ImportError:
        sys.exit(
            "error: boto3 is not installed.\n"
            "Run: pip install -r requirements.txt"
        )

    return boto3.client(
        "s3",
        endpoint_url=_require("R2_ENDPOINT"),
        aws_access_key_id=_require("R2_ACCESS_KEY_ID"),
        aws_secret_access_key=_require("R2_SECRET_ACCESS_KEY"),
        region_name=_REGION,
    )


def upload(local_path: str, key: str, *, s3=None) -> None:
    """Upload a file to <bucket>/<key>. boto3 splits large files automatically.

    Prints the bucket and key — never the endpoint or credentials.
    """
    s3 = s3 or client()
    name = bucket()
    size_mb = os.path.getsize(local_path) / (1024 * 1024)
    print(f"  uploading {size_mb:.1f} MB -> s3://{name}/{key}")
    s3.upload_file(local_path, name, key)


def copy(src_key: str, dst_key: str, *, s3=None) -> None:
    """Server-side copy within the bucket — no re-upload of the payload.

    Used to write a second retention tier (weekly/monthly) from an object that
    is already in R2, so a large blob tarball is only transferred once.
    """
    s3 = s3 or client()
    name = bucket()
    print(f"  copying   -> s3://{name}/{dst_key}")
    s3.copy_object(
        Bucket=name,
        Key=dst_key,
        CopySource={"Bucket": name, "Key": src_key},
    )
