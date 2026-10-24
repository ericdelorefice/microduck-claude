"""Generate a cathedral-rotunda MuJoCo scene for the Microduck and render it from the user's
overhead viewer angle (so what I see matches their live window).

From the research brief:
  - Drum = N tangent box panels around a circle (R apothem). Inner faces point inward -> render
    (no back-face-cull issue). Painting quat on a radial wall = qz(phi-90deg) * (+Y-wall base quat).
  - Ceiling = a FLAT disk (MuJoCo back-face-culls spheres, so a hemisphere seen from inside is
    invisible). A type="2d" mural maps cleanly on the disk's down-facing cap. `emission` makes it GLOW.
  - LIGHTING FIX: the headlight is camera-attached, so its diffuse vanishes on walls the camera
    isn't facing -> dark room in the live viewer. Fix = high warm AMBIENT (view-independent) +
    world-fixed point/spot lights + emission on the fresco. Verified by rendering top-down.
  - Floor plane stays collidable; everything else is contype=0 conaffinity=0 so duck physics is
    unchanged. Built on robot_groundcontact.xml (the robot that stands).
"""

import math
import os
import sys
from pathlib import Path

REPO = str(Path(__file__).resolve().parents[2])
# The microduck_rl sim clone (scene_gallery.xml must live beside robot_groundcontact.xml there).
_RL = os.environ.get("MICRODUCK_RL_DIR", os.path.expanduser("~/Pollen/microduck_rl"))
MICRODUCK = f"{_RL}/src/mjlab_microduck/robot/microduck"
PAINT = f"{REPO}/scenes/paintings"
TEX = f"{REPO}/scenes/textures"
OUT_SCENE = f"{MICRODUCK}/scene_gallery.xml"

R = 3.6  # drum apothem (panel-midpoint radius)
NP = 40  # drum panels (smoother curve at this radius)
H = 2.8  # drum height / dome springing
WALL_T = 0.05  # wall half-thickness
RIN = R - WALL_T  # inner wall face radius
PZ = 0.88  # painting centre height (natural gallery hang, clears the floor)


def qz(a):
    return (math.cos(a / 2), 0.0, 0.0, math.sin(a / 2))


def qmul(a, b):
    aw, ax, ay, az = a
    bw, bx, by, bz = b
    return (
        aw * bw - ax * bx - ay * by - az * bz,
        aw * bx + ax * bw + ay * bz - az * by,
        aw * by - ax * bz + ay * bw + az * bx,
        aw * bz + ax * by - ay * bx + az * bw,
    )


Q0 = (0.7071067811865476, 0.7071067811865476, 0.0, 0.0)  # +Y-wall base: +Z->inward, +Y->up


def paint_quat(phi):
    return qmul(qz(phi - math.pi / 2), Q0)


def qs(q):
    return f"{q[0]:.5f} {q[1]:.5f} {q[2]:.5f} {q[3]:.5f}"


# name, file, aspect(w/h), phi(deg), hero?, real_height_m, frame style
PAINTINGS = [
    ("mona", "mona_lisa.png", 536 / 800, 0, True, 0.77, "gilt"),
    ("starry", "starry_night.png", 800 / 633, 60, False, 0.74, "ebony"),
    ("wave", "great_wave.png", 800 / 537, 120, False, 0.26, "wood"),
    ("salvator", "salvator_mundi.png", 543 / 800, 180, True, 0.66, "gilt"),
    ("scotland", "scotland_forever.png", 800 / 405, 240, False, 1.02, "ebony"),
    ("brigade", "light_brigade.png", 800 / 486, 300, False, 1.00, "wood"),
]

# frame styles -> (inner liner, middle band, outer band) materials; liner is always gilt
STYLES = {
    "gilt": ("gold", "gold2", "gold"),
    "wood": ("gold", "wood", "wood"),
    "ebony": ("gold", "ebony", "ebony"),
}


