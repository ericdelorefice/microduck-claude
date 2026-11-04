"""Record a 3rd-person "gallery" shot of the live Microduck — headless, no onscreen viewer, no
screen capture.

Why this exists. Screen-recording the MuJoCo viewer window (OBS, QuickTime, ScreenCaptureKit)
competes with the sim for the GPU and the macOS compositor and stalls it: the body server steps
physics, presents the onscreen viewer and reads back the camera on one serial thread, so a recorder
that slows the present slows physics, the walk policy falls behind real time, and the duck stops.
(robotd's 500 ms deadman is wall-clock and is *not* the coupling — the stall is the body server's
render thread; see docs/the research report.) The sim's own camera feed is the duck's *first-person*
head camera only, as raw UYVY over a TCP socket — there is no 3rd-person stream to grab.

We don't capture the screen. We render the 3rd-person shot ourselves, offscreen, in this separate
process: load the same gallery scene, read the live duck's pose from the running body server
(`op:"read"` over TCP — trunk position, IMU quaternion, joint angles), drive our own copy of the
model to that pose, render a free "hero" camera that follows the duck, and pipe frames straight into
ffmpeg's VideoToolbox hardware encoder. No viewer window and no ScreenCaptureKit, so neither
contention mechanism fires and the duck keeps walking while we film it.

Run the sim headless so nothing renders the onscreen viewer, drive the duck as usual, then film:

    DUCK_SIM_VIEWER=0 DUCK_SIM_SCENE=gallery scripts/duck-sim      # (then run explore / drive)
    python scripts/gallery/record_gallery.py --out demo.mp4 --duration 30

Or log the pose now and film it afterwards. Logging only reads the body server (no render, no
encode), and a replay can be re-rendered with any camera and any window, without re-running the sim:

    python scripts/gallery/record_gallery.py --log-poses run.jsonl --duration 300
    python scripts/gallery/record_gallery.py --replay run.jsonl --camera outward --out demo.mp4
    python scripts/gallery/record_gallery.py --replay run.jsonl --stills 30,60,90 --out check.png

A replay prints the biggest per-frame jump of the duck's trunk, so a cut or a logging gap that
would make the duck appear to teleport shows up before anyone watches the video.

Smoke-test the render + encode path with no sim running (renders the STAND pose):

    python scripts/gallery/record_gallery.py --selftest --out selftest.mp4 --preview frame0.png

Needs mujoco + Pillow (the microduck_rl .venv has them) and ffmpeg built with VideoToolbox. The
offscreen render reuses build_scene.render()'s approach and does NOT need mjpython — only for
the onscreen viewer. Resolution is capped by the scene's offscreen buffer (1280x960).
"""

from __future__ import annotations

import argparse
import json
import math
import os
import shutil
import socket
import subprocess
import sys
import time

# `duck_ipc_proto::JOINT_NAMES` / body_server.JOINT_NAMES — the wire order every positional array is
# indexed by. 15 names: `mouth` (index 9) is on the wire but not in the walking model, so it maps to
# no joint here and is skipped. Duplicated (not imported) for the same reason the sim duplicates it:
# the sim lives in another repo and we only talk to it over the socket.
JOINT_NAMES = (
    "left_hip_yaw",
    "left_hip_roll",
    "left_hip_pitch",
    "left_knee",
    "left_ankle",
    "neck_pitch",
    "head_pitch",
    "head_yaw",
    "head_roll",
    "mouth",
    "right_hip_yaw",
    "right_hip_roll",
    "right_hip_pitch",
    "right_knee",
    "right_ankle",
)
PROTOCOL = 1  # body_server.PROTOCOL; checked in the hello handshake

_RL = os.environ.get("MICRODUCK_RL_DIR", os.path.expanduser("~/Pollen/microduck_rl"))
DEFAULT_SCENE = f"{_RL}/src/mjlab_microduck/robot/microduck/scene_gallery.xml"


