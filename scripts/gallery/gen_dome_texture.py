"""Procedural radially-symmetric COFFERED dome ceiling (cream + gilt ribs + recessed coffers +
a gilt oculus). Because it's radially symmetric it maps onto the dome perfectly from any angle —
no figurative-fresco centering problem. Maps via the dome mesh's radial UV (apex = image centre)."""

from pathlib import Path

import numpy as np
from PIL import Image

N = 2048
yy, xx = np.mgrid[0:N, 0:N].astype(np.float32)
cx = cy = (N - 1) / 2.0
dx, dy = xx - cx, yy - cy
r = np.sqrt(dx * dx + dy * dy) / (N / 2.0)  # 0 centre .. 1 edge-mid
ang = np.arctan2(dy, dx)

cream = np.array([0.91, 0.88, 0.81])
gold = np.array([0.82, 0.67, 0.32])
glow = np.array([0.97, 0.94, 0.86])

NR, NM = 6, 22  # coffer rings / meridians
cell_r = (r * NR) % 1.0
cell_m = (((ang + np.pi) / (2 * np.pi)) * NM) % 1.0
# distance to the nearest coffer edge (0 at a rib, ~0.5 at the coffer centre)
edge = np.minimum(np.minimum(cell_r, 1 - cell_r), np.minimum(cell_m, 1 - cell_m))

# recessed coffers: darken toward the coffer centre for a sunk, shadowed look
recess = np.clip((edge - 0.06) / 0.44, 0, 1)  # 0 at rib, 1 deep in the cell
img = cream[None, None, :] * (1.0 - 0.16 * recess[..., None])

# gilt ribs along every coffer edge
rib = edge < 0.05
img[rib] = gold
# a small gilt rosette boss at each coffer centre
rosette = edge > 0.42
img[rosette] = gold * 0.9 + cream * 0.1

# central oculus: gilt ring + warm glow
img[r < 0.11] = gold
img[r < 0.085] = glow
# outer gilt band (meets the cornice at the dome base)
img[r > 0.94] = gold

img = np.clip(img, 0, 1)
out = Path(__file__).resolve().parents[2] / "scenes" / "textures" / "dome_ceiling.png"
out.parent.mkdir(parents=True, exist_ok=True)  # scenes/textures/ is gitignored, so may not exist
Image.fromarray((img * 255).astype(np.uint8)).save(out)
print("wrote scenes/textures/dome_ceiling.png")
