# Banana Boy Knowledge Base

> The loader skips any file named `README.md` — this doc is for humans, not for Banana Boy.

Static reference docs that get stuffed into Banana Boy's system prompt every
chat. Used for fab/install codes, dimensions, ASTM specs, IBC/OSHA/AISC/AWS/ADA
requirements — anything the crew references and shouldn't have to repeat.

## How it works

`app/banana_boy/knowledge_base.py` walks this directory at first chat after
process start, reads every `*.md` file (sorted by filename), concatenates them
with `## Source: <filename>` headers, and caches the result. The combined
string is injected into the system prompt as a `cache_control: ephemeral`
block, so Anthropic prompt caching keeps the token cost flat across turns.

The loader prompts Banana Boy to cite the source filename when answering
KB-backed questions, so you can trace any claim back to the document it came
from.

## Adding a new document

1. Drop the `.md` into this directory. Use a descriptive filename — it shows
   up in source citations.
2. Restart the Flask app (or call `reset_cache()` in a Python shell).
3. Done. The loader picks it up automatically.

## What gets ingested

| Format | Ingested? | Notes |
|---|---|---|
| `.md`     | ✅ | All Markdown files in this directory. |
| `.pdf`    | ❌ | We keep PDFs here for client distribution but do **not** extract their text — usually they duplicate a `.md` already in the KB. |
| `.webp`, `.png`, `.jpg` | ❌ at runtime | Run `scripts/ocr_kb_image.py` once per image to produce a `.md` sidecar. The sidecar gets ingested. |

## Re-running OCR on diagrams

```
ANTHROPIC_API_KEY=... python scripts/ocr_kb_image.py            # only missing sidecars
ANTHROPIC_API_KEY=... python scripts/ocr_kb_image.py --force    # regenerate all
```

The script writes a `<image_basename>.md` next to each image. Hand-edit the
output to fix any garbled callouts before committing — it's just a starting
point.

## Watch the token bill

The KB block is cached, but it still counts against the input budget on the
first turn after a deploy or after the cache TTL expires. Run
`scripts/banana_boy_usage_report.py` to see `cache_read_tokens` vs
`cache_creation_tokens` and confirm the cache is hitting on most turns.

If the KB grows past ~50 KB of text, switch from "stuff everything into the
system prompt" to a `search_knowledge_base` tool that returns matching
excerpts only. That refactor isn't needed yet at the current size.
