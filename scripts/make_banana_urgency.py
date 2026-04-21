"""
Converts the pixel-art banana-boy sprite sheet into the transparent yellow PNG
used by the Job Log urgency column.

Input:  <repo>/banana-boy.png             (5-frame walk cycle, ~2816x1536, mint-green palette)
Output: <repo>/frontend/public/banana-boy.png  (~160px wide, transparent bg, yellow banana)

Run:    venv/bin/python scripts/make_banana_urgency.py
"""
from pathlib import Path
import colorsys
from PIL import Image

REPO = Path(__file__).resolve().parent.parent
SRC = REPO / "banana-boy.png"
OUT = REPO / "frontend" / "public" / "banana-boy.png"

FRAMES = 5
TARGET_WIDTH = 160  # final display ~140px, keep some headroom for retina

# Hue shift: mint/light-green → banana yellow.
# Input greens on the sprite sit roughly at hue 120°. We shift to ~52° (banana yellow).
TARGET_HUE_DEG = 52.0

# Tolerance for "this pixel is part of the green backdrop" — treat as transparent.
# Backdrop is a light mint green; body greens are more saturated / darker.
BG_RGB = (185, 233, 188)   # approximate; measured from the source
BG_TOLERANCE = 28          # Euclidean distance in RGB

# Pixels below this saturation are considered "near-neutral" (outline, feet, eyes) and
# are preserved as-is. Prevents dark outlines from turning olive after hue shift.
MIN_SAT_FOR_SHIFT = 0.12


def hue_shift_to_yellow(r: int, g: int, b: int) -> tuple[int, int, int]:
    h, s, v = colorsys.rgb_to_hsv(r / 255.0, g / 255.0, b / 255.0)
    if s < MIN_SAT_FOR_SHIFT:
        return r, g, b
    new_h = TARGET_HUE_DEG / 360.0
    nr, ng, nb = colorsys.hsv_to_rgb(new_h, s, v)
    return int(round(nr * 255)), int(round(ng * 255)), int(round(nb * 255))


def is_background(r: int, g: int, b: int) -> bool:
    dr = r - BG_RGB[0]
    dg = g - BG_RGB[1]
    db = b - BG_RGB[2]
    return (dr * dr + dg * dg + db * db) ** 0.5 <= BG_TOLERANCE


def main() -> None:
    if not SRC.exists():
        raise FileNotFoundError(f"Source sprite not found: {SRC}")

    sheet = Image.open(SRC).convert("RGBA")
    frame_w = sheet.width // FRAMES
    # Frame 1 = first standing pose, most neutral for a static icon.
    frame = sheet.crop((0, 0, frame_w, sheet.height))

    # Walk every pixel. Background → transparent; saturated greens → yellow; rest kept.
    px = frame.load()
    w, h = frame.size
    for y in range(h):
        for x in range(w):
            r, g, b, a = px[x, y]
            if a == 0:
                continue
            if is_background(r, g, b):
                px[x, y] = (0, 0, 0, 0)
                continue
            nr, ng, nb = hue_shift_to_yellow(r, g, b)
            px[x, y] = (nr, ng, nb, a)

    # Tight-crop transparent margins so the character fills the output box.
    bbox = frame.getbbox()
    if bbox:
        frame = frame.crop(bbox)

    # Downscale with NEAREST to keep pixel-art sharpness.
    aspect = frame.height / frame.width
    target_h = max(1, round(TARGET_WIDTH * aspect))
    frame = frame.resize((TARGET_WIDTH, target_h), Image.Resampling.NEAREST)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    frame.save(OUT, format="PNG", optimize=True)
    print(f"Wrote {OUT} ({frame.size[0]}x{frame.size[1]}, {OUT.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
