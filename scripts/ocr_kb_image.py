"""One-time OCR helper for knowledge-base/ images.

Sends every image (.webp, .png, .jpg) under knowledge-base/ to Anthropic's
vision API and writes the extracted text as a sidecar .md next to it. The
KB loader then picks up those .md files automatically — no runtime vision
calls during chat.

Usage:
    python scripts/ocr_kb_image.py                    # OCR everything missing a sidecar
    python scripts/ocr_kb_image.py --force            # re-OCR even if .md exists
    python scripts/ocr_kb_image.py path/to/file.webp  # OCR a single file
"""
import argparse
import base64
import os
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app import config as _app_config  # noqa: F401, E402  (loads .env)

KB_DIR = ROOT_DIR / "knowledge-base"
IMAGE_EXTS = {".webp", ".png", ".jpg", ".jpeg"}
MIME = {".webp": "image/webp", ".png": "image/png",
        ".jpg": "image/jpeg", ".jpeg": "image/jpeg"}
MODEL = "claude-sonnet-4-6"
MAX_TOKENS = 2048
PROMPT = (
    "You are extracting text and dimensional callouts from a technical "
    "stair/metalwork diagram so it can be used as reference text in a "
    "knowledge base. Output Markdown only — no preamble, no explanations.\n\n"
    "Include:\n"
    "- A short title heading describing what the diagram shows.\n"
    "- A bullet list of every labeled measurement, callout, code reference, "
    "  or annotation visible (e.g. 'Riser height: 7\" max', 'Tread depth: 11\"').\n"
    "- Any tables that appear in the image, transcribed as Markdown tables.\n"
    "- A brief 1–2 sentence summary at the bottom describing the diagram's "
    "  purpose (e.g. 'IBC commercial stair dimensional reference').\n\n"
    "Skip decorative elements, watermarks, and unrelated branding. If "
    "something is illegible, write '[illegible]' rather than guessing."
)


def _sidecar_path(image_path: Path) -> Path:
    return image_path.with_suffix(".md")


def _encode(image_path: Path) -> tuple[str, str]:
    data = image_path.read_bytes()
    return base64.standard_b64encode(data).decode("ascii"), MIME[image_path.suffix.lower()]


def ocr_one(image_path: Path, *, force: bool) -> bool:
    """OCR a single image. Returns True if a sidecar was written."""
    sidecar = _sidecar_path(image_path)
    if sidecar.exists() and not force:
        print(f"  skip (exists): {sidecar.name}")
        return False

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise SystemExit("ANTHROPIC_API_KEY is not set")

    import anthropic
    client = anthropic.Anthropic(api_key=api_key)

    b64, media_type = _encode(image_path)
    print(f"  OCR: {image_path.name} ({len(b64) // 1024} KB b64)")
    response = client.messages.create(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        messages=[{
            "role": "user",
            "content": [
                {"type": "image", "source": {
                    "type": "base64", "media_type": media_type, "data": b64,
                }},
                {"type": "text", "text": PROMPT},
            ],
        }],
    )
    text = "".join(
        b.text for b in response.content if getattr(b, "type", None) == "text"
    ).strip()
    if not text:
        print(f"  ✗ empty response for {image_path.name}")
        return False

    header = (
        f"<!-- Auto-generated from {image_path.name} by scripts/ocr_kb_image.py. "
        f"Edit freely; re-run with --force to regenerate. -->\n\n"
    )
    sidecar.write_text(header + text + "\n", encoding="utf-8")
    print(f"  ✓ wrote {sidecar.name} ({len(text)} chars)")
    return True


def main():
    parser = argparse.ArgumentParser(description="OCR knowledge-base images.")
    parser.add_argument("paths", nargs="*", help="Specific image paths (default: all in knowledge-base/).")
    parser.add_argument("--force", action="store_true", help="Re-OCR even if sidecar exists.")
    args = parser.parse_args()

    if args.paths:
        targets = [Path(p).resolve() for p in args.paths]
    else:
        targets = sorted(
            p for p in KB_DIR.iterdir()
            if p.suffix.lower() in IMAGE_EXTS
        )

    if not targets:
        print(f"No images found in {KB_DIR}")
        return 0

    written = 0
    for path in targets:
        if path.suffix.lower() not in IMAGE_EXTS:
            print(f"  skip (not an image): {path.name}")
            continue
        if ocr_one(path, force=args.force):
            written += 1

    print(f"\nDone. {written} sidecar file(s) written/updated.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
