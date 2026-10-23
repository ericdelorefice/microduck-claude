#!/usr/bin/env python3
"""Build the Microduck art-gallery demo scene.

Generates every texture (compass-rose marble floor, coffered dome ceiling, museum placards) and
the dome mesh into this repo's ``scenes/``, then writes ``scene_gallery.xml`` into your
``microduck_rl`` sim clone (it must live beside ``robot_groundcontact.xml`` so the relative
mesh include resolves).

Usage
-----
    MICRODUCK_RL_DIR=~/Pollen/microduck_rl python scripts/gallery/build_gallery.py
    # add --preview to also render offscreen preview PNGs into scenes/ (needs mujoco)

Requirements: ``pillow`` and ``numpy`` for the textures/mesh. Building the scene XML itself needs
neither. Then launch the sim from the microduck repo:

    DUCK_SIM_SCENE=gallery DUCK_SIM_CAMERAS=a scripts/duck-sim

and explore it:  MICRODUCK_ROBOT_BACKEND=rpc MICRODUCK_PERSONA=narrator microduck-claude explore
"""

from __future__ import annotations

import runpy
from pathlib import Path

HERE = Path(__file__).resolve().parent
# Order matters: assets first, then the scene that references them.
STEPS = ["gen_floor.py", "gen_dome_texture.py", "gen_plaques.py", "gen_dome_mesh.py", "build_scene.py"]


def main() -> None:
    for step in STEPS:
        print(f"\n=== {step} ===", flush=True)
        runpy.run_path(str(HERE / step), run_name="__main__")  # --preview flows through sys.argv
    print("\nGallery built. Launch:  DUCK_SIM_SCENE=gallery DUCK_SIM_CAMERAS=a scripts/duck-sim")


if __name__ == "__main__":
    main()