def _model_index(m):
    """Map the wire pose onto our model's qpos: the free-joint base address + each named hinge's.

    By name, never by wire index: the wire carries `mouth`, the walking model does not, so a
    positional copy would be off by one from index 9. Returns (trunk_qpos_adr, {wire_index: adr}).
    """
    import mujoco

    trunk_jid = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_JOINT, "trunk_base_freejoint")
    if trunk_jid < 0:
        raise SystemExit("scene has no 'trunk_base_freejoint' joint — is this the duck scene?")
    trunk_adr = int(m.jnt_qposadr[trunk_jid])
    hinge_adr = {}
    for wire_index, name in enumerate(JOINT_NAMES):
        jid = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_JOINT, name)
        if jid >= 0:
            hinge_adr[wire_index] = int(m.jnt_qposadr[jid])
    return trunk_adr, hinge_adr


def _apply_pose(m, d, state, trunk_adr, hinge_adr):
    """Drive our model's qpos from a body_server `op:"read"` reply, then mj_forward."""
    import mujoco

    d.qpos[trunk_adr : trunk_adr + 3] = state["trunk"]
    d.qpos[trunk_adr + 3 : trunk_adr + 7] = state["imu"]["quat"]
    positions = state["positions"]
    for wire_index, adr in hinge_adr.items():
        d.qpos[adr] = positions[wire_index]
    mujoco.mj_forward(m, d)


class BodyClient:
    """A read-only second client of the body server.

    robotd keeps its own connection and drives the duck; this opens a separate one and only ever
    asks `op:"read"`, so it takes the shared world lock briefly to copy sensors out and never writes
    ctrl/torque. The server is threaded, so an extra passive reader won't disturb robotd's socket.
    """

    def __init__(self, host, port, timeout=2.0):
        self.sock = socket.create_connection((host, port), timeout=timeout)
        self.sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        self.io = self.sock.makefile("rwb")
        self._call({"op": "hello", "protocol": PROTOCOL})  # fail loudly on a protocol mismatch

    def _call(self, request):
        self.io.write((json.dumps(request) + "\n").encode())
        self.io.flush()
        line = self.io.readline()
        if not line:
            raise ConnectionError("body server closed the connection")
        answer = json.loads(line)
        if "error" in answer:
            raise RuntimeError(f"body server: {answer['error']}")
        return answer

    def read(self):
        return self._call({"op": "read"})

    def close(self):
        try:
            self.io.close()
            self.sock.close()
        except OSError:
            pass


class CameraRig:
    """The 3rd-person camera, one of three:

    - ``follow``: a fixed orbit offset around the duck — it stays dead centre in frame, so on its
      own it reads as walking in place while the room slides past.
    - ``fixed``: never moves; the duck walks through the frame (and can walk out of it).
    - ``outward``: stands on the room-centre side of the duck and looks *out* past it at the wall,
      turning to keep the duck's bearing from the centre. Walking up to a painting puts the
      painting in frame behind the duck. In a round room the camera always stays inside the wall.

    ``smooth`` (seconds) lags the aim behind the duck, which takes the gait's bob out of the shot
    and lets the duck move across the frame before the camera catches up.
    """

    def __init__(self, args):
        self.args = args
        self.look = None
        self.azimuth = args.azimuth

    def update(self, m, trunk, dt):
        import mujoco

        a = self.args
        target = [float(trunk[0]), float(trunk[1]), float(trunk[2]) + a.lookat_z]
        if a.camera == "fixed":
            look = list(a.fixed_lookat)
        else:
            first = self.look is None
            k = 1.0 if first or a.smooth <= 0 else 1.0 - math.exp(-dt / a.smooth)
            if first:
                self.look = target
            else:
                self.look = [
                    cur + (want - cur) * k for cur, want in zip(self.look, target, strict=True)
                ]
            look = self.look
            # Near the middle the bearing is noise, so hold the last one. The first frame snaps to
            # it: starting from the default azimuth could put the camera outside the wall.
            if a.camera == "outward" and math.hypot(look[0], look[1]) > 0.4:
                want = math.degrees(math.atan2(look[1], look[0]))
                ka = 1.0
                if not first and a.smooth_azimuth > 0:
                    ka = 1.0 - math.exp(-dt / a.smooth_azimuth)
                self.azimuth += ((want - self.azimuth + 180.0) % 360.0 - 180.0) * ka
        cam = mujoco.MjvCamera()
        mujoco.mjv_defaultFreeCamera(m, cam)
        cam.lookat[:] = look
        cam.distance = a.distance
        cam.azimuth = self.azimuth
        cam.elevation = a.elevation
        return cam


