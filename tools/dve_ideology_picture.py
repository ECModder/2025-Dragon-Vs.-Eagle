#!/usr/bin/env python3
"""DvE - picture shown in the tooltip of a sub-ideology.

The tooltip of the ideology icon prints <sub_ideology>_desc. The picture is
a text icon (GFX_img_<sub_ideology>) written inside that description, with
blank lines above and below to make room for it.

  python3 tools/dve_ideology_picture.py photo.jpg market_socialism
      crop the photo to A4 landscape, resize it to 325x230 and save it as
      gfx/texticons/ideologies/market_socialism.jpg
  python3 tools/dve_ideology_picture.py --placeholders [--force]
      draw a placeholder for every sub-ideology without a picture
  python3 tools/dve_ideology_picture.py --check
      list the sub-ideologies missing a picture, a sprite or a description
  python3 tools/dve_ideology_picture.py --spacing 9
      blank lines above and below the picture, in every description

Needs Pillow (pip install pillow).
"""
import os, re, sys
from PIL import Image, ImageDraw, ImageFilter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
W, H = 325, 230            # A4 landscape, as wide as the tooltip text
PICS = "gfx/texticons/ideologies"
GFX = "interface/DVE_ideology_pictures.gfx"
LOC = "localisation/english/parties_l_english.yml"
IDEOLOGIES = "common/ideologies/00_ideologies.txt"
ICONS = "interface/ideologies.gfx"


def path(rel): return os.path.join(ROOT, rel)
def key(sub): return sub.lower()
def picture(sub): return path("%s/%s.jpg" % (PICS, key(sub)))


def block(text, start):
    """End index of the { } block opened just before start."""
    depth, i = 1, start
    while depth:
        depth += (text[i] == "{") - (text[i] == "}")
        i += 1
    return i


def sub_ideologies():
    """[(sub_ideology, group, (r, g, b))] read from the ideologies file."""
    text = re.sub(r"#.*", "", open(path(IDEOLOGIES), encoding="utf-8-sig").read())
    start = text.index("{", text.index("ideologies")) + 1
    out, pos, opener = [], start, re.compile(r"(\w+)\s*=\s*\{")
    while True:
        m = opener.search(text, pos)
        if not m: break
        end = block(text, m.end())
        body = text[m.end():end]
        c = re.search(r"color\s*=\s*\{([^}]*)\}", body)
        color = tuple(int(float(v)) for v in c.group(1).split()[:3]) if c else (90, 90, 90)
        t = re.search(r"types\s*=\s*\{", body)
        if t:
            inner = body[t.end():block(body, t.end()) - 1]
            for s in opener.finditer(inner):
                before = inner[:s.start()]
                if before.count("{") == before.count("}"):
                    out.append((s.group(1), m.group(1), color))
        pos = end
    return out


def icon(sub, group):
    """Icon of the sub-ideology, or of its group."""
    text = open(path(ICONS), encoding="utf-8-sig").read()
    sprites = dict(re.findall(r'name\s*=\s*"(\w+)"\s*\n\s*texturefile\s*=\s*"([^"]+)"', text))
    for name in ("GFX_ideology_" + sub, "GFX_ideology_%s_group" % group):
        if name in sprites and os.path.isfile(path(sprites[name])):
            return Image.open(path(sprites[name])).convert("RGBA")
    return None


