"""Record a 3rd-person "gallery" shot of the live Microduck — headless, no onscreen viewer, no
screen capture.

Why this exists. Screen-recording the MuJoCo viewer window (OBS, QuickTime, ScreenCaptureKit)
competes with the sim for the GPU and the macOS compositor and stalls it: the body server steps
physics, presents the onscreen viewer and reads back the camera on one serial thread, so a recorder
that slows the present slows physics, the walk policy falls behind real time, and the duck stops.
(robotd's 500 ms deadman is wall-clock and is *not* the coupling — the stall is the body server's
render thread; see docs/the research report.) The sim's own camera feed is the duck's *first-person*
head camera only, as raw UYVY over a TCP socket — there is no 3rd-person stream to grab.

So we do not capture the screen. We render the 3rd-person shot ourselves, offscreen, in this separate
process: load the same gallery scene, read the live duck's pose from the running body server
(`op:"read"` over TCP — trunk position, IMU quaternion, joint angles), drive our own copy of the
model to that pose, render a free "hero" camera that follows the duck, and pipe frames straight into
ffmpeg's VideoToolbox hardware encoder. No viewer window and no ScreenCaptureKit, so neither
contention mechanism fires and the duck keeps walking while we film it.

Run the sim headless so nothing renders the onscreen viewer, drive the duck as usual, then film:

    DUCK_SIM_VIEWER=0 DUCK_SIM_SCENE=gallery scripts/duck-sim      # (then run explore / drive)
    python scripts/gallery/record_gallery.py --out demo.mp4 --duration 30

Smoke-test the render + encode path with no sim running (renders the STAND pose):

    python scripts/gallery/record_gallery.py --selftest --out selftest.mp4 --preview frame0.png

Needs mujoco + Pillow (the microduck_rl .venv has them) and ffmpeg built with VideoToolbox. The
offscreen render reuses build_scene.render()'s approach and does NOT need mjpython — that is only for
the onscreen viewer. Resolution is capped by the scene's offscreen buffer (offwidth/offheight, 1280x960).
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path

# `duck_ipc_proto::JOINT_NAMES` / body_server.JOINT_NAMES — the wire order every positional array is
# indexed by. 15 names: `mouth` (index 9) is on the wire but not in the walking model, so it maps to
# no joint here and is skipped. Duplicated (not imported) for the same reason the sim duplicates it:
# the sim lives in another repo and we only talk to it over the socket.
JOINT_NAMES = (
    "left_hip_yaw", "left_hip_roll", "left_hip_pitch", "left_knee", "left_ankle",
    "neck_pitch", "head_pitch", "head_yaw", "head_roll", "mouth",
    "right_hip_yaw", "right_hip_roll", "right_hip_pitch", "right_knee", "right_ankle",
)
PROTOCOL = 1  # body_server.PROTOCOL; checked in the hello handshake

_RL = os.environ.get("MICRODUCK_RL_DIR", os.path.expanduser("~/Pollen/microduck_rl"))
DEFAULT_SCENE = f"{_RL}/src/mjlab_microduck/robot/microduck/scene_gallery.xml"


def _model_index(m):
    """Map the wire pose onto our model's qpos: the free-joint base address + each named hinge's.

    By name, never by wire index: the wire carries `mouth`, the walking model does not, so a
    positional copy would be off by one from index 9 on. Returns (trunk_qpos_adr, {wire_index: adr}).
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
    ctrl/torque. The server is threaded, so an extra passive reader does not disturb robotd's socket.
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


def _make_camera(m, args, lookat):
    """A free camera that looks at `lookat` from a fixed orbit offset (so it follows the duck)."""
    import mujoco

    cam = mujoco.MjvCamera()
    mujoco.mjv_defaultFreeCamera(m, cam)
    cam.lookat[:] = lookat
    cam.distance = args.distance
    cam.azimuth = args.azimuth
    cam.elevation = args.elevation
    return cam


def _ffmpeg(out, w, h, fps, encoder, bitrate):
    """Encode raw RGB frames from stdin with the hardware encoder (no screen capture involved).

    Timestamps come from the wall clock and the output is constant-rate, so the video plays back at
    real-time speed even when the offscreen render can't keep up with `fps` (it rendered ~20 fps at
    1280x720 here) — frames are duplicated to fill rather than the duck appearing to move too fast.
    """
    if shutil.which("ffmpeg") is None:
        raise SystemExit("ffmpeg not found on PATH")
    cmd = [
        "ffmpeg", "-y",
        "-use_wallclock_as_timestamps", "1",
        "-f", "rawvideo", "-pixel_format", "rgb24", "-video_size", f"{w}x{h}", "-i", "-",
        "-r", str(fps), "-fps_mode", "cfr",
        "-c:v", encoder, "-b:v", bitrate, "-pix_fmt", "yuv420p", "-movflags", "+faststart",
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
        # No sim: hold the STAND keyframe at the origin — the same pose build_scene.render() previews.
        names = [mujoco.mj_id2name(m, mujoco.mjtObj.mjOBJ_KEY, i) for i in range(m.nkey)]
        d.qpos[:] = m.key_qpos[names.index("STAND")]
        mujoco.mj_forward(m, d)
    else:
        client = BodyClient(args.host, args.port)

    proc = _ffmpeg(args.out, args.width, args.height, args.fps, args.encoder, args.bitrate)

    period = 1.0 / args.fps
    deadline = args.duration if args.duration > 0 else float("inf")
    start = time.perf_counter()
    frames = 0
    preview_saved = False
    try:
        while time.perf_counter() - start < deadline:
            tick = time.perf_counter()
            if client is not None:
                _apply_pose(m, d, client.read(), trunk_adr, hinge_adr)
                lookat = [float(v) for v in d.qpos[trunk_adr : trunk_adr + 3]]
                lookat[2] += args.lookat_z  # aim at the body, not the floor
            else:
                lookat = [0.0, 0.0, args.lookat_z]
            renderer.update_scene(d, _make_camera(m, args, lookat))
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
            slack = period - (time.perf_counter() - tick)  # cap the loop at target fps (ffmpeg owns timing)
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
    print(f"wrote {args.out}: {frames} frames in {elapsed:.1f}s ({frames / elapsed:.1f} fps actual)")


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
    p.add_argument("--encoder", default="h264_videotoolbox")
    p.add_argument("--bitrate", default="12M")
    p.add_argument("--preview", default="", help="also save the first frame as a PNG here")
    p.add_argument("--selftest", action="store_true", help="no sim: render the STAND pose (smoke test)")
    args = p.parse_args()
    if args.selftest and args.duration == 0.0:
        args.duration = 2.0  # a short clip is enough to prove the pipe
    run(args)


if __name__ == "__main__":
    main()