def _ffmpeg(out, w, h, fps, encoder, bitrate, wallclock=True):
    """Encode raw RGB frames from stdin with the hardware encoder (no screen capture involved).

    Live, timestamps come from the wall clock and the output is constant-rate, so the video plays
    back at real-time speed even when the offscreen render can't keep up with `fps` (it rendered
    ~20 fps at 1280x720 here) — frames are duplicated to fill rather than the duck appearing to move
    too fast. A replay renders every frame at its exact time, so it uses a plain fixed input rate.
    """
    if shutil.which("ffmpeg") is None:
        raise SystemExit("ffmpeg not found on PATH")
    timing = ["-use_wallclock_as_timestamps", "1"] if wallclock else ["-framerate", str(fps)]
    cmd = [
        "ffmpeg",
        "-y",
        "-loglevel",
        "error",
        *timing,
        "-f",
        "rawvideo",
        "-pixel_format",
        "rgb24",
        "-video_size",
        f"{w}x{h}",
        "-i",
        "-",
        "-r",
        str(fps),
        "-fps_mode",
        "cfr",
        "-c:v",
        encoder,
        "-b:v",
        bitrate,
        "-pix_fmt",
        "yuv420p",
        "-movflags",
        "+faststart",
        out,
    ]
    return subprocess.Popen(cmd, stdin=subprocess.PIPE)


def run(args):
    import mujoco

    m = mujoco.MjModel.from_xml_path(args.scene)
    d = mujoco.MjData(m)
    trunk_adr, hinge_adr = _model_index(m)
    renderer = mujoco.Renderer(m, args.height, args.width)

    client = None
    if args.selftest:
        # No sim: hold the STAND keyframe at the origin (the pose build_scene.render() previews).
        names = [mujoco.mj_id2name(m, mujoco.mjtObj.mjOBJ_KEY, i) for i in range(m.nkey)]
        d.qpos[:] = m.key_qpos[names.index("STAND")]
        mujoco.mj_forward(m, d)
    else:
        client = BodyClient(args.host, args.port)

    proc = _ffmpeg(args.out, args.width, args.height, args.fps, args.encoder, args.bitrate)

    rig = CameraRig(args)
    period = 1.0 / args.fps
    deadline = args.duration if args.duration > 0 else float("inf")
    start = time.perf_counter()
    last = start
    frames = 0
    preview_saved = False
    try:
        while time.perf_counter() - start < deadline:
            tick = time.perf_counter()
            if client is not None:
                _apply_pose(m, d, client.read(), trunk_adr, hinge_adr)
                trunk = d.qpos[trunk_adr : trunk_adr + 3]
            else:
                trunk = [0.0, 0.0, 0.0]
            renderer.update_scene(d, rig.update(m, trunk, max(tick - last, 1e-3)))
            last = tick
            frame = renderer.render()  # (h, w, 3) uint8 RGB
            if args.preview and not preview_saved:
                from PIL import Image

                Image.fromarray(frame).save(args.preview)
                preview_saved = True
                print("saved preview frame", args.preview, flush=True)
            try:
                proc.stdin.write(frame.tobytes())
            except BrokenPipeError:
                print("ffmpeg exited early; stopping", file=sys.stderr)
                break
            frames += 1
            slack = period - (
                time.perf_counter() - tick
            )  # cap the loop at target fps (ffmpeg owns timing)
            if slack > 0:
                time.sleep(slack)
    except KeyboardInterrupt:
        pass
    except (ConnectionError, RuntimeError, OSError) as err:
        print(f"lost the body server ({err}); stopping", file=sys.stderr)
    finally:
        if client is not None:
            client.close()
        if proc.stdin is not None:
            proc.stdin.close()
        proc.wait()
    elapsed = max(time.perf_counter() - start, 1e-6)
    print(
        f"wrote {args.out}: {frames} frames in {elapsed:.1f}s ({frames / elapsed:.1f} fps actual)"
    )


