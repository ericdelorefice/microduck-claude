"""Procedural compass-rose marble floor for the rotunda, as a single square PNG that maps once
onto the circular floor disk. Cream Carrara field with fractal veining, a central medallion of
gold/rosso/nero rings + an 8-point star, 16 radial hairlines, and a dark outer border ring."""

from pathlib import Path

import numpy as np
from PIL import Image

N = 4096
yy, xx = np.mgrid[0:N, 0:N].astype(np.float32)
cx = cy = (N - 1) / 2.0
dx, dy = xx - cx, yy - cy
r = np.sqrt(dx * dx + dy * dy) / (N / 2.0)  # 0 at centre, 1 at edge mid-side
ang = np.arctan2(dy, dx)  # -pi..pi

# palette
cream = np.array([0.94, 0.92, 0.87])  # Carrara white (papal)
gold = np.array([0.84, 0.69, 0.33])  # bright gilt
rosso = np.array([0.58, 0.15, 0.16])  # cardinal red
nero = np.array([0.22, 0.18, 0.14])

# fractal marble veining (smooth fractal noise via upscaled octaves)
rng = np.random.default_rng(11)
turb = np.zeros((N, N), np.float32)
for octv in range(1, 6):
    f = 2**octv
    small = rng.random((f, f)).astype(np.float32)
    big = (
        np.asarray(
            Image.fromarray((small * 255).astype(np.uint8)).resize((N, N), Image.BILINEAR),
            np.float32,
        )
        / 255.0
    )
    turb += big / (2**octv)
veins = 0.5 + 0.5 * np.sin((xx / N * 6 + turb * 5) * np.pi)  # 0..1
field = cream[None, None, :] * (0.92 + 0.12 * veins[..., None])  # veined cream

img = field.copy()


def ring(rr, lo, hi, color):
    m = (rr >= lo) & (rr < hi)
    img[m] = color


# outer border: nero band with gold edge lines
ring(r, 0.965, 1.001, nero)
ring(r, 0.95, 0.965, gold)
ring(r, 0.90, 0.92, gold)
# 16 radial gold hairlines across the field
spokes = (
    (np.abs(((ang % (2 * np.pi / 16)) / (2 * np.pi / 16)) - 0.5) < 0.012) & (r > 0.33) & (r < 0.90)
)
img[spokes] = gold
# central medallion rings
ring(r, 0.30, 0.33, gold)
ring(r, 0.20, 0.30, rosso)
ring(r, 0.17, 0.20, gold)
# 8-point star inside r<0.17
star_ang = np.abs(((ang % (2 * np.pi / 8)) / (2 * np.pi / 8)) - 0.5)
star = (r < 0.17) & (r > 0.05) & (star_ang < 0.12 * (1 - r / 0.17) + 0.04)
img[star] = gold
ring(r, 0.0, 0.05, nero)  # centre boss

img = np.clip(img, 0, 1)
Image.fromarray((img * 255).astype(np.uint8)).save(
    Path(__file__).resolve().parents[2] / "scenes" / "textures" / "marble_compass.png"
)
print("wrote scenes/textures/marble_compass.png")
