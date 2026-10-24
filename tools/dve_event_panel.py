#!/usr/bin/env python3
# DvE - builds the picture of a news-style event.
#
# In the news window (EventWindow_News, interface/eventwindow.gui) the event
# picture is a "panel": the header bar with its label plus the 557x372
# picture, 581x436 in all, drawn at the top-left corner of the window.
# Every sprite used as "picture" by a news_event must be made this way.
#
#   python3 tools/dve_event_panel.py picture.png "HEADER TEXT" out.dds
#       --icon warn|globe   header icon (default: globe for WORLD NEWS, else warn)
#       --plain             the picture already has scanlines and corner
#                           marks (cut out of a mock-up): add nothing on top
#   python3 tools/dve_event_panel.py --empty "HEADER TEXT" out.png
#       a panel with the header and an empty screen: a template to paste
#       a picture on by hand (tools/panel_templates/)
#   python3 tools/dve_event_panel.py --background out.dds
#       the empty top of the window (581x490, GFX_DVE_event_news_top)
#   The output is a .dds, or a .png if the name ends in .png.
#
# Wide pictures (like the old 397x153 ones) are not cropped: they are shown
# whole over a blurred copy of themselves. Needs Pillow; fonts are macOS ones.
import math, os, struct, sys
from PIL import Image, ImageDraw, ImageFilter, ImageFont

S = 2                                   # drawn at 2x, scaled down
W, TOP_H, PANEL_H = 581, 490, 436
PIC = (12, 60, 557, 372)                # x, y, width, height of the picture
TITLE_Y = 440                           # title bar, down to TOP_H
C_DARK, C_MID, C_LINE, C_ACC, C_TEXT = (4, 22, 56), (22, 51, 103), (48, 91, 171), (101, 157, 242), (198, 220, 255)

def lerp(a, b, t): return tuple(int(round(a[i] + (b[i] - a[i]) * t)) for i in range(len(a)))
def rgba(c, a=1.0): return c + (int(round(255 * a)),)
def box(x0, y0, x1, y1): return [min(x0, x1), min(y0, y1), max(x0, x1) - 1, max(y0, y1) - 1]

class Blend:
    """ImageDraw that alpha-blends (plain ImageDraw replaces the pixels)"""
    def __init__(self, im): self.im = im
    def textlength(self, *a, **k): return ImageDraw.Draw(self.im).textlength(*a, **k)
    def __getattr__(self, name):
        def f(*a, **k):
            ov = Image.new("RGBA", self.im.size, (0, 0, 0, 0)); getattr(ImageDraw.Draw(ov), name)(*a, **k); self.im.alpha_composite(ov)
        return f

def vgrad(w, h, top, bot):
    im = Image.new("RGBA", (1, h)); px = im.load()
    for y in range(h): px[0, y] = rgba(lerp(top, bot, y / max(1, h - 1)))
    return im.resize((w, h), Image.NEAREST)

def hglow(w, h, stops):
    im = Image.new("RGBA", (w, 1)); px = im.load()
    for x in range(w):
        t = x / max(1, w - 1)
        for (p0, c0, a0), (p1, c1, a1) in zip(stops, stops[1:]):
            if p0 <= t <= p1:
                u = (t - p0) / max(1e-6, p1 - p0); px[x, 0] = lerp(c0, c1, u) + (int(255 * (a0 + (a1 - a0) * u)),); break
    return im.resize((w, h), Image.NEAREST)

def diag(w, h, stops, deg=160):
    a = math.radians(deg); dx, dy = math.sin(a), -math.cos(a); L = abs(w * dx) + abs(h * dy)
    im = Image.new("RGBA", (w, h)); px = im.load()
    for y in range(h):
        for x in range(w):
            t = min(1, max(0, ((x - w / 2) * dx + (y - h / 2) * dy) / L + 0.5))
            for (p0, c0), (p1, c1) in zip(stops, stops[1:]):
                if p0 <= t <= p1: px[x, y] = rgba(lerp(c0, c1, (t - p0) / max(1e-6, p1 - p0))); break
    return im

def font(size, index=2):
    for p in ("/System/Library/Fonts/Avenir Next Condensed.ttc", "/System/Library/Fonts/Supplemental/Avenir Next Condensed.ttc"):
        if os.path.exists(p): return ImageFont.truetype(p, size, index=index)
    for p in ("C:/Windows/Fonts/bahnschrift.ttf", "C:/Windows/Fonts/arialbd.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"):
        if os.path.exists(p): return ImageFont.truetype(p, size)
    return ImageFont.load_default()

