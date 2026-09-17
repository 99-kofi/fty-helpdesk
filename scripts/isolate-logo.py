"""Isolate the FTY logo: white background -> transparent, artwork -> solid black.

Luminance-keyed alpha keeps the antialiased edges smooth so the cut-out
looks clean on both light and dark backgrounds.
"""
from pathlib import Path
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "fty-logo.png"
DEST = ROOT / "frontend" / "public" / "fty-logo.png"

img = Image.open(SRC).convert("L")
w, h = img.size

# Soft ramp: pure white (>=250) fully transparent, dark (<=120) fully opaque.
alpha = img.point(lambda v: 0 if v >= 250 else (255 if v <= 120 else int((250 - v) * 255 / 130)))

cut = Image.new("RGB", (w, h), (0, 0, 0)).convert("RGBA")
cut.putalpha(alpha)

# Autocrop transparent margins + small breathing room.
bbox = cut.getbbox()
assert bbox, "no artwork found"
pad = 12
l = max(0, bbox[0] - pad)
t = max(0, bbox[1] - pad)
r = min(w, bbox[2] + pad)
b = min(h, bbox[3] + pad)
cut = cut.crop((l, t, r, b))

DEST.parent.mkdir(parents=True, exist_ok=True)
cut.save(DEST)
print(f"saved {DEST} size={cut.size}")