def log_poses(args):
    """Log the live pose to JSONL at `fps` — no render, no encode, so it costs the sim ~nothing.

    Each line is ``{"t": <unix seconds>, "trunk": [...], "quat": [...], "positions": [...]}``; the
    wall-clock ``t`` lines the log up with anything else stamped in real time (narration, say).
    """
    client = BodyClient(args.host, args.port)
    period = 1.0 / args.fps
    deadline = args.duration if args.duration > 0 else float("inf")
    start = time.perf_counter()
    rows = 0
    with open(args.log_poses, "w") as f:
        try:
            while time.perf_counter() - start < deadline:
                tick = time.perf_counter()
                s = client.read()
                row = {
                    "t": time.time(),
                    "trunk": s["trunk"],
                    "quat": s["imu"]["quat"],
                    "positions": s["positions"],
                }
                f.write(json.dumps(row) + "\n")
                rows += 1
                if rows % args.fps == 0:
                    f.flush()
                slack = period - (time.perf_counter() - tick)
                if slack > 0:
                    time.sleep(slack)
        except KeyboardInterrupt:
            pass
        except (ConnectionError, RuntimeError, OSError) as err:
            print(f"lost the body server ({err}); stopping", file=sys.stderr)
        finally:
            client.close()
    print(f"logged {rows} poses in {time.perf_counter() - start:.1f}s to {args.log_poses}")


def _lerp_pose(a, b, u):
    """Blend two logged poses: lerp position and joints, normalised lerp of the quaternion."""
    qa, qb = a["quat"], b["quat"]
    if sum(x * y for x, y in zip(qa, qb, strict=True)) < 0:  # same rotation, shortest way round
        qb = [-v for v in qb]
    q = [x + (y - x) * u for x, y in zip(qa, qb, strict=True)]
    norm = math.sqrt(sum(v * v for v in q)) or 1.0
    return {
        "trunk": [x + (y - x) * u for x, y in zip(a["trunk"], b["trunk"], strict=True)],
        "imu": {"quat": [v / norm for v in q]},
        "positions": [x + (y - x) * u for x, y in zip(a["positions"], b["positions"], strict=True)],
    }


def replay(args):
    """Render a logged run offline: every frame at its exact time, any camera, any window."""
    import mujoco

    with open(args.replay) as f:
        rows = [json.loads(line) for line in f if line.strip()]
    if len(rows) < 2:
        raise SystemExit(f"{args.replay}: need at least two logged poses")
    t0 = rows[0]["t"]
    span = rows[-1]["t"] - t0
    gaps = [b["t"] - a["t"] for a, b in zip(rows, rows[1:], strict=False)]
    print(
        f"log: {len(rows)} poses over {span:.1f}s, starts at unix {t0:.3f}, "
        f"widest gap {max(gaps):.2f}s"
    )

    m = mujoco.MjModel.from_xml_path(args.scene)
    m.vis.global_.fovy = args.fovy
    d = mujoco.MjData(m)
    trunk_adr, hinge_adr = _model_index(m)
    renderer = mujoco.Renderer(m, args.height, args.width)
    rig = CameraRig(args)

    start = args.start
    end = args.end if args.end > 0 else span
    step = args.speed / args.fps  # log seconds per output frame
    stills = sorted(float(s) for s in args.stills.split(",")) if args.stills else []
    if stills:
        # Step the camera through every frame up to the last still, rendering only at the stills,
        # so a still shows exactly what that moment of the video would.
        end = stills[-1] + step
    if args.frame_times:
        # An explicit log second for every output frame: a speed ramp (play the pauses fast).
        # Time only ever runs forward, so unlike a cut the duck never jumps.
        with open(args.frame_times) as f:
            times = [float(t) for t in json.load(f)]
    else:
        times = [start + k * step for k in range(int((end - start) / step))]
    pending = list(stills)
    proc = None
    if not stills:
        proc = _ffmpeg(
            args.out, args.width, args.height, args.fps, args.encoder, args.bitrate, wallclock=False
        )

    i = 0
    prev_trunk, worst, worst_at = None, 0.0, 0.0
    try:
        for t in times:
            while i + 2 < len(rows) and rows[i + 1]["t"] - t0 <= t:
                i += 1
            a, b = rows[i], rows[i + 1]
            u = min(max((t - (a["t"] - t0)) / max(b["t"] - a["t"], 1e-6), 0.0), 1.0)
            _apply_pose(m, d, _lerp_pose(a, b, u), trunk_adr, hinge_adr)
            trunk = d.qpos[trunk_adr : trunk_adr + 3].copy()
            if prev_trunk is not None and not stills:
                jump = math.hypot(trunk[0] - prev_trunk[0], trunk[1] - prev_trunk[1])
                if jump > worst:
                    worst, worst_at = jump, t
            prev_trunk = trunk
            cam = rig.update(m, trunk, 1.0 / args.fps)  # smooth in screen time, whatever the speed
            if stills:
                if not pending or t + step / 2 < pending[0]:
                    continue
                from PIL import Image

                renderer.update_scene(d, cam)
                stem, ext = os.path.splitext(args.out)
                path = f"{stem}_t{pending.pop(0):g}{ext or '.png'}"
                Image.fromarray(renderer.render()).save(path)
                print("saved", path)
            else:
                renderer.update_scene(d, cam)
                proc.stdin.write(renderer.render().tobytes())
    finally:
        if proc is not None:
            proc.stdin.close()
            proc.wait()
    if not stills:
        # The duck walks ~0.3 m/s, so ~1 cm a frame; anything near 5 cm is a cut or a dropout.
        print(
            f"wrote {args.out}: {len(times)} frames ({len(times) / args.fps:.1f}s); biggest "
            f"step {worst * 100:.1f} cm/frame at t={worst_at:.1f}s"
        )


