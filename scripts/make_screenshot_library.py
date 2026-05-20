#!/usr/bin/env python3
"""
Generate 5 fictional manga / anime comics for App Store screenshots.

Each cover is composed of manga-native visual primitives: halftone
screentones, speed lines, large kanji / katakana, anime character
silhouettes, stylized eyes, and dramatic typography — i.e. things
that read as manga at thumbnail size, not just "indie book covers".

Run:
    python scripts/make_screenshot_library.py

Activate for a screenshot session:
    mv library.json library.json.real
    cp screenshots_library/library.json library.json
    python gui/main.py
    # take screenshots, then restore:
    mv library.json.real library.json
"""

from __future__ import annotations

import io
import json
import math
import random
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont


# ------------------------------------------------------------ paths
PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = PROJECT_ROOT / "screenshots_library"

FONT_BOLD = "/System/Library/Fonts/HelveticaNeue.ttc"
FONT_REGULAR = "/System/Library/Fonts/Avenir Next.ttc"
FONT_JP = "/System/Library/Fonts/Hiragino Sans GB.ttc"


def _font(path: str, size: int, index: int = 0) -> ImageFont.FreeTypeFont:
    try:
        return ImageFont.truetype(path, size=size, index=index)
    except Exception:
        return ImageFont.load_default()


# ------------------------------------------------------------ comics
COMICS: list[dict] = [
    {
        "key": "starlight_academy",
        "title": "Starlight Academy",
        "title_jp": "スターライト学園",
        "kanji_motif": "キラ",
        "alt_titles": ["スターライト学園", "Starlight Gakuen"],
        "source": "comix",
        "source_url": "https://comix.to/title/sla7x-starlight-academy",
        "tags": ["School Life", "Magical Girls", "Romance", "Fantasy"],
        "artists": ["Yuki Hoshino"],
        "status": "ongoing",
        "chapter_count": 24,
        "subtitle": "Vol. 3 — Awakening",
        "palette": "starlight",
        "genre_tag": "少女 · MAGICAL",
        "vol_number": "VOL. 03",
        "compose": "starlight",
        "alt_sources": [
            {"provider": "toonily",
             "url": "https://toonily.com/serie/starlight-academy",
             "title_on_site": "Starlight Academy",
             "status": "ongoing", "chapter_count": 22},
            {"provider": "mangafire",
             "url": "https://mangafire.to/manga/starlight-academy.x9k2x",
             "title_on_site": "Starlight Academy",
             "status": "ongoing", "chapter_count": 24},
        ],
    },
    {
        "key": "phantom_blade_chronicles",
        "title": "Phantom Blade Chronicles",
        "title_jp": "幻刃録",
        "kanji_motif": "斬",
        "alt_titles": ["幻刃録", "Maboroshi no Tsurugi"],
        "source": "mangafire",
        "source_url": "https://mangafire.to/manga/phantom-blade-chronicles.p3b8c",
        "tags": ["Action", "Historical", "Supernatural", "Samurai"],
        "artists": ["Ryo Tachibana", "Akiko Yamazaki"],
        "status": "completed",
        "chapter_count": 87,
        "subtitle": "The Complete Saga",
        "palette": "phantom",
        "genre_tag": "少年 · ACTION",
        "vol_number": "完 · COMPLETE",
        "compose": "phantom",
        "alt_sources": [
            {"provider": "manhwabuddy",
             "url": "https://manhwabuddy.com/manhwa/phantom-blade-chronicles",
             "title_on_site": "Phantom Blade Chronicles",
             "status": "completed", "chapter_count": 87},
        ],
    },
    {
        "key": "neon_heart_tokyo",
        "title": "Neon Heart Tokyo",
        "title_jp": "ネオンハート東京",
        "kanji_motif": "東京",
        "alt_titles": ["ネオンハート東京", "Neon Heart Shibuya"],
        "source": "toonily",
        "source_url": "https://toonily.com/serie/neon-heart-tokyo",
        "tags": ["Cyberpunk", "Romance", "Drama", "Sci-Fi"],
        "artists": ["Mei Sakamoto"],
        "status": "ongoing",
        "chapter_count": 12,
        "subtitle": "Vol. 2 — Static",
        "palette": "neon",
        "genre_tag": "青年 · CYBERPUNK",
        "vol_number": "VOL. 02",
        "compose": "neon",
        "alt_sources": [],
    },
    {
        "key": "the_last_dragonslayer",
        "title": "The Last Dragonslayer",
        "title_jp": "最後の竜殺し",
        "kanji_motif": "龍",
        "alt_titles": ["最後の竜殺し", "Saigo no Ryū Goroshi"],
        "source": "comix",
        "source_url": "https://comix.to/title/dr8sl-the-last-dragonslayer",
        "tags": ["Fantasy", "Adventure", "Action", "Magic"],
        "artists": ["Daichi Kuroda"],
        "status": "completed",
        "chapter_count": 156,
        "subtitle": "Complete Edition · Ch. 1–156",
        "palette": "dragon",
        "genre_tag": "少年 · EPIC",
        "vol_number": "完 · 156 CH",
        "compose": "dragon",
        "alt_sources": [
            {"provider": "manhwaread",
             "url": "https://manhwaread.com/manhwa/the-last-dragonslayer",
             "title_on_site": "The Last Dragonslayer",
             "status": "completed", "chapter_count": 156},
            {"provider": "mangadistrict",
             "url": "https://mangadistrict.com/series/the-last-dragonslayer",
             "title_on_site": "The Last Dragonslayer",
             "status": "completed", "chapter_count": 154},
            {"provider": "manhwa18",
             "url": "https://www.manhwa18.com/manga/the-last-dragonslayer",
             "title_on_site": "The Last Dragonslayer",
             "status": "completed", "chapter_count": 156},
        ],
    },
    {
        "key": "coffee_shop_confessions",
        "title": "Coffee Shop Confessions",
        "title_jp": "カフェの告白",
        "kanji_motif": "恋",
        "alt_titles": ["カフェの告白"],
        "source": "manhwabuddy",
        "source_url": "https://manhwabuddy.com/manhwa/coffee-shop-confessions",
        "tags": ["Slice of Life", "Romance", "Comedy", "Drama"],
        "artists": ["Hana Asakura"],
        "status": "ongoing",
        "chapter_count": 8,
        "subtitle": "Brewing · Chapter 8",
        "palette": "coffee",
        "genre_tag": "少女 · SLICE",
        "vol_number": "VOL. 01",
        "compose": "coffee",
        "alt_sources": [],
    },
]


# ------------------------------------------------------------ palettes
PALETTES = {
    "starlight": {
        "bg_top":    (255, 192, 222),
        "bg_bottom": (130, 200, 240),
        "shape":     (255, 250, 255),
        "accent":    (255, 80, 160),
        "deep":      (90, 30, 110),
        "ink":       (35, 15, 60),
        "card":      (255, 255, 255, 240),
        "card_ink":  (60, 30, 80),
        "tag_bg":    (255, 80, 160),
        "tag_ink":   (255, 255, 255),
    },
    "phantom": {
        "bg_top":    (16, 6, 10),
        "bg_bottom": (110, 14, 28),
        "shape":     (235, 195, 95),
        "accent":    (220, 50, 60),
        "deep":      (8, 2, 6),
        "ink":       (245, 235, 215),
        "card":      (10, 4, 8, 235),
        "card_ink":  (235, 195, 95),
        "tag_bg":    (235, 195, 95),
        "tag_ink":   (16, 6, 10),
    },
    "neon": {
        "bg_top":    (10, 5, 35),
        "bg_bottom": (190, 30, 130),
        "shape":     (60, 230, 250),
        "accent":    (255, 80, 200),
        "deep":      (4, 2, 16),
        "ink":       (255, 255, 255),
        "card":      (6, 2, 18, 235),
        "card_ink":  (60, 230, 250),
        "tag_bg":    (255, 80, 200),
        "tag_ink":   (10, 5, 35),
    },
    "dragon": {
        "bg_top":    (12, 22, 16),
        "bg_bottom": (110, 80, 24),
        "shape":     (250, 200, 80),
        "accent":    (220, 150, 40),
        "deep":      (8, 14, 10),
        "ink":       (250, 230, 180),
        "card":      (10, 16, 12, 240),
        "card_ink":  (250, 220, 130),
        "tag_bg":    (250, 200, 80),
        "tag_ink":   (12, 22, 16),
    },
    "coffee": {
        "bg_top":    (78, 48, 32),
        "bg_bottom": (245, 215, 170),
        "shape":     (250, 230, 195),
        "accent":    (200, 90, 80),
        "deep":      (40, 22, 16),
        "ink":       (50, 28, 20),
        "card":      (255, 250, 240, 240),
        "card_ink":  (78, 48, 32),
        "tag_bg":    (78, 48, 32),
        "tag_ink":   (250, 230, 195),
    },
}


# ============================================================ primitives

COVER_W, COVER_H = 600, 800


def _gradient(top: tuple, bot: tuple, w: int, h: int) -> Image.Image:
    t = np.linspace(0.0, 1.0, h, dtype=np.float32).reshape(h, 1, 1)
    top_arr = np.array(top, dtype=np.float32).reshape(1, 1, 3)
    bot_arr = np.array(bot, dtype=np.float32).reshape(1, 1, 3)
    col = top_arr * (1.0 - t) + bot_arr * t      # (h, 1, 3)
    arr = np.broadcast_to(col, (h, w, 3)).astype(np.uint8)
    return Image.fromarray(arr, "RGB")