def fit(im):
    """Centre crop to the A4 ratio, then resize."""
    im = im.convert("RGB")
    w, h = im.size
    if w * H > h * W:
        nw = h * W // H
        im = im.crop(((w - nw) // 2, 0, (w - nw) // 2 + nw, h))
    else:
        nh = w * H // W
        im = im.crop((0, (h - nh) // 2, w, (h - nh) // 2 + nh))
    return im.resize((W, H), Image.LANCZOS)


def placeholder(sub, group, color):
    """Group-coloured card with the icon of the sub-ideology."""
    dark = tuple(int(c * 0.16) + 8 for c in color)
    mid = tuple(int(c * 0.55) + 14 for c in color)
    im = Image.new("RGB", (W, H), dark)
    glow = Image.new("L", (W, H), 0)
    ImageDraw.Draw(glow).ellipse([W // 2 - 135, H // 2 - 100, W // 2 + 135, H // 2 + 100], fill=210)
    im.paste(Image.new("RGB", (W, H), mid), (0, 0), glow.filter(ImageFilter.GaussianBlur(48)))
    d = ImageDraw.Draw(im)
    for y in range(0, H, 3):                                   # scan lines
        d.line([(0, y), (W, y)], fill=tuple(max(0, c - 5) for c in im.getpixel((W // 2, y))))
    ic = icon(sub, group)
    if ic:
        ic = ic.resize((ic.width * 2, ic.height * 2), Image.LANCZOS)
        shadow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        shadow.paste((0, 0, 0, 150), ((W - ic.width) // 2 + 3, (H - ic.height) // 2 + 5), ic)
        im.paste(shadow.filter(ImageFilter.GaussianBlur(6)), (0, 0), shadow.filter(ImageFilter.GaussianBlur(6)))
        im.paste(ic, ((W - ic.width) // 2, (H - ic.height) // 2), ic)
    d = ImageDraw.Draw(im)
    d.rectangle([0, 0, W - 1, H - 1], outline=tuple(min(255, c + 60) for c in mid))
    d.rectangle([1, 1, W - 2, H - 2], outline=(0, 0, 0))
    return im


def save(im, sub):
    os.makedirs(path(PICS), exist_ok=True)
    im.save(picture(sub), "JPEG", quality=92, progressive=False)


def sprite(sub):
    return ('\tspriteType = {\n\t\tname = "GFX_img_%s"\n\t\ttexturefile = "%s/%s.jpg"\n'
            '\t\tlegacy_lazy_load = no\n\t}\n' % (key(sub), PICS, key(sub)))


def ensure_sprite(sub):
    """Add the sprite of a new sub-ideology at the end of the gfx file."""
    text = open(path(GFX), encoding="utf-8").read()
    if '"GFX_img_%s"' % key(sub) in text:
        return
    cut = text.rindex("}")
    open(path(GFX), "w", encoding="utf-8", newline="\n").write(text[:cut] + sprite(sub) + text[cut:])
    print("sprite GFX_img_%s added to %s" % (key(sub), GFX))


def check():
    gfx = open(path(GFX), encoding="utf-8").read()
    loc = open(path(LOC), encoding="utf-8-sig").read()
    bad = 0
    for sub, group, _ in sub_ideologies():
        miss = []
        if not os.path.isfile(picture(sub)): miss.append("picture")
        if '"GFX_img_%s"' % key(sub) not in gfx: miss.append("sprite")
        if not re.search(r"^ %s:" % re.escape(sub), loc, re.M): miss.append("name")
        d = re.search(r'^ %s_desc:\d* "(.*)"' % re.escape(sub), loc, re.M)
        if not d: miss.append("description")
        elif "£img_%s " % key(sub) not in d.group(1): miss.append("picture not in the description")
        if miss:
            bad += 1
            print("%-36s %-24s %s" % (sub, group, ", ".join(miss)))
    print("%d sub-ideologies, %d with something missing" % (len(sub_ideologies()), bad))


def spacing(n):
    """Same number of blank lines around every picture (targeted edit)."""
    raw = open(path(LOC), encoding="utf-8-sig").read()
    new, count = re.subn(r"(?:\\n)+(£img_\w+ )(?:\\n)+", lambda m: "\\n" * n + m.group(1) + "\\n" * n, raw)
    open(path(LOC), "w", encoding="utf-8-sig", newline="\n").write(new)
    print("%d descriptions set to %d blank lines" % (count, n))


def main(argv):
    if "--check" in argv:
        return check()
    if "--spacing" in argv:
        return spacing(int(argv[argv.index("--spacing") + 1]))
    subs = sub_ideologies()
    if "--placeholders" in argv:
        made = 0
        for sub, group, color in subs:
            if "--force" in argv or not os.path.isfile(picture(sub)):
                save(placeholder(sub, group, color), sub)
                ensure_sprite(sub)
                made += 1
        return print("%d placeholders written to %s" % (made, PICS))
    if len(argv) != 2:
        return print(__doc__)
    src, sub = argv
    names = {s.lower(): s for s, _, _ in subs}
    if sub.lower() not in names:
        sys.exit("unknown sub-ideology: %s (see %s)" % (sub, IDEOLOGIES))
    sub = names[sub.lower()]
    save(fit(Image.open(src)), sub)
    ensure_sprite(sub)
    print("saved %s/%s.jpg (%dx%d)" % (PICS, key(sub), W, H))


if __name__ == "__main__":
    main(sys.argv[1:])