def painting_body(name, file, aspect, phi_deg, hero, real_h, style):
    phi = math.radians(phi_deg)
    hh = real_h / 2
    hw = hh * aspect
    fw = (0.10 if hero else 0.085) * (2 * max(hh, hw))  # total frame face width
    fd = 0.07 if hero else 0.055  # frame depth (proud of wall)
    # mount so even the frame's outer corners stay INSIDE the curved wall (no poke-through)
    pr = math.sqrt(max(RIN * RIN - (hw + fw) ** 2, 1.0)) - 0.03
    t1, t2, t3 = fw * 0.22, fw * 0.33, fw * 0.45  # inner liner / middle / outer bands
    z1, z2, z3 = fd * 0.45, fd * 0.72, fd  # stepped proudness -> carved molding
    px, py = pr * math.cos(phi), pr * math.sin(phi)

    def tier(tag, off, w, pz, mat):
        oe, c = hw + off + w, hh + off + w / 2
        return [
            f'            <geom name="{tag}_{name}_t" type="box" size="{oe:.3f} {w / 2:.3f} {pz / 2:.3f}" pos="0 {c:.3f} {pz / 2:.3f}" material="{mat}" contype="0" conaffinity="0" group="1"/>',
            f'            <geom name="{tag}_{name}_b" type="box" size="{oe:.3f} {w / 2:.3f} {pz / 2:.3f}" pos="0 {-c:.3f} {pz / 2:.3f}" material="{mat}" contype="0" conaffinity="0" group="1"/>',
            f'            <geom name="{tag}_{name}_l" type="box" size="{w / 2:.3f} {hh:.3f} {pz / 2:.3f}" pos="{-(hw + off + w / 2):.3f} 0 {pz / 2:.3f}" material="{mat}" contype="0" conaffinity="0" group="1"/>',
            f'            <geom name="{tag}_{name}_r" type="box" size="{w / 2:.3f} {hh:.3f} {pz / 2:.3f}" pos="{hw + off + w / 2:.3f} 0 {pz / 2:.3f}" material="{mat}" contype="0" conaffinity="0" group="1"/>',
        ]

    parts = [
        f'        <body name="art_{name}" pos="{px:.3f} {py:.3f} {PZ}" quat="{qs(paint_quat(phi))}">',
        f'            <geom name="canvas_{name}" type="box" size="{hw:.3f} {hh:.3f} 0.008" material="m_{name}" contype="0" conaffinity="0" group="1"/>',
    ]
    liner, mid, outer = STYLES[style]
    parts += tier("fi", 0.0, t1, z1, liner)  # inner gilt liner
    parts += tier("fm", t1, t2, z2, mid)  # middle band (style)
    parts += tier("fo", t1 + t2, t3, z3, outer)  # outer band (style)
    parts.append(
        f'            <geom name="label_{name}" type="box" size="0.098 0.056 0.004" pos="{hw + fw + 0.14:.3f} {-(hh * 0.3):.3f} 0.015" material="pl_{name}" contype="0" conaffinity="0" group="1"/>'
    )
    parts.append("        </body>")
    return "\n".join(parts)


def drum():
    out = []
    hw = R * math.tan(math.pi / NP) * 1.03  # +3% so panels overlap at corners (no seams)
    for i in range(NP):
        th = 2 * math.pi * i / NP
        px, py = R * math.cos(th), R * math.sin(th)
        out.append(
            f'        <geom name="drum_{i}" type="box" size="{hw:.4f} 0.05 {H / 2:.3f}" '
            f'pos="{px:.4f} {py:.4f} {H / 2:.3f}" quat="{qs(qz(th + math.pi / 2))}" '
            f'material="wall" contype="0" conaffinity="0" group="1"/>'
        )
    return "\n".join(out)


def cornice():
    # one clean gilt ring at the wall->dome seam (dome base = RIN, so they meet flush)
    out = []
    hw = R * math.tan(math.pi / NP) * 1.10
    for i in range(NP):
        th = 2 * math.pi * i / NP
        c, s = math.cos(th), math.sin(th)
        out.append(
            f'        <geom name="cor_{i}" type="box" size="{hw:.4f} 0.05 0.06" '
            f'pos="{RIN * c:.4f} {RIN * s:.4f} {H:.3f}" quat="{qs(qz(th + math.pi / 2))}" '
            f'material="gold" contype="0" conaffinity="0" group="1"/>'
        )
    return "\n".join(out)


def pilasters():
    out = []
    n = 6  # one per gap between the 6 paintings (never behind one)
    sh_h = (H - 0.30) / 2  # shaft half-height (room for capital + base)
    for k in range(n):
        th = math.radians(30) + 2 * math.pi * k / n
        c, s = math.cos(th), math.sin(th)
        q = qs(qz(th + math.pi / 2))
        px, py = (R - 0.07) * c, (R - 0.07) * s
        out.append(
            f'        <geom name="pil_{k}" type="box" size="0.10 0.05 {sh_h:.3f}" '
            f'pos="{px:.4f} {py:.4f} {0.12 + sh_h:.3f}" quat="{q}" material="pilaster" contype="0" conaffinity="0" group="1"/>'
        )
        out.append(
            f'        <geom name="cap_{k}" type="box" size="0.13 0.06 0.05" '
            f'pos="{px:.4f} {py:.4f} {H - 0.12:.3f}" quat="{q}" material="gold" contype="0" conaffinity="0" group="1"/>'
        )
        out.append(
            f'        <geom name="base_{k}" type="box" size="0.12 0.06 0.06" '
            f'pos="{px:.4f} {py:.4f} 0.06" quat="{q}" material="gold" contype="0" conaffinity="0" group="1"/>'
        )
    return "\n".join(out)