def main():
    p = argparse.ArgumentParser(description=(__doc__ or "").split("\n")[0])
    p.add_argument("--out", default="gallery_demo.mp4", help="output video path")
    p.add_argument("--scene", default=DEFAULT_SCENE, help="gallery scene .xml")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=7801, help="body server port for duck 'a'")
    p.add_argument("--fps", type=int, default=30)
    p.add_argument("--duration", type=float, default=0.0, help="seconds; 0 = until Ctrl-C")
    p.add_argument("--width", type=int, default=1280, help="<= scene offwidth (1280)")
    p.add_argument("--height", type=int, default=720, help="<= scene offheight (960)")
    p.add_argument("--distance", type=float, default=1.9, help="free-camera distance to the duck")
    p.add_argument("--azimuth", type=float, default=90.0)
    p.add_argument("--elevation", type=float, default=-8.0)
    p.add_argument("--lookat-z", dest="lookat_z", type=float, default=0.22, help="aim height")
    p.add_argument("--camera", choices=("follow", "fixed", "outward"), default="follow")
    p.add_argument("--smooth", type=float, default=0.0, help="aim lag, seconds (0 = rigid)")
    p.add_argument(
        "--smooth-azimuth",
        dest="smooth_azimuth",
        type=float,
        default=2.5,
        help="outward camera: how slowly it swings round after the duck, seconds",
    )
    p.add_argument(
        "--fixed-lookat",
        dest="fixed_lookat",
        type=float,
        nargs=3,
        default=(0.0, 0.0, 0.3),
        metavar=("X", "Y", "Z"),
        help="fixed camera: the point it looks at",
    )
    p.add_argument("--fovy", type=float, default=45.0, help="replay: vertical field of view")
    p.add_argument("--encoder", default="h264_videotoolbox")
    p.add_argument("--bitrate", default="12M")
    p.add_argument("--preview", default="", help="also save the first frame as a PNG here")
    p.add_argument(
        "--selftest", action="store_true", help="no sim: render the STAND pose (smoke test)"
    )
    p.add_argument("--log-poses", dest="log_poses", default="", help="log the pose here; no video")
    p.add_argument("--replay", default="", help="render this pose log instead of the live duck")
    p.add_argument("--start", type=float, default=0.0, help="replay: from this log second")
    p.add_argument("--end", type=float, default=0.0, help="replay: to this log second (0 = end)")
    p.add_argument("--speed", type=float, default=1.0, help="replay: playback speed")
    p.add_argument("--stills", default="", help="replay: save PNGs at these log seconds instead")
    p.add_argument(
        "--frame-times",
        dest="frame_times",
        default="",
        help="replay: JSON list of the log second to show on each output frame (a speed ramp)",
    )
    args = p.parse_args()
    if args.selftest and args.duration == 0.0:
        args.duration = 2.0  # a short clip is enough to prove the pipe
    if args.log_poses:
        log_poses(args)
    elif args.replay:
        replay(args)
    else:
        run(args)


if __name__ == "__main__":
    main()
