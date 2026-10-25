"""
Build the app icon from gui/resources/icon-source.png.

The source art has a ragged, colour-fringed edge (background removal
leftovers). We cut inside it, mask the art to a clean macOS squircle,
place it on Apple's 1024 grid (824 px body, transparent margin, soft
shadow), and write:

    gui/resources/icon.png      1024×1024, used for the window / Dock icon
    gui/resources/AppIcon.icns  macOS icon set (16 … 1024, @2x)

    python scripts/make_app_icon.py
"""
import shutil
import subprocess
import tempfile
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter

ROOT = Path(__file__).resolve().parent.parent
RES = ROOT / "gui" / "resources"
SRC = RES / "icon-source.png"

CANVAS = 1024
BODY = 824            # Apple's icon grid: body inside a 1024 canvas
INSET = 80            # px cut from each side of the source to drop the fringe
SS = 4                # supersampling for a smooth mask edge


def squircle_mask(size: int, n: float = 5.0) -> Image.Image:
    """Anti-aliased superellipse |x|^n + |y|^n <= 1 (the macOS icon shape)."""
    big = size * SS
    m = Image.new("L", (big, big), 0)
    px = m.load()
    r = big / 2
    for y in range(big):
        ny = abs((y + 0.5 - r) / r) ** n
        if ny > 1:
            continue
        half = (1 - ny) ** (1 / n) * r
        x0, x1 = int(r - half), int(r + half)
        for x in range(max(0, x0), min(big, x1)):
            px[x, y] = 255
    return m.resize((size, size), Image.LANCZOS)


def build() -> Image.Image:
    src = Image.open(SRC).convert("RGBA")
    w, h = src.size
    art = src.crop((INSET, INSET, w - INSET, h - INSET)).resize((BODY, BODY), Image.LANCZOS)
    # Opaque body: flatten onto the art's own blue so no fringe alpha survives.
    base = Image.new("RGBA", art.size, art.getpixel((BODY // 2, 12)))
    base.alpha_composite(art)
    mask = squircle_mask(BODY)
    base.putalpha(ImageChops.multiply(mask, Image.new("L", mask.size, 255)))

    canvas = Image.new("RGBA", (CANVAS, CANVAS), (0, 0, 0, 0))
    off = (CANVAS - BODY) // 2
    # soft drop shadow, like native macOS icons
    shadow = Image.new("RGBA", (CANVAS, CANVAS), (0, 0, 0, 0))
    shadow_mask = Image.new("L", (CANVAS, CANVAS), 0)
    shadow_mask.paste(mask, (off, off + 12))
    shadow.putalpha(shadow_mask.point(lambda v: v * 0.35).filter(ImageFilter.GaussianBlur(18)))
    canvas.alpha_composite(shadow)
    canvas.alpha_composite(base, (off, off))
    return canvas


def write_icns(icon: Image.Image) -> None:
    tmp = Path(tempfile.mkdtemp())
    iconset = tmp / "AppIcon.iconset"
    iconset.mkdir()
    for s in (16, 32, 128, 256, 512):
        icon.resize((s, s), Image.LANCZOS).save(iconset / f"icon_{s}x{s}.png")
        icon.resize((s * 2, s * 2), Image.LANCZOS).save(iconset / f"icon_{s}x{s}@2x.png")
    subprocess.run(["iconutil", "-c", "icns", str(iconset), "-o", str(RES / "AppIcon.icns")], check=True)
    shutil.rmtree(tmp)


if __name__ == "__main__":
    icon = build()
    icon.save(RES / "icon.png")
    write_icns(icon)
    print("wrote", RES / "icon.png", "and", RES / "AppIcon.icns")
