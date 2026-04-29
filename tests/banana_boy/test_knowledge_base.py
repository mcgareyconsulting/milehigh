"""Tests for the knowledge-base loader and its system-prompt integration."""
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.banana_boy import client as bb_client
from app.banana_boy import knowledge_base as kb


@pytest.fixture(autouse=True)
def reset_kb_cache():
    kb.reset_cache()
    yield
    kb.reset_cache()


def test_loader_includes_primary_doc():
    text = kb.get_knowledge_base()
    assert "Division 05" in text
    assert "## Source: Division 05 Miscellaneous Metals Knowledge Base.md" in text


def test_loader_excludes_pdf_and_webp():
    """Source headers only ever name .md files, even if pdf/webp filenames
    appear elsewhere in the content as URL references."""
    text = kb.get_knowledge_base()
    source_lines = [
        line for line in text.splitlines() if line.startswith("## Source:")
    ]
    assert source_lines
    for line in source_lines:
        assert line.endswith(".md"), f"non-md source loaded: {line}"


def test_loader_caches(monkeypatch):
    real_load = kb._load
    call_count = {"n": 0}

    def counting_load():
        call_count["n"] += 1
        return real_load()

    monkeypatch.setattr(kb, "_load", counting_load)
    kb.get_knowledge_base()
    kb.get_knowledge_base()
    kb.get_knowledge_base()
    assert call_count["n"] == 1


def test_loader_skips_readme():
    text = kb.get_knowledge_base()
    assert "## Source: README.md" not in text


def test_loader_returns_empty_when_dir_missing(monkeypatch, tmp_path):
    monkeypatch.setattr(kb, "KB_DIR", tmp_path / "nope")
    assert kb.get_knowledge_base() == ""


def test_generate_reply_injects_kb_block_with_cache_control(app):
    fake_response = MagicMock()
    fake_response.stop_reason = "end_turn"
    fake_response.content = [MagicMock(type="text", text="ok")]
    fake_response.usage = MagicMock(
        input_tokens=10, output_tokens=2,
        cache_read_input_tokens=0, cache_creation_input_tokens=0,
    )

    with app.app_context(), \
         patch.object(bb_client, "_get_client") as get_client:
        fake_client = MagicMock()
        fake_client.messages.create.return_value = fake_response
        get_client.return_value = fake_client

        bb_client.generate_reply([{"role": "user", "content": "hi"}])

        kwargs = fake_client.messages.create.call_args.kwargs
        system_blocks = kwargs["system"]

    assert isinstance(system_blocks, list)
    cached_blocks = [
        b for b in system_blocks
        if isinstance(b, dict) and b.get("cache_control")
    ]
    assert len(cached_blocks) == 1
    block = cached_blocks[0]
    assert block["cache_control"] == {"type": "ephemeral"}
    assert block["text"].startswith("<knowledge_base>")
    assert "Division 05" in block["text"]