KEYFRAMES = """
    <keyframe>
        <key name="INIT" qpos="0 0 0.12 1 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0" ctrl="0 0 0 0 0 0 0 0 0 0 0 0 0 0"/>
        <key name="STAND" qpos="
        0 0 0.12 1 0 0 0
        0 -0.08726646259971647 -0.457924 -0.004940 0.452984
        0.3490658503988659 0.3490658503988659 0 0
        0 0.08726646259971647 0.457924 0.004940 -0.452984"
         ctrl="
        0 -0.08726646259971647 -0.457924 -0.004940 0.452984
        0.3490658503988659 0.3490658503988659 0 0
        0 0.08726646259971647 0.457924 0.004940 -0.452984"
        />
        <key name="SIT" qpos="
        0 0 0.07 1 0 0 0
        0 0 -0.5236 1.0472
        0 0.5 1.6 0
        0 0 0 0.5236 -1.0472 0" ctrl="
        0 0 -0.5236 1.0472 0
        0.5 1.6 0 0 0
        0 0.5236 -1.0472 0"/>
        <key name="FOLD" qpos="
        0 0 0.07 1 0 0 0
        0 0 1.57 1.57 0
        1 1 0 0 0
        0 -1.57 -1.57 0" ctrl="
        0 0 1.57 1.57 0
        1 1 0 0
        0 0 -1.57 -1.57 0"/>
    </keyframe>"""


def build_xml():
    tex, mats = [], []
    for p in PAINTINGS:
        n = p[0]
        tex.append(f'        <texture type="2d" name="t_{n}" file="{PAINT}/{p[1]}"/>')
        tex.append(f'        <texture type="2d" name="t_pl_{n}" file="{TEX}/plaque_{n}.png"/>')
        mats.append(f'        <material name="m_{n}" texture="t_{n}" texuniform="false"/>')
        mats.append(
            f'        <material name="pl_{n}" texture="t_pl_{n}" texuniform="false" texrepeat="1 1" emission="0.28"/>'
        )
    bodies = "".join(painting_body(*p) for p in PAINTINGS)
    return f"""<mujoco model="gallery">
    <!-- Cathedral rotunda for the Microduck. Drum = {NP} tangent panels (R={R}); flat fresco ceiling
         disk (Brumidi 'Apotheosis', public domain) that GLOWS via material emission; compass-rose
         marble floor. Floor plane stays collidable; all scenery is contype=0 conaffinity=0 so the
         duck's physics is unchanged. Generated by scratchpad/generate_rotunda.py.
         Launch:  DUCK_SIM_SCENE=gallery DUCK_SIM_CAMERAS=a scripts/duck-sim -->
    <include file="robot_groundcontact.xml" />

    <visual>
        <headlight ambient="0.24 0.23 0.21" diffuse="0.18 0.17 0.15" specular="0.05 0.05 0.05"/>
        <quality shadowsize="2048"/>
        <map haze="0.12"/>
        <rgba haze="0.90 0.86 0.78 1"/>
        <global azimuth="130" elevation="-18" offwidth="1280" offheight="960"/>
    </visual>

    <asset>
        <texture type="skybox" builtin="gradient" rgb1="0.82 0.80 0.76" rgb2="0.55 0.54 0.52" width="512" height="3072"/>
        <mesh name="dome" file="{REPO}/scenes/meshes/dome.obj"/>
        <texture type="2d" name="t_fresco" file="{TEX}/dome_ceiling.png"/>
        <texture type="2d" name="t_compass" file="{TEX}/marble_compass.png"/>
        <material name="wall" rgba="0.93 0.91 0.85 1" specular="0.05" shininess="0.1" reflectance="0" emission="0.20"/>
        <material name="pilaster" rgba="0.96 0.95 0.91 1" specular="0.05" shininess="0.1" emission="0.22"/>
        <material name="gold" rgba="0.92 0.78 0.40 1" specular="0.95" shininess="0.98" reflectance="0.15" emission="0.06"/>
        <material name="gold2" rgba="0.74 0.60 0.26 1" specular="0.85" shininess="0.9" reflectance="0.08" emission="0.04"/>
        <material name="wood" rgba="0.26 0.15 0.08 1" specular="0.3" shininess="0.5" emission="0.04"/>
        <material name="ebony" rgba="0.09 0.08 0.08 1" specular="0.45" shininess="0.65" emission="0.03"/>
        <material name="fresco" texture="t_fresco" texuniform="false" texrepeat="1 1" emission="0.55" specular="0.1" shininess="0.2"/>
        <material name="compass" texture="t_compass" texuniform="false" texrepeat="1 1" specular="0.1" shininess="0.3" reflectance="0.04" emission="0.03"/>
        <material name="marble" rgba="0.92 0.90 0.86 1" specular="0.2" shininess="0.2" reflectance="0"/>
{chr(10).join(tex)}
{chr(10).join(mats)}
    </asset>

    <worldbody>
        <!-- scene lights: fixed in the world so shading is stable as the camera orbits -->
        <light name="oculus" type="spot" pos="0 0 {H - 0.35:.2f}" dir="0 0 -1" cutoff="62" exponent="10" diffuse="0.20 0.19 0.16" specular="0.1 0.1 0.1" castshadow="true"/>
        <light name="wash_px" type="directional" dir="1 0 -0.7" diffuse="0.17 0.16 0.14" specular="0 0 0" castshadow="false"/>
        <light name="wash_nx" type="directional" dir="-1 0 -0.7" diffuse="0.17 0.16 0.14" specular="0 0 0" castshadow="false"/>
        <light name="wash_py" type="directional" dir="0 1 -0.7" diffuse="0.17 0.16 0.14" specular="0 0 0" castshadow="false"/>
        <light name="wash_ny" type="directional" dir="0 -1 -0.7" diffuse="0.17 0.16 0.14" specular="0 0 0" castshadow="false"/>

        <!-- collidable floor plane (physics); marble colour, shows outside the room -->
        <geom name="floor" size="0 0 0.05" pos="0 0 0" type="plane" material="marble"/>
        <!-- compass-rose marble disk overlay inside the drum (visual only, reflective) -->
        <geom name="compass" type="box" size="{R:.2f} {R:.2f} 0.002" pos="0 0 0.001" material="compass" contype="0" conaffinity="0" group="1"/>

{drum()}

{pilasters()}

{cornice()}

        <!-- true curved dome mesh; fresco maps radially (centre->apex) and glows via emission -->
        <geom name="dome" type="mesh" mesh="dome" material="fresco" contype="0" conaffinity="0" group="1"/>
{bodies}
    </worldbody>
{KEYFRAMES}
</mujoco>
"""


