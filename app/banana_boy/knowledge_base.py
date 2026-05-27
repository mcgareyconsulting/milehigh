"""Static knowledge base loader for Banana Boy.

Reads every .md file under knowledge-base/ at process start (lazy on first
call), concatenates with source headers, and caches the result. The combined
string is injected into Banana Boy's system prompt as a cache_control block
so Anthropic prompt caching keeps it cheap across turns.

Returns "" when the directory is missing or empty (e.g. test envs) — the
chat keeps working without it.
"""
from pathlib import Path
from threading import Lock

from app.logging_config import get_logger

logger = get_logger(__name__)

KB_DIR = Path(__file__).resolve().parents[2] / "knowledge-base"

_cache: str | None = None
_lock = Lock()


def _load() -> str:
    if not KB_DIR.is_dir():
        logger.info("kb_dir_missing", path=str(KB_DIR))
        return ""

    md_files = sorted(
        p for p in KB_DIR.glob("*.md")
        if p.stem.lower() != "readme"
    )
    if not md_files:
        logger.info("kb_dir_empty", path=str(KB_DIR))
        return ""

    parts = []
    for path in md_files:
        try:
            content = path.read_text(encoding="utf-8").strip()
        except OSError as exc:
            logger.warning("kb_read_failed", file=path.name, error=str(exc))
            continue
        if not content:
            continue
        parts.append(f"## Source: {path.name}\n\n{content}")

    combined = "\n\n---\n\n".join(parts)
    logger.info("kb_loaded", file_count=len(parts), char_count=len(combined))
    return combined


def get_knowledge_base() -> str:
    """Return the concatenated knowledge base, cached after first call."""
    global _cache
    if _cache is not None:
        return _cache
    with _lock:
        if _cache is None:
            _cache = _load()
    return _cache


def reset_cache() -> None:
    """Clear the in-memory cache. Used by tests."""
    global _cache
    with _lock:
        _cache = None