def _halftone(img: Image.Image, color: tuple, alpha: int = 120,
              step: int = 14, dot: int = 5,
              region: tuple | None = None) -> None:
    """Manga screentone — uniform dot grid with slight jitter."""
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(overlay)
    rng = random.Random(0xC0FFEE)
    x0, y0, x1, y1 = region if region else (0, 0, *img.size)
    for y in range(y0, y1, step):
        offset = (step // 2) if (y // step) % 2 else 0
        for x in range(x0 + offset, x1, step):
            jx, jy = rng.randint(-1, 1), rng.randint(-1, 1)
            r = dot + rng.choice((-1, 0, 0, 1))
            d.ellipse([x + jx - r, y + jy - r, x + jx + r, y + jy + r],
                      fill=color + (alpha,))
    img.alpha_composite(overlay)


def _speedlines(img: Image.Image, cx: int, cy: int, *,
                count: int = 80, length: int = 700,
                inner: int = 120, color: tuple = (255, 255, 255),
                alpha: int = 200, width: int = 3,
                spread_deg: tuple | None = None) -> None:
    """Radial action lines emanating from (cx, cy)."""
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(overlay)
    rng = random.Random(0xBEEF)
    for _ in range(count):
        if spread_deg:
            ang = math.radians(rng.uniform(*spread_deg))
        else:
            ang = rng.uniform(0, math.tau)
        r_in = inner + rng.randint(0, 40)
        r_out = r_in + rng.randint(int(length * 0.4), length)
        x1 = cx + math.cos(ang) * r_in
        y1 = cy + math.sin(ang) * r_in
        x2 = cx + math.cos(ang) * r_out
        y2 = cy + math.sin(ang) * r_out
        w = rng.choice((width - 1, width, width, width + 1))
        a = rng.randint(int(alpha * 0.5), alpha)
        d.line([(x1, y1), (x2, y2)], fill=color + (a,), width=max(1, w))
    img.alpha_composite(overlay)


def _ink_splatter(img: Image.Image, color: tuple, *,
                  count: int = 90, alpha_range=(80, 200),
                  region: tuple | None = None) -> None:
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(overlay)
    rng = random.Random(0xF00D)
    x0, y0, x1, y1 = region if region else (0, 0, *img.size)
    for _ in range(count):
        cx = rng.randint(x0, x1)
        cy = rng.randint(y0, y1)
        r = rng.choice((2, 2, 3, 4, 5, 7, 10))
        a = rng.randint(*alpha_range)
        d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=color + (a,))
        if rng.random() < 0.18:
            # Long drip
            d.line([(cx, cy), (cx + rng.randint(-2, 2),
                               cy + rng.randint(8, 30))],
                   fill=color + (a,), width=2)
    img.alpha_composite(overlay)


def _kanji_decoration(img: Image.Image, text: str, font_size: int,
                      color: tuple, alpha: int, x: int, y: int,
                      rotate: float = 0, outline: tuple | None = None,
                      outline_w: int = 0) -> None:
    """Big translucent kanji as background decoration."""
    f = _font(FONT_JP, font_size)
    tmp = Image.new("RGBA",
                    (font_size * len(text) + 80, font_size + 80),
                    (0, 0, 0, 0))
    td = ImageDraw.Draw(tmp)
    if outline and outline_w:
        for dx in range(-outline_w, outline_w + 1):
            for dy in range(-outline_w, outline_w + 1):
                if dx or dy:
                    td.text((40 + dx, 30 + dy), text,
                            font=f, fill=outline + (alpha,))
    td.text((40, 30), text, font=f, fill=color + (alpha,))
    if rotate:
        tmp = tmp.rotate(rotate, resample=Image.BICUBIC, expand=True)
    img.alpha_composite(tmp, (x, y))