def glow(im, x, y, w, h=2):
    im.alpha_composite(hglow(w * S, h * S, [(0, C_ACC, 0), (0.3, C_ACC, 1), (0.5, C_TEXT, 1), (0.7, C_ACC, 1), (1, C_ACC, 0)]), (x * S, y * S))

def marks(d, x, y, w, h, inset=7, L=13, T=2, dots=True):
    """corner marks and signal dots of a screen"""
    for cx, cy, sx, sy in ((x + inset, y + inset, 1, 1), (x + w - inset, y + inset, -1, 1), (x + inset, y + h - inset, 1, -1), (x + w - inset, y + h - inset, -1, -1)):
        X, Y = cx * S, cy * S
        d.rectangle(box(X, Y, X + sx * L * S, Y + sy * T * S), fill=rgba(C_ACC)); d.rectangle(box(X, Y, X + sx * T * S, Y + sy * L * S), fill=rgba(C_ACC))
    if dots:
        for k, op in enumerate((0.35, 0.6, 1)):
            cx = (x + w - 46 + k * 10) * S
            d.ellipse([cx, (y + h - 19) * S, cx + 5 * S, (y + h - 14) * S], fill=rgba(C_ACC, op))

def header(im, label, icon):
    d = Blend(im); y0 = 4
    d.rectangle([2 * S, y0 * S, (W - 2) * S - 1, (y0 + 48) * S - 1], fill=rgba((4, 20, 52)))
    d.line([2 * S, (y0 + 48) * S, (W - 2) * S, (y0 + 48) * S], fill=rgba(C_ACC, 0.22), width=S)
    bx, by = 20 * S, (y0 + 10) * S
    d.rectangle([bx, by, bx + 28 * S, by + 28 * S], outline=rgba(C_ACC), width=3)
    def P(px, py): return (bx + (7 + px * 14 / 24) * S, by + (7 + py * 14 / 24) * S)
    if icon == "globe":
        d.ellipse([*P(2, 2), *P(22, 22)], outline=rgba(C_TEXT), width=3); d.ellipse([*P(8, 2), *P(16, 22)], outline=rgba(C_TEXT), width=2)
        d.line([P(2, 12), P(22, 12)], fill=rgba(C_TEXT), width=2)
    else:
        d.line([P(12, 3.5), P(2, 20.5), P(22, 20.5), P(12, 3.5)], fill=rgba(C_TEXT), width=3, joint="curve")
        d.line([P(12, 9), P(12, 13.5)], fill=rgba(C_TEXT), width=3); d.ellipse([*P(11, 16), *P(13, 18)], fill=rgba(C_TEXT))
    f = font(14 * S); x = 58 * S
    for ch in label.upper():
        d.text((x, (y0 + 15) * S), ch, font=f, fill=rgba(C_TEXT)); x += d.textlength(ch, font=f) + 3 * S
    for x in range(58 * S, (W - 110) * S, 8 * S): d.line([x, (y0 + 35) * S, x + 4 * S, (y0 + 35) * S], fill=rgba(C_ACC, 0.30), width=S)
    for k, op in enumerate((0.35, 0.6, 1)):
        x = (W - 70 + k * 10) * S; d.ellipse([x, (y0 + 22) * S, x + 5 * S, (y0 + 27) * S], fill=rgba(C_ACC, op))