def render(scene, cam_cfg, out, w=1280, h=960):
    import mujoco  # lazy: only for optional --preview renders, not for building the scene

    m = mujoco.MjModel.from_xml_path(scene)
    d = mujoco.MjData(m)
    names = [mujoco.mj_id2name(m, mujoco.mjtObj.mjOBJ_KEY, i) for i in range(m.nkey)]
    k = names.index("STAND")
    d.qpos[:] = m.key_qpos[k]
    d.ctrl[:] = m.key_ctrl[k]
    mujoco.mj_forward(m, d)
    r = mujoco.Renderer(m, h, w)
    if isinstance(cam_cfg, str):  # fixed camera defined in the scene
        r.update_scene(d, camera=cam_cfg)
    else:  # free orbit camera
        cam = mujoco.MjvCamera()
        mujoco.mjv_defaultFreeCamera(m, cam)
        cam.lookat[:] = cam_cfg["lookat"]
        cam.distance = cam_cfg["distance"]
        cam.azimuth = cam_cfg["azimuth"]
        cam.elevation = cam_cfg["elevation"]
        r.update_scene(d, cam)
    from PIL import Image

    Image.fromarray(r.render()).save(out)
    print("rendered", out, "ngeom", m.ngeom, "nlight", m.nlight)


if __name__ == "__main__":
    with open(OUT_SCENE, "w") as f:
        f.write(build_xml())
    print("wrote", OUT_SCENE)
    if "--preview" in sys.argv:  # optional offscreen previews (needs mujoco), via free cameras
        render(
            OUT_SCENE,
            {"lookat": [0.5, 0, 0.6], "distance": 1.7, "azimuth": 0, "elevation": -4},
            f"{REPO}/scenes/rot_hero.png",
        )
        render(
            OUT_SCENE,
            {"lookat": [0.3, 0, 0.4], "distance": 1.5, "azimuth": 0, "elevation": -6},
            f"{REPO}/scenes/rot_duck.png",
        )