def _anime_eye(img: Image.Image, cx: int, cy: int, size: int,
               iris: tuple, highlight: tuple = (255, 255, 255),
               liner: tuple = (25, 10, 40)) -> None:
    """Stylized shoujo manga eye — big iris, star highlight, eyelashes."""
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(overlay)
    w, h = size * 2, int(size * 1.3)

    # Eye-white almond shape (slightly tilted)
    almond = Image.new("RGBA", (w + 20, h + 20), (0, 0, 0, 0))
    ad = ImageDraw.Draw(almond)
    ad.ellipse([10, 10, w + 10, h + 10], fill=(255, 255, 255, 255))
    overlay.alpha_composite(almond, (cx - w // 2 - 10, cy - h // 2 - 10))

    # Iris — large filled circle with rim ring
    ir = int(size * 0.55)
    d.ellipse([cx - ir, cy - ir, cx + ir, cy + ir], fill=iris + (255,))
    d.ellipse([cx - ir, cy - ir, cx + ir, cy + ir],
              outline=liner + (255,), width=4)

    # Inner pupil
    pr = int(ir * 0.45)
    d.ellipse([cx - pr, cy - pr, cx + pr, cy + pr], fill=liner + (255,))

    # Star-shaped highlight (4-point sparkle)
    hr = int(ir * 0.35)
    hx, hy = cx - int(ir * 0.35), cy - int(ir * 0.35)
    d.polygon(
        [(hx, hy - hr), (hx + hr * 0.22, hy - hr * 0.22),
         (hx + hr, hy), (hx + hr * 0.22, hy + hr * 0.22),
         (hx, hy + hr), (hx - hr * 0.22, hy + hr * 0.22),
         (hx - hr, hy), (hx - hr * 0.22, hy - hr * 0.22)],
        fill=highlight + (255,))
    # Small secondary highlight dot
    d.ellipse([cx + int(ir * 0.3), cy + int(ir * 0.1),
               cx + int(ir * 0.55), cy + int(ir * 0.35)],
              fill=highlight + (255,))

    # Eyelid line above
    d.arc([cx - w // 2, cy - h // 2 - 4,
           cx + w // 2, cy + h // 2 - 4],
          start=190, end=350,
          fill=liner + (255,), width=6)

    # Eyelashes — short angled lines along the upper lid
    for i in range(7):
        t = i / 6
        ang = math.radians(190 + 160 * t)
        rx = (w // 2) * math.cos(ang)
        ry = (h // 2) * math.sin(ang)
        ex, ey = cx + rx, cy + ry - 4
        # Outward kick
        out_x = ex + math.cos(ang) * 18
        out_y = ey + math.sin(ang) * 18 - 8
        d.line([(ex, ey), (out_x, out_y)], fill=liner + (255,), width=4)

    # Blush dot under the eye
    blush = (255, 130, 170, 100)
    d.ellipse([cx - 30, cy + h // 2 + 8, cx + 30, cy + h // 2 + 24],
              fill=blush)

    img.alpha_composite(overlay)


def _samurai_silhouette(img: Image.Image, cx: int, cy: int,
                        color: tuple) -> None:
    """Side-view samurai with raised katana, simplified silhouette."""
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(overlay)

    # Body / robe — broad shoulder triangle into narrower waist
    body = [
        (cx - 90, cy + 200),       # bottom-left hem
        (cx - 130, cy + 60),       # left shoulder out
        (cx - 80, cy + 20),        # left shoulder top
        (cx - 30, cy + 10),        # neck left
        (cx + 30, cy + 10),        # neck right
        (cx + 80, cy + 20),        # right shoulder top
        (cx + 130, cy + 60),       # right shoulder out
        (cx + 90, cy + 200),       # bottom-right hem
    ]
    d.polygon(body, fill=color + (255,))

    # Head (topknot warrior)
    hr = 42
    d.ellipse([cx - hr, cy - 70, cx + hr, cy + 14],
              fill=color + (255,))
    # Topknot
    d.ellipse([cx - 18, cy - 100, cx + 18, cy - 70],
              fill=color + (255,))
    # Hair sweep
    d.polygon([(cx - hr, cy - 30), (cx - hr - 12, cy - 20),
               (cx - hr - 4, cy - 4), (cx - hr + 6, cy - 14)],
              fill=color + (255,))

    # Sword — long diagonal blade raised behind
    blade = [
        (cx + 40, cy + 30),
        (cx + 230, cy - 220),
        (cx + 245, cy - 215),
        (cx + 55, cy + 45),
    ]
    d.polygon(blade, fill=color + (255,))
    # Hilt
    d.polygon([(cx + 30, cy + 50), (cx + 50, cy + 30),
               (cx + 70, cy + 50), (cx + 50, cy + 70)],
              fill=color + (255,))
    # Tsuba (guard)
    d.rectangle([cx + 30, cy + 36, cx + 70, cy + 44],
                fill=color + (255,))

    # Sash
    d.rectangle([cx - 95, cy + 100, cx + 95, cy + 122],
                fill=color + (220,))

    img.alpha_composite(overlay)


def _dragon_silhouette(img: Image.Image, cx: int, cy: int,
                       color: tuple) -> None:
    """Serpentine eastern dragon silhouette curling diagonally."""
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(overlay)

    # Snake-body S-curve made from overlapping ellipses
    body_pts = []
    for t in range(0, 100):
        u = t / 99
        # S-curve trajectory
        x = cx + math.sin(u * math.pi * 2.2) * 180 - u * 60
        y = cy - 220 + u * 460
        body_pts.append((x, y, u))

    # Body — thick to thin
    for x, y, u in body_pts:
        r = int(34 * (1 - u * 0.5))
        d.ellipse([x - r, y - r, x + r, y + r], fill=color + (255,))

    # Head — at the start (top)
    hx, hy, _ = body_pts[0]
    d.polygon([(hx - 40, hy - 40), (hx + 50, hy - 20),
               (hx + 60, hy + 10), (hx + 20, hy + 30),
               (hx - 30, hy + 15)], fill=color + (255,))
    # Horns
    d.polygon([(hx - 5, hy - 35), (hx + 5, hy - 70), (hx + 20, hy - 30)],
              fill=color + (255,))
    d.polygon([(hx + 20, hy - 30), (hx + 40, hy - 65), (hx + 50, hy - 25)],
              fill=color + (255,))

    # Whiskers
    d.line([(hx - 20, hy + 15), (hx - 100, hy + 60)],
           fill=color + (255,), width=4)
    d.line([(hx - 10, hy + 25), (hx - 90, hy + 90)],
           fill=color + (255,), width=4)

    # Spines along the body
    for i, (x, y, u) in enumerate(body_pts[::6]):
        if i == 0:
            continue
        r = int(28 * (1 - u * 0.5))
        sx = x + (r + 14) * (1 if (i % 2) else -1)
        sy = y - 8
        d.polygon([(x, y - 4), (sx, sy - 16), (sx + 4, sy + 4)],
                  fill=color + (240,))

    # Wing — small bat-like silhouette mid-body
    mx, my, _ = body_pts[40]
    d.polygon([(mx, my - 40), (mx + 110, my - 100),
               (mx + 90, my - 40), (mx + 120, my - 20),
               (mx + 80, my - 10)], fill=color + (255,))

    # Tail flourish
    tx, ty, _ = body_pts[-1]
    d.polygon([(tx, ty - 6), (tx - 30, ty + 30),
               (tx + 10, ty + 14), (tx + 30, ty + 28)],
              fill=color + (255,))

    img.alpha_composite(overlay)


def _knight_silhouette(img: Image.Image, cx: int, cy: int,
                       color: tuple, scale: float = 1.0) -> None:
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(overlay)
    s = scale
    # Body
    d.polygon([
        (cx - 30 * s, cy + 80 * s), (cx - 24 * s, cy - 10 * s),
        (cx - 40 * s, cy - 30 * s), (cx - 10 * s, cy - 40 * s),
        (cx + 10 * s, cy - 40 * s), (cx + 40 * s, cy - 30 * s),
        (cx + 24 * s, cy - 10 * s), (cx + 30 * s, cy + 80 * s),
    ], fill=color + (255,))
    # Helmet — pointed
    d.polygon([
        (cx - 18 * s, cy - 45 * s), (cx, cy - 90 * s),
        (cx + 18 * s, cy - 45 * s),
    ], fill=color + (255,))
    # Sword raised
    d.polygon([
        (cx + 30 * s, cy - 20 * s), (cx + 90 * s, cy - 140 * s),
        (cx + 100 * s, cy - 138 * s), (cx + 40 * s, cy - 18 * s),
    ], fill=color + (255,))
    d.rectangle([cx + 20 * s, cy - 14 * s, cx + 50 * s, cy - 6 * s],
                fill=color + (255,))
    img.alpha_composite(overlay)


def _profile_head(img: Image.Image, cx: int, cy: int, size: int,
                  facing: str, color: tuple, hair: str = "short") -> None:
    """Anime profile silhouette. facing='right' or 'left'."""
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(overlay)
    flip = 1 if facing == "right" else -1

    # Body / shoulders cone
    body = [
        (cx - 90, cy + size + 80),
        (cx - 50, cy + size + 20),
        (cx - 20, cy + int(size * 0.6)),
        (cx + 20, cy + int(size * 0.6)),
        (cx + 50, cy + size + 20),
        (cx + 90, cy + size + 80),
    ]
    d.polygon(body, fill=color + (255,))

    # Head (oval)
    hw, hh = int(size * 0.75), int(size * 0.95)
    d.ellipse([cx - hw, cy - hh, cx + hw, cy + hh], fill=color + (255,))

    # Anime-profile bump — small nose protrusion on the facing side
    nose_x = cx + flip * hw
    d.polygon([(nose_x, cy - 10), (nose_x + flip * 18, cy - 4),
               (nose_x, cy + 10)], fill=color + (255,))

    # Hair — varies by style
    if hair == "long":
        # Long flowing hair behind head and over shoulder
        d.polygon([
            (cx - flip * hw - flip * 10, cy - hh + 10),
            (cx - flip * hw - flip * 50, cy + 30),
            (cx - flip * hw - flip * 80, cy + size + 30),
            (cx - flip * 30, cy + size + 60),
            (cx - flip * 30, cy + 20),
        ], fill=color + (255,))
        # Top spikes
        d.polygon([
            (cx - hw + 10, cy - hh),
            (cx, cy - hh - 30),
            (cx + hw // 2, cy - hh + 10),
        ], fill=color + (255,))
        # Front bang
        d.polygon([
            (cx + flip * hw - flip * 20, cy - hh + 30),
            (cx + flip * hw - flip * 14, cy + 14),
            (cx + flip * 10, cy + 8),
        ], fill=color + (255,))
    elif hair == "spiky":
        # Spiky shounen hair
        for i, off_x in enumerate([-40, -20, 0, 20, 40]):
            spike_h = 60 + (i % 2) * 20
            d.polygon([
                (cx + off_x - 14, cy - hh + 10),
                (cx + off_x, cy - hh - spike_h),
                (cx + off_x + 14, cy - hh + 10),
            ], fill=color + (255,))
        # Sideburn
        d.polygon([
            (cx - flip * hw + flip * 4, cy - hh + 30),
            (cx - flip * hw - flip * 14, cy + 30),
            (cx - flip * hw + flip * 10, cy + 24),
        ], fill=color + (255,))
    else:  # short
        d.polygon([
            (cx - hw - 6, cy - hh + 20),
            (cx, cy - hh - 18),
            (cx + hw + 6, cy - hh + 20),
            (cx + hw - 4, cy - hh + 50),
            (cx, cy - hh + 26),
            (cx - hw + 4, cy - hh + 50),
        ], fill=color + (255,))

    img.alpha_composite(overlay)


def _wand(img: Image.Image, cx: int, cy: int, color: tuple,
          tip: tuple) -> None:
    """Magical-girl staff with a star at the top."""
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(overlay)
    # Shaft
    d.line([(cx, cy), (cx + 30, cy + 220)], fill=color + (255,), width=8)
    # Star tip
    r = 36
    pts = []
    for i in range(10):
        ang = math.radians(-90 + i * 36)
        rr = r if i % 2 == 0 else r * 0.45
        pts.append((cx + math.cos(ang) * rr, cy + math.sin(ang) * rr))
    d.polygon(pts, fill=tip + (255,), outline=color + (255,))
    img.alpha_composite(overlay)


def _coffee_cup(img: Image.Image, cx: int, cy: int, color: tuple,
                rim: tuple) -> None:
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(overlay)
    # Cup body — trapezoid
    d.polygon([
        (cx - 110, cy - 70), (cx + 110, cy - 70),
        (cx + 90, cy + 110), (cx - 90, cy + 110),
    ], fill=color + (255,))
    # Rim ellipse on top
    d.ellipse([cx - 112, cy - 90, cx + 112, cy - 50], fill=rim + (255,))
    d.ellipse([cx - 90, cy - 80, cx + 90, cy - 60], fill=color + (255,))
    # Handle
    d.ellipse([cx + 90, cy - 30, cx + 170, cy + 70],
              outline=color + (255,), width=18)
    # Saucer
    d.ellipse([cx - 150, cy + 100, cx + 150, cy + 140], fill=color + (255,))
    img.alpha_composite(overlay)


def _steam_curls(img: Image.Image, cx: int, cy: int, color: tuple,
                 alpha: int = 160) -> None:
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(overlay)
    for col_i, ox in enumerate((-50, 0, 50)):
        prev = (cx + ox, cy)
        for y in range(cy, cy - 280, -8):
            t = (cy - y) / 280
            x = cx + ox + math.sin(y * 0.05 + col_i) * 30 * t
            r = int(18 + 22 * t)
            a = int(alpha * (1 - t * 0.6))
            d.ellipse([x - r, y - r, x + r, y + r], fill=color + (a,))
            prev = (x, y)
    img.alpha_composite(overlay)


def _starburst_ring(img: Image.Image, cx: int, cy: int, *,
                    inner: int, outer: int, points: int,
                    color: tuple, alpha: int = 220) -> None:
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(overlay)
    pts = []
    for i in range(points * 2):
        ang = math.radians(i * (360 / (points * 2)) - 90)
        r = outer if i % 2 == 0 else inner
        pts.append((cx + math.cos(ang) * r, cy + math.sin(ang) * r))
    d.polygon(pts, fill=color + (alpha,))
    img.alpha_composite(overlay)


def _sparkle(img: Image.Image, cx: int, cy: int, r: int,
             color: tuple, alpha: int = 220) -> None:
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(overlay)
    # 4-point star + small cross
    d.polygon([
        (cx, cy - r), (cx + r * 0.25, cy - r * 0.25),
        (cx + r, cy), (cx + r * 0.25, cy + r * 0.25),
        (cx, cy + r), (cx - r * 0.25, cy + r * 0.25),
        (cx - r, cy), (cx - r * 0.25, cy - r * 0.25),
    ], fill=color + (alpha,))
    img.alpha_composite(overlay)


def _scanlines(img: Image.Image, color: tuple, alpha: int = 30,
               step: int = 3) -> None:
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(overlay)
    for y in range(0, img.size[1], step):
        d.line([(0, y), (img.size[0], y)], fill=color + (alpha,), width=1)
    img.alpha_composite(overlay)


def _diagonal_band(img: Image.Image, y0: int, y1: int, color: tuple,
                   alpha: int = 220, skew: int = 30) -> None:
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(overlay)
    d.polygon([
        (-20, y0 + skew), (img.size[0] + 20, y0 - skew),
        (img.size[0] + 20, y1 - skew), (-20, y1 + skew),
    ], fill=color + (alpha,))
    img.alpha_composite(overlay)


def _vignette(img: Image.Image, strength: int = 90) -> None:
    """Soft dark vignette around the edges to focus attention."""
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(overlay)
    w, h = img.size
    for i in range(40):
        a = int(strength * (i / 40) ** 2)
        d.rectangle([i, i, w - i, h - i],
                    outline=(0, 0, 0, a), width=1)
    img.alpha_composite(overlay)


# ============================================================ composers

def _compose_starlight(img: Image.Image, comic: dict, p: dict) -> None:
    """Magical-girl cover: big sparkly eye, kira-kira kanji, sparkles."""
    # Soft pink halftone over the top half
    _halftone(img, color=p["accent"], alpha=70, step=12, dot=4,
              region=(0, 0, COVER_W, int(COVER_H * 0.7)))

    # Big diagonal kira-kira kanji
    _kanji_decoration(img, comic["kanji_motif"] * 2, font_size=180,
                      color=p["shape"], alpha=80, x=-40, y=20,
                      rotate=-12)
    _kanji_decoration(img, comic["kanji_motif"], font_size=120,
                      color=(255, 255, 255), alpha=140, x=380, y=320,
                      rotate=12)

    # Light starburst ring behind the eye
    _starburst_ring(img, COVER_W // 2, 240,
                    inner=85, outer=170, points=12,
                    color=(255, 255, 255), alpha=140)
    _starburst_ring(img, COVER_W // 2, 240,
                    inner=50, outer=130, points=8,
                    color=p["accent"], alpha=140)

    # Big anime eye centered
    _anime_eye(img, COVER_W // 2, 250, size=90,
               iris=(120, 70, 200),
               liner=(60, 25, 90))

    # Sparkles around
    rng = random.Random(42)
    for _ in range(28):
        sx = rng.randint(20, COVER_W - 20)
        sy = rng.randint(40, int(COVER_H * 0.55))
        if abs(sx - COVER_W // 2) < 110 and abs(sy - 250) < 110:
            continue  # don't sparkle inside the eye
        r = rng.choice((6, 8, 10, 14, 18, 22))
        c = rng.choice([p["shape"], p["accent"], (255, 220, 240)])
        _sparkle(img, sx, sy, r, c, alpha=210)
        # Small companion dot
        if rng.random() < 0.4:
            ImageDraw.Draw(img, "RGBA").ellipse(
                [sx + r + 6, sy + 2, sx + r + 10, sy + 6],
                fill=c + (180,))


def _compose_phantom(img: Image.Image, comic: dict, p: dict) -> None:
    """Samurai action: speed lines, big slash kanji, blood splatter."""
    # Speed lines radiating from upper-right (where blade is raised)
    _speedlines(img, cx=520, cy=140, count=110, length=720,
                inner=80, color=p["shape"], alpha=180, width=3)

    # Giant 斬 kanji bg
    _kanji_decoration(img, comic["kanji_motif"], font_size=460,
                      color=p["deep"], alpha=200, x=80, y=70,
                      outline=p["shape"], outline_w=3)
    _kanji_decoration(img, comic["kanji_motif"], font_size=460,
                      color=p["shape"], alpha=60, x=70, y=60)

    # Halftone dots in lower half
    _halftone(img, color=p["shape"], alpha=70, step=14, dot=4,
              region=(0, int(COVER_H * 0.4), COVER_W, int(COVER_H * 0.78)))

    # Samurai silhouette
    _samurai_silhouette(img, cx=COVER_W // 2 - 30, cy=COVER_H // 2 - 30,
                        color=p["deep"])

    # Blood splatter overlay
    _ink_splatter(img, color=p["accent"], count=70,
                  alpha_range=(120, 200),
                  region=(0, 0, COVER_W, int(COVER_H * 0.65)))

    # Diagonal red slash band across the upper third
    _diagonal_band(img, y0=120, y1=160, color=p["accent"],
                   alpha=200, skew=60)
    _diagonal_band(img, y0=175, y1=185, color=p["shape"],
                   alpha=200, skew=60)


def _compose_neon(img: Image.Image, comic: dict, p: dict) -> None:
    """Cyberpunk romance: front-facing anime girl with visor + skyline."""
    # Skyline silhouette in the back
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(overlay)
    ground = int(COVER_H * 0.6)
    rng = random.Random(91)
    x = 0
    while x < COVER_W:
        bw = rng.randint(28, 70)
        bh = rng.randint(100, 240)
        d.rectangle([x, ground - bh, x + bw, ground],
                    fill=p["deep"] + (255,))
        for wy in range(ground - bh + 12, ground - 10, 16):
            for wx in range(x + 6, x + bw - 6, 12):
                if rng.random() < 0.5:
                    c = rng.choice([p["shape"], p["accent"]])
                    d.rectangle([wx, wy, wx + 3, wy + 5], fill=c + (220,))
        x += bw + rng.randint(2, 6)
    img.alpha_composite(overlay)

    # Vertical "東京" neon sign on the left as if it's a building sign
    _kanji_decoration(img, "東", font_size=110,
                      color=p["shape"], alpha=220, x=20, y=70,
                      outline=(255, 255, 255), outline_w=2)
    _kanji_decoration(img, "京", font_size=110,
                      color=p["shape"], alpha=220, x=20, y=170,
                      outline=(255, 255, 255), outline_w=2)

    # "ハート" katakana running vertically on the right
    _kanji_decoration(img, "ハ", font_size=72,
                      color=p["accent"], alpha=220, x=510, y=70)
    _kanji_decoration(img, "ー", font_size=72,
                      color=p["accent"], alpha=220, x=510, y=140)
    _kanji_decoration(img, "ト", font_size=72,
                      color=p["accent"], alpha=220, x=510, y=210)

    # Foreground anime girl bust — front-facing
    _anime_girl_bust(img, cx=COVER_W // 2, cy=int(COVER_H * 0.48),
                     p=p, scale=1.0)

    # Soft neon glow halo behind the head
    glow = Image.new("RGBA", img.size, (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    gx, gy = COVER_W // 2, int(COVER_H * 0.32)
    for i, a in [(280, 30), (220, 50), (160, 80)]:
        gd.ellipse([gx - i, gy - i, gx + i, gy + i],
                   fill=p["accent"] + (a,))
    glow = glow.filter(ImageFilter.GaussianBlur(radius=20))
    # Composite UNDER the rest by re-stacking
    new = Image.new("RGBA", img.size, (0, 0, 0, 0))
    new.alpha_composite(glow)
    new.alpha_composite(img)
    img.paste(new, (0, 0))

    # Scanlines on top for CRT feel
    _scanlines(img, color=p["shape"], alpha=24, step=3)


def _anime_girl_bust(img: Image.Image, cx: int, cy: int, p: dict,
                     scale: float = 1.0) -> None:
    """Front-facing anime girl bust with long hair, visor, big eyes.

    Draws head + hair + cyberpunk visor band (the "anime visor" trope
    sells the cyberpunk read more strongly than free-floating eyes).
    """
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(overlay)
    s = scale

    # Long flowing hair — twin tails flaring outward + back curtain
    hair_color = p["shape"]      # cyan
    hair_accent = p["accent"]    # magenta highlight

    # Back hair (wide curtain behind shoulders)
    d.polygon([
        (cx - 180 * s, cy + 220 * s),
        (cx - 230 * s, cy + 50 * s),
        (cx - 200 * s, cy - 60 * s),
        (cx - 130 * s, cy - 100 * s),
        (cx + 130 * s, cy - 100 * s),
        (cx + 200 * s, cy - 60 * s),
        (cx + 230 * s, cy + 50 * s),
        (cx + 180 * s, cy + 220 * s),
    ], fill=hair_color + (255,))

    # Hair streaks (magenta accents)
    d.polygon([
        (cx - 220 * s, cy + 30 * s),
        (cx - 200 * s, cy - 50 * s),
        (cx - 190 * s, cy + 60 * s),
        (cx - 210 * s, cy + 180 * s),
    ], fill=hair_accent + (180,))
    d.polygon([
        (cx + 210 * s, cy + 30 * s),
        (cx + 200 * s, cy - 50 * s),
        (cx + 190 * s, cy + 60 * s),
        (cx + 215 * s, cy + 180 * s),
    ], fill=hair_accent + (180,))

    # Body / collar (jacket suggestion)
    d.polygon([
        (cx - 120 * s, cy + 240 * s),
        (cx - 85 * s, cy + 130 * s),
        (cx - 40 * s, cy + 100 * s),
        (cx + 40 * s, cy + 100 * s),
        (cx + 85 * s, cy + 130 * s),
        (cx + 120 * s, cy + 240 * s),
    ], fill=(p["deep"][0], p["deep"][1], p["deep"][2], 255))
    # Collar V
    d.polygon([
        (cx - 40 * s, cy + 100 * s),
        (cx, cy + 150 * s),
        (cx + 40 * s, cy + 100 * s),
    ], fill=hair_accent + (240,))

    # Face — skin oval (light cream/peach, to read as a face)
    face_color = (255, 220, 210)
    fw, fh = int(95 * s), int(115 * s)
    d.ellipse([cx - fw, cy - fh, cx + fw, cy + fh],
              fill=face_color + (255,))

    # Front bang — sweeping fringe across the forehead
    d.polygon([
        (cx - fw, cy - fh + 10),
        (cx - fw - 15, cy + 10),
        (cx - 30 * s, cy - 20 * s),
        (cx + 20 * s, cy - 40 * s),
        (cx + 60 * s, cy - 30 * s),
        (cx + fw + 10, cy - fh + 30),
        (cx + fw - 8, cy - fh - 18),
        (cx, cy - fh - 30),
        (cx - fw + 8, cy - fh - 18),
    ], fill=hair_color + (255,))

    # Cyberpunk visor — dark rectangular band across the eye line
    vy = cy - int(30 * s)
    visor_h = int(34 * s)
    d.rounded_rectangle(
        [cx - fw + 2, vy - visor_h // 2,
         cx + fw - 2, vy + visor_h // 2],
        radius=8, fill=p["deep"] + (240,),
    )
    # Visor inner glow (two glowing horizontal lines = "eyes")
    d.rectangle(
        [cx - fw + 12, vy - 6, cx - 12, vy - 2],
        fill=p["shape"] + (255,),
    )
    d.rectangle(
        [cx + 12, vy - 6, cx + fw - 12, vy - 2],
        fill=p["shape"] + (255,),
    )
    # Visor reflection accent
    d.line([(cx - fw + 14, vy - 12), (cx - fw + 38, vy - 12)],
           fill=(255, 255, 255, 200), width=2)

    # Small mouth dot
    d.polygon([
        (cx - 6, cy + 36 * s), (cx + 6, cy + 36 * s),
        (cx, cy + 42 * s),
    ], fill=p["accent"] + (200,))

    # Side bangs flanking the visor (the iconic anime "framing locks")
    d.polygon([
        (cx - fw - 5, cy - fh + 30),
        (cx - fw - 20, cy + 70 * s),
        (cx - fw + 10, cy + 50 * s),
        (cx - fw + 8, cy - fh + 50),
    ], fill=hair_color + (255,))
    d.polygon([
        (cx + fw + 5, cy - fh + 30),
        (cx + fw + 20, cy + 70 * s),
        (cx + fw - 10, cy + 50 * s),
        (cx + fw - 8, cy - fh + 50),
    ], fill=hair_color + (255,))

    img.alpha_composite(overlay)


def _compose_dragon(img: Image.Image, comic: dict, p: dict) -> None:
    """Epic fantasy: huge dragon kanji, dragon silhouette, knight."""
    # Halftone gold dots
    _halftone(img, color=p["shape"], alpha=70, step=16, dot=5,
              region=(0, 0, COVER_W, int(COVER_H * 0.78)))

    # Enormous 龍 kanji
    _kanji_decoration(img, comic["kanji_motif"], font_size=540,
                      color=p["deep"], alpha=220, x=40, y=10,
                      outline=p["accent"], outline_w=4)
    _kanji_decoration(img, comic["kanji_motif"], font_size=540,
                      color=p["shape"], alpha=70, x=32, y=4)

    # Dragon silhouette curling down
    _dragon_silhouette(img, cx=COVER_W // 2, cy=COVER_H // 2 - 40,
                       color=p["deep"])

    # Knight silhouette at the bottom
    _knight_silhouette(img, cx=COVER_W // 2, cy=int(COVER_H * 0.56),
                       color=p["deep"], scale=0.9)

    # Ornate gold corner flourishes
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(overlay)
    cs = 90
    for cx, cy, sx, sy in [
        (0, 0, 1, 1),
        (COVER_W, 0, -1, 1),
        (0, COVER_H, 1, -1),
        (COVER_W, COVER_H, -1, -1),
    ]:
        d.polygon([
            (cx, cy),
            (cx + sx * cs, cy),
            (cx + sx * (cs - 20), cy + sy * 8),
            (cx + sx * 8, cy + sy * (cs - 20)),
            (cx, cy + sy * cs),
        ], fill=p["shape"] + (200,))
    img.alpha_composite(overlay)


def _compose_coffee(img: Image.Image, comic: dict, p: dict) -> None:
    """Slice of life: coffee cup whose steam forms a heart, soft halftone."""
    _halftone(img, color=p["deep"], alpha=40, step=18, dot=3,
              region=(0, 0, COVER_W, int(COVER_H * 0.72)))

    # Big translucent 恋 kanji as background watermark
    _kanji_decoration(img, comic["kanji_motif"], font_size=480,
                      color=p["accent"], alpha=80, x=60, y=10)

    # Window-pane style frame (cafe window vibe)
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(overlay)
    d.line([(60, 50), (60, 520)], fill=p["deep"] + (90,), width=3)
    d.line([(COVER_W - 60, 50), (COVER_W - 60, 520)],
           fill=p["deep"] + (90,), width=3)
    img.alpha_composite(overlay)

    # Steam — three streams that swirl up and converge into a heart
    _heart_steam(img, cx=COVER_W // 2, cy=int(COVER_H * 0.48),
                 color=p["shape"], heart_color=p["accent"])

    # Coffee cup, larger, centered low
    _coffee_cup(img, cx=COVER_W // 2, cy=int(COVER_H * 0.58),
                color=p["deep"], rim=p["accent"])

    # Floating hearts of varying sizes
    rng = random.Random(7)
    for _ in range(10):
        sx = rng.randint(60, COVER_W - 60)
        sy = rng.randint(60, int(COVER_H * 0.55))
        if abs(sx - COVER_W // 2) < 90 and abs(sy - int(COVER_H * 0.4)) < 90:
            continue  # avoid the central heart-steam area
        r = rng.choice((8, 12, 16))
        col = rng.choice([p["accent"], p["deep"]]) + (180,)
        ol = Image.new("RGBA", img.size, (0, 0, 0, 0))
        od = ImageDraw.Draw(ol)
        od.ellipse([sx - r, sy - r, sx, sy], fill=col)
        od.ellipse([sx, sy - r, sx + r, sy], fill=col)
        od.polygon([(sx - r, sy - 2), (sx + r, sy - 2),
                    (sx, sy + r + 2)], fill=col)
        img.alpha_composite(ol)

    # Small "...?" speech bubble peek — slice-of-life staple
    bubble = Image.new("RGBA", img.size, (0, 0, 0, 0))
    bd = ImageDraw.Draw(bubble)
    bx, by = 90, 80
    bd.ellipse([bx, by, bx + 90, by + 60], fill=(255, 255, 255, 230))
    bd.polygon([(bx + 30, by + 55), (bx + 55, by + 78),
                (bx + 50, by + 55)], fill=(255, 255, 255, 230))
    f_bub = _font(FONT_JP, 32)
    bd.text((bx + 28, by + 8), "…?", font=f_bub, fill=p["deep"] + (255,))
    img.alpha_composite(bubble)


def _heart_steam(img: Image.Image, cx: int, cy: int,
                 color: tuple, heart_color: tuple) -> None:
    """Three steam streams converging upward into a heart shape."""
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(overlay)

    # Three rising columns of soft cloud puffs
    for col_i, ox in enumerate((-46, 0, 46)):
        for y in range(cy + 60, cy - 110, -8):
            t = (cy + 60 - y) / 170
            x = cx + ox + math.sin(y * 0.06 + col_i) * 24 * t
            r = int(20 + 12 * t)
            a = int(170 * (1 - t * 0.4))
            d.ellipse([x - r, y - r, x + r, y + r], fill=color + (a,))

    # Heart at the apex made of two circles + triangle
    hr = 60
    hy = cy - 140
    d.ellipse([cx - hr - 6, hy - hr, cx + 6, hy + 4],
              fill=heart_color + (240,))
    d.ellipse([cx - 6, hy - hr, cx + hr + 6, hy + 4],
              fill=heart_color + (240,))
    d.polygon([(cx - hr - 4, hy), (cx + hr + 4, hy),
               (cx, hy + hr + 20)],
              fill=heart_color + (240,))
    # Inner highlight on the heart
    d.ellipse([cx - hr + 8, hy - hr + 8, cx - hr + 26, hy - hr + 26],
              fill=(255, 255, 255, 220))

    img.alpha_composite(overlay)


COMPOSERS = {
    "starlight": _compose_starlight,
    "phantom":   _compose_phantom,
    "neon":      _compose_neon,
    "dragon":    _compose_dragon,
    "coffee":    _compose_coffee,
}


# ============================================================ title block

def _draw_title_block(img: Image.Image, comic: dict, p: dict) -> None:
    """Bottom title card — magazine-style logo treatment."""
    d = ImageDraw.Draw(img, "RGBA")

    # Genre tag — top-right pill with mixed CJK + EN
    tag = comic["genre_tag"]
    f_tag = _font(FONT_JP, 18)
    bbox = d.textbbox((0, 0), tag, font=f_tag)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    pad_x, pad_y = 14, 8
    tx = COVER_W - tw - pad_x * 2 - 20
    ty = 22
    d.rounded_rectangle(
        [tx, ty, tx + tw + pad_x * 2, ty + th + pad_y * 2 + 4],
        radius=18, fill=p["tag_bg"] + (255,),
    )
    d.text((tx + pad_x, ty + pad_y - 2), tag,
           font=f_tag, fill=p["tag_ink"])

    # Vol number — top-left
    f_vol = _font(FONT_JP, 17)
    d.text((24, 26), comic["vol_number"],
           font=f_vol, fill=p["ink"] + (220,))

    # Title card — bottom 36%
    card_top = int(COVER_H * 0.66)
    card_layer = Image.new("RGBA", (COVER_W, COVER_H - card_top),
                           p["card"])
    img.alpha_composite(card_layer, (0, card_top))

    # Accent bar across the top of the card
    d.rectangle([0, card_top, COVER_W, card_top + 5],
                fill=p["accent"] + (255,))
    d.rectangle([0, card_top + 7, COVER_W, card_top + 9],
                fill=p["accent"] + (180,))

    # Japanese subtitle on top of the English title
    f_jp = _font(FONT_JP, 22)
    d.text((28, card_top + 18), comic["title_jp"],
           font=f_jp, fill=p["card_ink"] + (220,))

    # English title — auto-fit, with manga-style double layer (shadow + fill)
    title = comic["title"]
    f_title = None
    for size in (58, 52, 46, 42):
        f = _font(FONT_BOLD, size, index=1)
        bbox = d.textbbox((0, 0), title, font=f)
        if bbox[2] - bbox[0] <= COVER_W - 56:
            f_title = f
            break
    if f_title is None:
        f_title = _font(FONT_BOLD, 38, index=1)
    words = title.split()
    lines = [title]
    if d.textbbox((0, 0), title, font=f_title)[2] > COVER_W - 56 \
            and len(words) > 1:
        mid = len(words) // 2
        lines = [" ".join(words[:mid]), " ".join(words[mid:])]

    ty = card_top + 50
    shadow = (p["accent"][0], p["accent"][1], p["accent"][2], 140)
    for line in lines:
        d.text((28 + 3, ty + 3), line, font=f_title, fill=shadow)
        d.text((28, ty), line, font=f_title, fill=p["card_ink"] + (255,))
        ty += int(f_title.size * 1.04)
    ty += 6

    # Subtitle / volume
    f_sub = _font(FONT_REGULAR, 18, index=2)
    d.text((28, ty), comic["subtitle"],
           font=f_sub, fill=p["card_ink"] + (255,))
    ty += 26

    # Artist credit
    f_artist = _font(FONT_REGULAR, 13, index=0)
    artist_str = "STORY · ART  " + "  ·  ".join(
        a.upper() for a in comic["artists"]
    )
    d.text((28, ty), artist_str,
           font=f_artist, fill=p["card_ink"] + (210,))


# ============================================================ cover

def _draw_cover(comic: dict) -> Image.Image:
    p = PALETTES[comic["palette"]]
    img = _gradient(p["bg_top"], p["bg_bottom"],
                    COVER_W, COVER_H).convert("RGBA")
    COMPOSERS[comic["compose"]](img, comic, p)
    _vignette(img, strength=80)
    _draw_title_block(img, comic, p)
    return img.convert("RGB")


# ============================================================ pages

PAGE_W, PAGE_H = 1080, 1536


# Per-comic dialogue / SFX banks for chapter pages.
SCENES = {
    "starlight_academy": {
        "dialogue": [
            "Is this... really happening?",
            "The starlight is calling me!",
            "I won't lose. Not this time.",
            "Awaken — my true form!",
            "I feel everyone with me!",
            "Together... we can do this!",
        ],
        "sfx": ["キラッ", "ピカッ", "ドキッ", "シャイン", "ピカ", "キラキラ"],
    },
    "phantom_blade_chronicles": {
        "dialogue": [
            "You should not have come here.",
            "My blade has tasted ten thousand.",
            "This ends with one of us.",
            "Honor demands it.",
            "Speak your last name, traitor.",
            "Steel does not forget.",
        ],
        "sfx": ["ザン", "ドン", "シャキン", "ブン", "ザッ", "ガキィン"],
    },
    "neon_heart_tokyo": {
        "dialogue": [
            "The system thinks I'm broken.",
            "Tokyo never sleeps.",
            "Are you sure you want this?",
            "I'll find you. No matter where.",
            "The signal won't last forever.",
            "We're not supposed to feel this.",
        ],
        "sfx": ["ピッ", "ガガッ", "カチャ", "ザザッ", "ピピッ", "ブブッ"],
    },
    "the_last_dragonslayer": {
        "dialogue": [
            "The kingdom is gone. Only I remain.",
            "You face the last of my kind, mortal.",
            "By steel and by oath.",
            "This ends today.",
            "Run, while you still can.",
            "The blade remembers.",
        ],
        "sfx": ["ガオオ", "ドゴオ", "キィン", "ゴオ", "ザッ", "ドオン"],
    },
    "coffee_shop_confessions": {
        "dialogue": [
            "Um... the usual, please.",
            "He always orders the same thing...",
            "Today's the day. I'll tell him.",
            "Wait — is that...?",
            "M-my heart won't stop!",
            "I-it's not what you think!",
        ],
        "sfx": ["カラン", "ドキドキ", "コトッ", "ハッ", "ザワ", "シーン"],
    },
}


# ------------------------------------------------------------ panel atoms

def _panel_rect(img: Image.Image, x: int, y: int, w: int, h: int, *,
                bg_top: tuple, bg_bottom: tuple,
                border: int = 6) -> tuple:
    """Panel with gradient bg + thick black border. Returns inner bbox."""
    grad = _gradient(bg_top, bg_bottom, w, h).convert("RGBA")
    img.alpha_composite(grad, (x, y))
    d = ImageDraw.Draw(img, "RGBA")
    d.rectangle([x, y, x + w, y + h], outline=(0, 0, 0, 255), width=border)
    return (x + border, y + border, x + w - border, y + h - border)


def _text_width(d: ImageDraw.ImageDraw, text: str,
                font: ImageFont.FreeTypeFont) -> int:
    bbox = d.textbbox((0, 0), text, font=font)
    return bbox[2] - bbox[0]


def _speech_bubble(img: Image.Image, cx: int, cy: int, text: str, *,
                   max_w: int = 360, font_size: int = 32,
                   tail: str = "bottom-left",
                   color: tuple = (255, 255, 255),
                   ink: tuple = (20, 20, 20)) -> None:
    """Classic manga speech bubble — ellipse + tail + wrapped text."""
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(overlay)
    f = _font(FONT_BOLD, font_size, index=1)

    # Word-wrap
    words = text.split()
    lines, cur = [], ""
    for w in words:
        test = (cur + " " + w).strip()
        if _text_width(d, test, f) <= max_w - 60:
            cur = test
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    if not lines:
        lines = [text]

    line_h = int(font_size * 1.2)
    text_h = line_h * len(lines)
    text_w = max(_text_width(d, line, f) for line in lines)
    bw = int(max(text_w + 70, 180))
    bh = int(text_h + 50)
    x0 = cx - bw // 2
    y0 = cy - bh // 2

    d.ellipse([x0, y0, x0 + bw, y0 + bh],
              fill=color + (245,), outline=ink + (255,), width=5)

    # Tail
    if tail == "bottom-left":
        tp = [(x0 + bw * 0.18, y0 + bh - 6),
              (x0 + bw * 0.32, y0 + bh - 10),
              (x0 + bw * 0.08, y0 + bh + 44)]
    elif tail == "bottom-right":
        tp = [(x0 + bw * 0.68, y0 + bh - 10),
              (x0 + bw * 0.82, y0 + bh - 6),
              (x0 + bw * 0.92, y0 + bh + 44)]
    elif tail == "top-left":
        tp = [(x0 + bw * 0.18, y0 + 6),
              (x0 + bw * 0.32, y0 + 10),
              (x0 + bw * 0.08, y0 - 44)]
    elif tail == "top-right":
        tp = [(x0 + bw * 0.68, y0 + 10),
              (x0 + bw * 0.82, y0 + 6),
              (x0 + bw * 0.92, y0 - 44)]
    else:
        tp = None
    if tp:
        d.polygon(tp, fill=color + (245,), outline=ink + (255,))

    # Text
    ty = y0 + (bh - text_h) // 2
    for line in lines:
        tw = _text_width(d, line, f)
        d.text((cx - tw // 2, ty), line, font=f, fill=ink + (255,))
        ty += line_h

    img.alpha_composite(overlay)


def _sfx_text(img: Image.Image, cx: int, cy: int, text: str, *,
              font_size: int = 90, color: tuple = (255, 255, 255),
              outline: tuple = (0, 0, 0), outline_w: int = 5,
              rotate: float = -14.0) -> None:
    """Big manga sound-effect text — thick outline, rotated."""
    f = _font(FONT_JP, font_size)
    pad = font_size
    tmp = Image.new("RGBA",
                    (font_size * (len(text) + 1) + pad * 2,
                     font_size + pad * 2),
                    (0, 0, 0, 0))
    td = ImageDraw.Draw(tmp)
    for dx in range(-outline_w, outline_w + 1):
        for dy in range(-outline_w, outline_w + 1):
            if dx * dx + dy * dy <= outline_w * outline_w:
                td.text((pad + dx, pad + dy), text,
                        font=f, fill=outline + (255,))
    td.text((pad, pad), text, font=f, fill=color + (255,))
    if rotate:
        tmp = tmp.rotate(rotate, resample=Image.BICUBIC, expand=True)
    tw, th = tmp.size
    img.alpha_composite(tmp, (cx - tw // 2, cy - th // 2))


def _panel_halftone(img: Image.Image, color: tuple, alpha: int,
                    bounds: tuple, step: int = 18, dot: int = 5) -> None:
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(overlay)
    x0, y0, x1, y1 = bounds
    rng = random.Random(0xABBA)
    for y in range(y0, y1, step):
        off = (step // 2) if (y // step) % 2 else 0
        for x in range(x0 + off, x1, step):
            r = dot + rng.choice((-1, 0, 0, 1))
            d.ellipse([x - r, y - r, x + r, y + r],
                      fill=color + (alpha,))
    img.alpha_composite(overlay)


# ------------------------------------------------------------ scene drawers

def _scene_starlight(img, bounds, p, variant):
    x0, y0, x1, y1 = bounds
    cx, cy = (x0 + x1) // 2, (y0 + y1) // 2
    _panel_halftone(img, p["accent"], 90, bounds, step=18, dot=5)
    if variant % 4 == 0:
        _starburst_ring(img, cx, cy, inner=80, outer=200, points=12,
                        color=(255, 255, 255), alpha=140)
        _anime_eye(img, cx, cy, size=min(110, (y1 - y0) // 4),
                   iris=(120, 70, 200), liner=(60, 25, 90))
    elif variant % 4 == 1:
        rng = random.Random(31 + variant)
        for _ in range(40):
            sx = rng.randint(x0 + 30, x1 - 30)
            sy = rng.randint(y0 + 30, y1 - 30)
            r = rng.choice((10, 14, 20, 26, 32))
            col = rng.choice([p["shape"], p["accent"], (255, 230, 240)])
            _sparkle(img, sx, sy, r, col, alpha=220)
    elif variant % 4 == 2:
        _wand(img, cx - 20, cy - 100, p["deep"], p["accent"])
        rng = random.Random(7 + variant)
        for _ in range(20):
            sx = rng.randint(x0 + 30, x1 - 30)
            sy = rng.randint(y0 + 30, y1 - 30)
            r = rng.choice((8, 12, 16))
            _sparkle(img, sx, sy, r, p["shape"], alpha=200)
    else:
        _starburst_ring(img, cx, cy, inner=60, outer=180, points=16,
                        color=p["shape"], alpha=160)
        _kanji_decoration(img, "輝", font_size=min(220, (x1 - x0) // 2),
                          color=p["accent"], alpha=240,
                          x=cx - 100, y=cy - 120)


def _scene_phantom(img, bounds, p, variant):
    x0, y0, x1, y1 = bounds
    cx, cy = (x0 + x1) // 2, (y0 + y1) // 2
    _panel_halftone(img, p["shape"], 60, bounds, step=16, dot=4)
    if variant % 4 == 0:
        _samurai_silhouette(img, cx, cy + 30, p["deep"])
        _speedlines(img, cx + 100, cy - 100, count=70, length=400,
                    inner=80, color=p["shape"], alpha=160, width=3)
    elif variant % 4 == 1:
        _speedlines(img, cx, cy, count=140, length=600, inner=60,
                    color=p["shape"], alpha=200, width=4)
        _diagonal_band(img, y0=cy - 40, y1=cy + 20, color=p["accent"],
                       alpha=220, skew=80)
    elif variant % 4 == 2:
        _ink_splatter(img, p["accent"], count=160,
                      alpha_range=(160, 230), region=bounds)
    else:
        size = min(x1 - x0, y1 - y0)
        _kanji_decoration(img, "斬", font_size=int(size * 0.85),
                          color=p["deep"], alpha=230,
                          x=cx - size // 3, y=cy - size // 2,
                          outline=p["shape"], outline_w=3)


def _scene_neon(img, bounds, p, variant):
    x0, y0, x1, y1 = bounds
    cx, cy = (x0 + x1) // 2, (y0 + y1) // 2
    if variant % 4 == 0:
        scale = min((x1 - x0) / 560, (y1 - y0) / 640)
        _anime_girl_bust(img, cx, cy + int(40 * scale), p, scale=scale)
    elif variant % 4 == 1:
        overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
        d = ImageDraw.Draw(overlay)
        ground = y1 - 10
        rng = random.Random(91 + variant)
        x = x0
        while x < x1:
            bw = rng.randint(28, 70)
            bh = rng.randint(80, min(240, y1 - y0 - 20))
            d.rectangle([x, ground - bh, x + bw, ground],
                        fill=p["deep"] + (255,))
            for wy in range(ground - bh + 12, ground - 10, 14):
                for wx in range(x + 6, x + bw - 6, 10):
                    if rng.random() < 0.55:
                        c = rng.choice([p["shape"], p["accent"]])
                        d.rectangle([wx, wy, wx + 3, wy + 4],
                                    fill=c + (220,))
            x += bw + rng.randint(2, 6)
        img.alpha_composite(overlay)
        _scanlines(img, p["shape"], alpha=20, step=3)
    elif variant % 4 == 2:
        size = min(x1 - x0, y1 - y0)
        _kanji_decoration(img, "東京", font_size=int(size * 0.55),
                          color=p["shape"], alpha=220,
                          x=x0 + 20, y=cy - size // 3,
                          outline=(255, 255, 255), outline_w=3)
        _scanlines(img, p["accent"], alpha=24, step=4)
    else:
        _scanlines(img, p["shape"], alpha=50, step=3)
        overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
        gd = ImageDraw.Draw(overlay)
        gd.ellipse([cx - 220, cy - 220, cx + 220, cy + 220],
                   fill=p["accent"] + (110,))
        overlay = overlay.filter(ImageFilter.GaussianBlur(radius=30))
        img.alpha_composite(overlay)


def _scene_dragon(img, bounds, p, variant):
    x0, y0, x1, y1 = bounds
    cx, cy = (x0 + x1) // 2, (y0 + y1) // 2
    _panel_halftone(img, p["shape"], 70, bounds, step=18, dot=5)
    if variant % 4 == 0:
        _dragon_silhouette(img, cx, cy, p["deep"])
    elif variant % 4 == 1:
        _knight_silhouette(img, cx, cy + 30, p["deep"], scale=2.2)
        _speedlines(img, cx, cy - 100, count=80, length=400, inner=60,
                    color=p["shape"], alpha=170, width=3)
    elif variant % 4 == 2:
        size = min(x1 - x0, y1 - y0)
        _kanji_decoration(img, "龍", font_size=int(size * 0.9),
                          color=p["deep"], alpha=240,
                          x=cx - size // 3, y=cy - size // 2,
                          outline=p["accent"], outline_w=4)
    else:
        _ink_splatter(img, p["shape"], count=160,
                      alpha_range=(160, 230), region=bounds)


def _scene_coffee(img, bounds, p, variant):
    x0, y0, x1, y1 = bounds
    cx, cy = (x0 + x1) // 2, (y0 + y1) // 2
    _panel_halftone(img, p["deep"], 50, bounds, step=18, dot=4)
    if variant % 4 == 0:
        _coffee_cup(img, cx, cy + 30, p["deep"], p["accent"])
        _steam_curls(img, cx, cy - 60, p["shape"], alpha=180)
    elif variant % 4 == 1:
        rng = random.Random(7 + variant)
        for _ in range(16):
            sx = rng.randint(x0 + 40, x1 - 40)
            sy = rng.randint(y0 + 40, y1 - 40)
            r = rng.choice((14, 20, 28, 34))
            col = p["accent"] + (210,)
            ol = Image.new("RGBA", img.size, (0, 0, 0, 0))
            od = ImageDraw.Draw(ol)
            od.ellipse([sx - r, sy - r, sx, sy], fill=col)
            od.ellipse([sx, sy - r, sx + r, sy], fill=col)
            od.polygon([(sx - r, sy - 2), (sx + r, sy - 2),
                        (sx, sy + r + 2)], fill=col)
            img.alpha_composite(ol)
    elif variant % 4 == 2:
        # Cafe door silhouette + bell
        overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
        d = ImageDraw.Draw(overlay)
        dw, dh = min(220, (x1 - x0) // 2), min(420, y1 - y0 - 60)
        d.rectangle([cx - dw // 2, cy - dh // 2,
                     cx + dw // 2, cy + dh // 2],
                    fill=p["deep"] + (255,))
        d.rectangle([cx - dw // 2 + 24, cy - dh // 2 + 24,
                     cx + dw // 2 - 24, cy + dh // 2 - 100],
                    fill=p["shape"] + (180,))
        # Bell above the door
        bell_y = cy - dh // 2 - 40
        d.ellipse([cx - 20, bell_y - 20, cx + 20, bell_y + 20],
                  fill=p["accent"] + (255,))
        d.polygon([(cx - 6, bell_y + 16), (cx + 6, bell_y + 16),
                   (cx, bell_y + 30)], fill=p["accent"] + (255,))
        img.alpha_composite(overlay)
    else:
        size = min(x1 - x0, y1 - y0)
        _kanji_decoration(img, "恋", font_size=int(size * 0.85),
                          color=p["accent"], alpha=240,
                          x=cx - size // 3, y=cy - size // 2)


SCENE_DRAWERS = {
    "starlight": _scene_starlight,
    "phantom":   _scene_phantom,
    "neon":      _scene_neon,
    "dragon":    _scene_dragon,
    "coffee":    _scene_coffee,
}


# ------------------------------------------------------------ layouts

def _page_footer(img, comic, p, chap_n, page_n, total_pages):
    d = ImageDraw.Draw(img, "RGBA")
    fy = PAGE_H - 56
    d.line([(50, fy - 10), (PAGE_W - 50, fy - 10)],
           fill=p["deep"] + (200,), width=2)
    f_foot = _font(FONT_REGULAR, 22, index=0)
    f_jp = _font(FONT_JP, 22)
    d.text((50, fy - 2),
           f"CHAPTER {chap_n}  ·  PAGE {page_n}/{total_pages}",
           font=f_foot, fill=p["ink"] + (220,))
    tw = _text_width(d, comic["title_jp"], f_jp)
    d.text((PAGE_W - 50 - tw, fy - 2),
           comic["title_jp"], font=f_jp, fill=p["ink"] + (210,))


def _layout_splash(img, comic, p, chap_n, page_n, total_pages):
    """Page 1 — chapter title splash with a hero scene above the card."""
    _halftone(img, color=p["shape"], alpha=70, step=22, dot=6)
    _kanji_decoration(img, comic["kanji_motif"], font_size=620,
                      color=p["deep"], alpha=160,
                      x=PAGE_W // 2 - 290, y=PAGE_H // 2 - 380)

    drawer = SCENE_DRAWERS[comic["compose"]]
    drawer(img, (60, 80, PAGE_W - 60, int(PAGE_H * 0.46)), p, 0)

    # Title card
    card_w, card_h = int(PAGE_W * 0.78), int(PAGE_H * 0.32)
    cx0 = (PAGE_W - card_w) // 2
    cy0 = int(PAGE_H * 0.54)
    card = Image.new("RGBA", (card_w, card_h), p["card"])
    img.alpha_composite(card, (cx0, cy0))
    d = ImageDraw.Draw(img, "RGBA")
    d.rectangle([cx0, cy0, cx0 + card_w, cy0 + card_h],
                outline=p["card_ink"] + (255,), width=4)

    f_label = _font(FONT_REGULAR, 32, index=2)
    f_chap = _font(FONT_BOLD, 160, index=1)
    f_title = _font(FONT_BOLD, 48, index=1)
    f_jp = _font(FONT_JP, 30)
    f_page = _font(FONT_REGULAR, 22)

    d.text((cx0 + 48, cy0 + 36), "CHAPTER",
           font=f_label, fill=p["card_ink"] + (220,))
    d.text((cx0 + 48, cy0 + 80), str(chap_n),
           font=f_chap, fill=p["card_ink"] + (255,))
    d.text((cx0 + 48, cy0 + card_h - 180), comic["title_jp"],
           font=f_jp, fill=p["card_ink"] + (210,))
    d.text((cx0 + 48, cy0 + card_h - 142), comic["title"],
           font=f_title, fill=p["card_ink"] + (255,))
    d.text((cx0 + 48, cy0 + card_h - 60),
           f"Page {page_n} / {total_pages}",
           font=f_page, fill=p["card_ink"] + (200,))

    _page_footer(img, comic, p, chap_n, page_n, total_pages)


def _layout_4panel(img, comic, p, chap_n, page_n, total_pages):
    """Classic 2×2 manga grid — 2 panels with dialogue, 2 with SFX."""
    margin = 50
    gutter = 24
    cell_w = (PAGE_W - margin * 2 - gutter) // 2
    cell_h = (PAGE_H - margin * 2 - gutter - 80) // 2
    drawer = SCENE_DRAWERS[comic["compose"]]
    scenes = SCENES[comic["key"]]

    for i, (col, row) in enumerate([(0, 0), (1, 0), (0, 1), (1, 1)]):
        px = margin + col * (cell_w + gutter)
        py = margin + row * (cell_h + gutter)
        bg_top = p["bg_top"] if i % 2 == 0 else p["bg_bottom"]
        bg_bot = p["bg_bottom"] if i % 2 == 0 else p["bg_top"]
        inner = _panel_rect(img, px, py, cell_w, cell_h,
                            bg_top=bg_top, bg_bottom=bg_bot, border=6)
        drawer(img, inner, p, variant=i + chap_n + page_n)

        if i in (0, 3):
            tail = "bottom-left" if i == 0 else "top-right"
            line_idx = (chap_n + i + page_n) % len(scenes["dialogue"])
            bubble_y = py + 90 if i == 0 else py + cell_h - 90
            _speech_bubble(img, px + cell_w // 2, bubble_y,
                           scenes["dialogue"][line_idx],
                           max_w=cell_w - 80, font_size=28, tail=tail)
        else:
            sfx_idx = (chap_n * 3 + i + page_n) % len(scenes["sfx"])
            _sfx_text(img,
                      px + cell_w - 120 if i == 1 else px + 140,
                      py + cell_h - 100 if i == 1 else py + 100,
                      scenes["sfx"][sfx_idx],
                      font_size=84, color=p["shape"],
                      outline=p["deep"], outline_w=6,
                      rotate=-12 if i % 2 == 0 else 12)

    _page_footer(img, comic, p, chap_n, page_n, total_pages)


def _layout_2panel(img, comic, p, chap_n, page_n, total_pages):
    """Two wide horizontal panels — top action, bottom reaction."""
    margin = 50
    gutter = 24
    inner_w = PAGE_W - margin * 2
    panel_h = (PAGE_H - margin * 2 - gutter - 80) // 2
    drawer = SCENE_DRAWERS[comic["compose"]]
    scenes = SCENES[comic["key"]]

    inner = _panel_rect(img, margin, margin, inner_w, panel_h,
                        bg_top=p["bg_top"], bg_bottom=p["bg_bottom"],
                        border=8)
    drawer(img, inner, p, variant=1 + chap_n + page_n)
    sfx_idx = (chap_n + page_n) % len(scenes["sfx"])
    _sfx_text(img, margin + inner_w - 240, margin + 130,
              scenes["sfx"][sfx_idx],
              font_size=140, color=p["accent"],
              outline=p["deep"], outline_w=8, rotate=-12)

    py = margin + panel_h + gutter
    inner = _panel_rect(img, margin, py, inner_w, panel_h,
                        bg_top=p["bg_bottom"], bg_bottom=p["bg_top"],
                        border=8)
    drawer(img, inner, p, variant=3 + chap_n + page_n)
    line_idx = (chap_n + page_n + 1) % len(scenes["dialogue"])
    _speech_bubble(img, PAGE_W // 2 - 60, py + panel_h - 140,
                   scenes["dialogue"][line_idx],
                   max_w=620, font_size=36, tail="bottom-right")

    _page_footer(img, comic, p, chap_n, page_n, total_pages)


def _layout_hero(img, comic, p, chap_n, page_n, total_pages):
    """Single dramatic full-page panel with giant SFX + dialogue."""
    margin = 50
    inner_h = PAGE_H - margin * 2 - 80
    drawer = SCENE_DRAWERS[comic["compose"]]
    scenes = SCENES[comic["key"]]

    inner = _panel_rect(img, margin, margin, PAGE_W - margin * 2,
                        inner_h,
                        bg_top=p["bg_top"], bg_bottom=p["bg_bottom"],
                        border=10)
    drawer(img, inner, p, variant=(chap_n + page_n) % 4)
    drawer(img, inner, p, variant=2)  # overlay variant for density

    sfx_idx = (chap_n * 5 + page_n) % len(scenes["sfx"])
    _sfx_text(img, PAGE_W // 2, margin + 220,
              scenes["sfx"][sfx_idx],
              font_size=240, color=p["accent"],
              outline=p["deep"], outline_w=12, rotate=-8)

    line_idx = (chap_n + page_n + 3) % len(scenes["dialogue"])
    _speech_bubble(img, PAGE_W // 2, margin + inner_h - 180,
                   scenes["dialogue"][line_idx],
                   max_w=720, font_size=44, tail="bottom-left")

    _page_footer(img, comic, p, chap_n, page_n, total_pages)


LAYOUTS = [_layout_splash, _layout_4panel, _layout_2panel, _layout_hero]


def _draw_chapter_page(comic: dict, chap_n: int, page_n: int,
                       total_pages: int) -> bytes:
    """Render a real manga-style page: panels, scenes, dialogue, SFX."""
    p = PALETTES[comic["palette"]]
    img = _gradient(p["bg_top"], p["bg_bottom"],
                    PAGE_W, PAGE_H).convert("RGBA")

    layout = LAYOUTS[(page_n - 1) % len(LAYOUTS)]
    layout(img, comic, p, chap_n, page_n, total_pages)

    _vignette(img, strength=60)

    out = io.BytesIO()
    img.convert("RGB").save(out, format="JPEG", quality=82, optimize=True)
    return out.getvalue()


def _build_cbz(comic: dict, chap_n: int, dest: Path, pages: int = 4) -> None:
    with zipfile.ZipFile(dest, "w", compression=zipfile.ZIP_DEFLATED) as z:
        for i in range(1, pages + 1):
            img_bytes = _draw_chapter_page(comic, chap_n, i, pages)
            z.writestr(f"{i:03d}.jpg", img_bytes)


# ============================================================ library

def _now_iso(offset_days: float = 0) -> str:
    t = datetime.now(tz=timezone.utc) - timedelta(days=offset_days)
    return t.replace(microsecond=0).isoformat()


def _build_entry(comic: dict, folder_name: str,
                 download_path: Path) -> dict:
    chapters = {}
    for i in range(1, comic["chapter_count"] + 1):
        chapters[str(i)] = {
            "title": "",
            "downloaded_at":
                _now_iso(offset_days=(comic["chapter_count"] - i) * 0.5),
        }

    added_iso = _now_iso(offset_days=comic["chapter_count"] * 0.5 + 7)
    last_updated = _now_iso(
        offset_days=1 if comic["status"] == "ongoing" else 14
    )
    last_checked = _now_iso(offset_days=0.25)

    return {
        "source": comic["source"],
        "source_url": comic["source_url"],
        "manga_id": None,
        "hash_id": None,
        "manga_code": comic["key"],
        "title": comic["title"],
        "alt_titles": comic["alt_titles"],
        "poster_url": "",
        "is_nsfw": False,
        "artists": comic["artists"],
        "tags": comic["tags"],
        "output_format": "cbz",
        "download_path": str(download_path),
        "folder": folder_name,
        "added_at": added_iso,
        "last_updated_at": last_updated,
        "last_checked_at": last_checked,
        "status": comic["status"],
        "status_auto": comic["status"],
        "status_manual": False,
        "chapters": chapters,
        "alternative_sources": comic["alt_sources"],
        "origin": "screenshot_seed",
    }


# ============================================================ main

def main() -> None:
    OUT_DIR.mkdir(exist_ok=True)
    entries = []

    for comic in COMICS:
        folder = comic["title"]
        comic_dir = OUT_DIR / folder
        comic_dir.mkdir(parents=True, exist_ok=True)

        cover_path = comic_dir / "cover.jpg"
        print(f"  cover  → {cover_path.relative_to(PROJECT_ROOT)}")
        _draw_cover(comic).save(cover_path, format="JPEG",
                                quality=88, optimize=True)

        sample_chapters = min(3, comic["chapter_count"])
        for n in range(1, comic["chapter_count"] + 1):
            cbz = comic_dir / f"Chapter_{n}.cbz"
            if n <= sample_chapters:
                _build_cbz(comic, n, cbz, pages=4)
            else:
                with zipfile.ZipFile(cbz, "w") as z:
                    z.writestr(
                        "README.txt",
                        f"{comic['title']} — Chapter {n} (placeholder)\n",
                    )
        print(f"  built  → {comic['chapter_count']:>3} CBZ files for "
              f"{comic['title']}")

        entry = _build_entry(comic, folder, OUT_DIR)
        entry["poster_url"] = "file://" + str(cover_path)
        entries.append(entry)

    library = {"version": 1, "entries": entries}
    lib_path = OUT_DIR / "library.json"
    lib_path.write_text(json.dumps(library, indent=2, ensure_ascii=False))

    print()
    print(f"Wrote {lib_path.relative_to(PROJECT_ROOT)} "
          f"with {len(entries)} entries.")
    print()
    print("To use for screenshots:")
    print("    mv library.json library.json.real")
    print(f"    cp {lib_path.relative_to(PROJECT_ROOT)} library.json")
    print("    python gui/main.py")
    print()
    print("Restore your real library after taking screenshots:")
    print("    mv library.json.real library.json")


if __name__ == "__main__":
    main()