def fit(src, w, h):
    """picture -> w x h: cropped to fill, or whole over a blurred copy when it is much wider"""
    src = src.convert("RGB")
    if src.width / src.height > 1.25 * w / h:
        back = src.resize((w, h), Image.BILINEAR).filter(ImageFilter.GaussianBlur(w // 28))
        back = Image.blend(back, Image.new("RGB", (w, h), C_DARK), 0.45)
        hh = round(w * src.height / src.width); back.paste(src.resize((w, hh), Image.LANCZOS), (0, (h - hh) // 2))
        return back
    k = max(w / src.width, h / src.height); nw, nh = max(w, round(src.width * k)), max(h, round(src.height * k))
    big = src.resize((nw, nh), Image.LANCZOS); x, y = (nw - w) // 2, (nh - h) // 2
    return big.crop((x, y, x + w, y + h))

def top_art(label="WORLD NEWS", icon=None, picture=None, plain=False):
    """the whole top of the window, 581x490; with a picture it is the panel of one event"""
    icon = icon or ("globe" if label.upper() == "WORLD NEWS" else "warn")
    im = Image.new("RGBA", (W * S, TOP_H * S), rgba(C_DARK))
    header(im, label, icon)
    x, y, w, h = PIC
    im.paste(diag(w * S // 8, h * S // 8, [(0, C_MID), (0.3, C_LINE), (0.55, C_MID), (0.8, C_DARK), (1, C_DARK)]).resize((w * S, h * S), Image.BILINEAR), (x * S, y * S))
    d = Blend(im)
    for x1, y1, x2, y2 in ((0, 0.28, 1, 0.42), (0, 0.70, 1, 0.58), (0.12, 0, 0.10, 1), (0.9, 0, 0.91, 1)):
        d.line([(x + x1 * w) * S, (y + y1 * h) * S, (x + x2 * w) * S, (y + y2 * h) * S], fill=rgba(C_ACC, 0.13), width=S)
    im.paste(vgrad((W - 4) * S, (TOP_H - TITLE_Y) * S, C_MID, C_DARK), (2 * S, TITLE_Y * S)); glow(im, 2, TITLE_Y - 1, W - 4)
    for yy in range(3 * S, TOP_H * S, 4 * S): d.rectangle([0, yy, W * S, yy + S - 1], fill=(0, 0, 0, 12))
    if picture is not None:
        im.paste(fit(picture, w * S, h * S), (x * S, y * S))
        if not plain:
            for yy in range(y * S + 3 * S, (y + h) * S, 4 * S): d.rectangle([x * S, yy, (x + w) * S - 1, yy + S - 1], fill=(0, 0, 0, 26))
            vg = Image.new("L", (w * S, h * S), 110); ImageDraw.Draw(vg).ellipse([-w * S * 0.2, -h * S * 0.3, w * S * 1.2, h * S * 1.3], fill=0)
            sh = Image.new("RGBA", (w * S, h * S), (0, 0, 0, 255)); sh.putalpha(vg.filter(ImageFilter.GaussianBlur(40 * S))); im.alpha_composite(sh, (x * S, y * S))
    if not plain: marks(d, x, y, w, h, dots=picture is not None)
    d.rectangle([x * S - S, y * S - S, (x + w) * S, (y + h) * S], outline=rgba(C_ACC, 0.55), width=S)
    glow(im, x + int(w * 0.06), y - 1, int(w * 0.88))
    d.line([0, 0, W * S, 0], fill=rgba(C_LINE), width=3)
    d.line([S // 2, 0, S // 2, TOP_H * S], fill=rgba(C_LINE), width=3); d.line([W * S - 2, 0, W * S - 2, TOP_H * S], fill=rgba(C_LINE), width=3)
    for cx, sx in ((6, 1), (W - 6, -1)):
        X, Y = cx * S, 6 * S
        d.rectangle(box(X, Y, X + sx * 18 * S, Y + 2 * S), fill=rgba(C_ACC)); d.rectangle(box(X, Y, X + sx * 2 * S, Y + 18 * S), fill=rgba(C_ACC))
    out = im.resize((W, TOP_H), Image.LANCZOS); out.putalpha(255)
    return out

def panel(picture, label, icon=None, plain=False):
    return top_art(label, icon, picture, plain).crop((0, 0, W, PANEL_H))

def save_dds(im, path):
    """uncompressed 32 bit DDS, the format of the other DvE interface art"""
    im = im.convert("RGBA"); w, h = im.size; r, g, b, a = im.split()
    head = b"DDS " + struct.pack("<7I", 124, 0x100F, h, w, w * 4, 0, 1) + b"\0" * 44
    head += struct.pack("<2I4s5I", 32, 0x41, b"\0\0\0\0", 32, 0x00FF0000, 0x0000FF00, 0x000000FF, 0xFF000000) + struct.pack("<5I", 0x1000, 0, 0, 0, 0)
    with open(path, "wb") as f: f.write(head + Image.merge("RGBA", (b, g, r, a)).tobytes())

def save(im, path):
    im.save(path) if path.lower().endswith(".png") else save_dds(im, path)

if __name__ == "__main__":
    a = sys.argv[1:]
    if len(a) == 2 and a[0] == "--background":
        save(top_art(), a[1])
    elif len(a) == 3 and a[0] == "--empty":
        save(top_art(a[1]).crop((0, 0, W, PANEL_H)), a[2])
    elif len(a) >= 3 and not a[0].startswith("--"):
        icon = a[a.index("--icon") + 1] if "--icon" in a else None
        save(panel(Image.open(a[0]), a[1], icon, "--plain" in a), a[2])
    else:
        sys.exit(__doc__ or "usage: dve_event_panel.py picture \"HEADER TEXT\" out.dds [--icon warn|globe] [--plain] | --background out.dds")
