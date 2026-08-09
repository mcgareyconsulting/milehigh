"""Resolve Postgres connection URLs for operational scripts from the environment.

Credentials must never be hardcoded in this repo (it is public). Each URL comes from
an env var, matching the names app/db_config.py already uses:

    PRODUCTION_DATABASE_URL  (falls back to DATABASE_URL)
    SANDBOX_DATABASE_URL

Set them in .env or export them before running a script. A missing var exits with a
clear message rather than silently connecting somewhere unexpected.
"""
import os
import sys

from dotenv import load_dotenv

load_dotenv()


def _require(name: str, *fallbacks: str) -> str:
    for var in (name, *fallbacks):
        value = (os.environ.get(var) or "").strip()
        if value:
            return value
    names = " or ".join((name, *fallbacks))
    sys.exit(
        f"error: {names} is not set.\n"
        f"Add it to .env or export it before running this script."
    )


def prod_url() -> str:
    """Production Postgres URL. Exits if unset."""
    return _require("PRODUCTION_DATABASE_URL", "DATABASE_URL")


def sandbox_url() -> str:
    """Sandbox Postgres URL. Exits if unset."""
    return _require("SANDBOX_DATABASE_URL")


def mask(url: str) -> str:
    """host/db only — never print credentials."""
    tail = url.split("@")[-1] if "@" in url else url
    return tail.split("/")[-1] if "/" in tail else tail
