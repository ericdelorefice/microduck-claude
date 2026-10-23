"""Generate a true curved dome as an OBJ mesh (spherical cap) for the rotunda, with INWARD-facing
winding/normals (so MuJoCo, which back-face-culls, renders it from inside) and a RADIAL UV unwrap
so the circular Apotheosis fresco maps center->apex, rim->base. Baked in world coordinates so the
geom needs no transform.

If the dome renders invisible from inside, set FLIP=True (reverses triangle winding)."""

import math
import os
from pathlib import Path

OUT = str(Path(__file__).resolve().parents[2] / "scenes" / "meshes" / "dome.obj")
R = 3.55       # base radius = drum INNER wall face, so the dome springs flush with the wall
H = 2.8        # base height (drum top = dome springing)
RISE = 2.6     # dome rise above the springing
NPHI = 24      # rings from apex to base
NTH = 72       # segments around
FLIP = True

a = (R * R - RISE * RISE) / (2 * RISE)
zc = H - a                     # sphere centre height
Rs = H + RISE - zc             # sphere radius
phimax = math.acos((H - zc) / Rs)

verts, uvs, norms = [], [], []
# apex (vertex 1)
verts.append((0.0, 0.0, zc + Rs)); uvs.append((0.5, 0.5)); norms.append((0.0, 0.0, -1.0))
for i in range(1, NPHI + 1):
    phi = phimax * i / NPHI
    for j in range(NTH):
        th = 2 * math.pi * j / NTH
        x = Rs * math.sin(phi) * math.cos(th)
        y = Rs * math.sin(phi) * math.sin(th)
        z = zc + Rs * math.cos(phi)
        verts.append((x, y, z))
        rr = 0.5 * (phi / phimax)
        uvs.append((0.5 - rr * math.cos(th), 0.5 + rr * math.sin(th)))   # -cos un-mirrors the text
        norms.append((-x / Rs, -y / Rs, -(z - zc) / Rs))   # inward


def idx(i, j):
    return 2 + (i - 1) * NTH + (j % NTH)   # apex=1; ring i (1..NPHI), seg j


faces = []
for j in range(NTH):                        # apex fan
    tri = (1, idx(1, j), idx(1, j + 1))
    faces.append(tri if not FLIP else (tri[0], tri[2], tri[1]))
for i in range(1, NPHI):                     # quad bands
    for j in range(NTH):
        v00, v01 = idx(i, j), idx(i, j + 1)
        v10, v11 = idx(i + 1, j), idx(i + 1, j + 1)
        if not FLIP:
            faces += [(v00, v10, v11), (v00, v11, v01)]
        else:
            faces += [(v00, v11, v10), (v00, v01, v11)]

os.makedirs(os.path.dirname(OUT), exist_ok=True)
with open(OUT, "w") as f:
    for v in verts:
        f.write(f"v {v[0]:.5f} {v[1]:.5f} {v[2]:.5f}\n")
    for t in uvs:
        f.write(f"vt {t[0]:.5f} {t[1]:.5f}\n")
    for n in norms:
        f.write(f"vn {n[0]:.5f} {n[1]:.5f} {n[2]:.5f}\n")
    for fa in faces:
        f.write("f " + " ".join(f"{k}/{k}/{k}" for k in fa) + "\n")
print(f"wrote {OUT}: {len(verts)} verts, {len(faces)} faces; apex z={zc+Rs:.2f}, base z={H}, Rs={Rs:.2f}")
