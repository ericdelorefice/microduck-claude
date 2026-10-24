"""Generate small museum placard textures (title + artist) for each painting, as PNGs mapped onto
the plaque geoms. Ivory card, thin gold rule, serif text."""

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

OUT = str(Path(__file__).resolve().parents[2] / "scenes" / "textures")
Path(OUT).mkdir(parents=True, exist_ok=True)  # scenes/textures/ is gitignored, so may not exist
PLAQUES = {
    "mona": ("MONA LISA", "Leonardo da Vinci  ·  c.1503"),
    "starry": ("THE STARRY NIGHT", "Vincent van Gogh  ·  1889"),
    "wave": ("THE GREAT WAVE", "Katsushika Hokusai  ·  c.1831"),
    "salvator": ("SALVATOR MUNDI", "Leonardo da Vinci  ·  c.1500"),
    "scotland": ("SCOTLAND FOREVER!", "Lady Butler  ·  1881"),
    "brigade": ("CHARGE OF THE LIGHT BRIGADE", "R. Caton Woodville  ·  1894"),
}
W, Hh = 560, 320
IVORY = (243, 239, 230)
GOLD = (176, 142, 52)
INK = (38, 30, 22)
GREY = (90, 80, 68)

FONTS = [
    "/System/Library/Fonts/Supplemental/Georgia Bold.ttf",
    "/System/Library/Fonts/Supplemental/Times New Roman Bold.ttf",
    "/Library/Fonts/Georgia Bold.ttf",
]
FONTS_R = [
    "/System/Library/Fonts/Supplemental/Georgia.ttf",
    "/System/Library/Fonts/Supplemental/Times New Roman.ttf",
    "/Library/Fonts/Georgia.ttf",
]


def load(paths, size):
    for p in paths:
        try:
            return ImageFont.truetype(p, size)
        except OSError:
            pass
    return ImageFont.load_default()


def wrap(draw, text, font, maxw):
    words, lines, cur = text.split(), [], ""
    for w in words:
        t = (cur + " " + w).strip()
        if draw.textlength(t, font=font) <= maxw:
            cur = t
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


for key, (title, artist) in PLAQUES.items():
    img = Image.new("RGB", (W, Hh), IVORY)
    d = ImageDraw.Draw(img)
    d.rectangle([6, 6, W - 7, Hh - 7], outline=GOLD, width=5)
    # fit title (shrink until it fits in <=2 lines across the card)
    for ts in (62, 56, 50, 44, 40, 36):
        tf = load(FONTS, ts)
        lines = wrap(d, title, tf, W - 70)
        if len(lines) <= 2:
            break
    af = load(FONTS_R, 34)
    lh = tf.size + 8
    total = lh * len(lines) + 46
    y = (Hh - total) // 2
    for ln in lines:
        w = d.textlength(ln, font=tf)
        d.text(((W - w) / 2, y), ln, font=tf, fill=INK)
        y += lh
    y += 6
    d.line([(W / 2 - 90, y), (W / 2 + 90, y)], fill=GOLD, width=3)
    y += 12
    w = d.textlength(artist, font=af)
    d.text(((W - w) / 2, y), artist, font=af, fill=GREY)
    img.save(f"{OUT}/plaque_{key}.png")
    print("wrote", f"plaque_{key}.png", "-", title)
