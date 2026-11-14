"""Score the duck's moves on the sim against ground truth: turns, walking straight, stopping.

The moves under test only use what the robot itself reports (robotd's heading, tofd's
distance). This script additionally reads the simulator's ground truth (the body server's
`op:"read"` — trunk position and orientation) purely to grade them, so it is a sim-only tool.

    # start the gallery sim with the duck in the middle, then:
    python scripts/bench/movement_bench.py --mode closed --out closed.json
    python scripts/bench/movement_bench.py --mode timed  --out timed.json   # the old timed moves

Restart the sim between runs so each mode starts from the same place. Run it from the project
venv (it imports microduck_claude); the sim must be running headless or with its viewer.
"""

from __future__ import annotations

import argparse
import json
import math
import socket
import statistics
import time

from microduck_claude.robot import build_robot
from microduck_claude.robot.motion import WALK_VX, WALK_YAW_TRIM, turn_by, turn_command, walk

WALL_R = 3.55  # inner face of the gallery drum (build_scene.py: R - WALL_T)
TURNS = (30.0, -30.0, 60.0, -60.0, 90.0, -90.0, 150.0, -150.0)


class Truth:
    """The sim's ground truth, read straight from the body server (never seen by the moves)."""

    def __init__(self, host: str, port: int) -> None:
        self._sock = socket.create_connection((host, port), timeout=3)
        self._io = self._sock.makefile("rwb")

    def read(self) -> tuple[float, float, float]:
        self._io.write(b'{"op":"read"}\n')
        self._io.flush()
        d = json.loads(self._io.readline())
        x, y, _ = d["trunk"]
        w, qx, qy, qz = d["imu"]["quat"]
        return x, y, math.atan2(2 * (w * qz + qx * qy), 1 - 2 * (qy * qy + qz * qz))

    def wall_ahead(self) -> float:
        x, y, yaw = self.read()
        ux, uy = math.cos(yaw), math.sin(yaw)
        b = x * ux + y * uy
        return -b + math.sqrt(max(b * b - (x * x + y * y - WALL_R**2), 0.0))


def _wrap_deg(a: float) -> float:
    return (a + 180.0) % 360.0 - 180.0


def bench_turns(robot, truth: Truth, mode: str) -> list[dict]:
    rows = []
    for want in TURNS:
        time.sleep(0.6)
        _, _, a0 = truth.read()
        t0 = time.monotonic()
        if mode == "closed":
            reported = turn_by(robot, want).turned_deg
        else:
            vx, vyaw, duration = turn_command(want)
            robot.drive_for(vx, 0.0, vyaw, duration=duration)
            reported = None
        took = time.monotonic() - t0
        time.sleep(0.8)
        _, _, a1 = truth.read()
        got = _wrap_deg(math.degrees(a1 - a0))
        if abs(want) > 120 and abs(got - want) > 180:  # the long way round reads as wrapped
            got += 360.0 if want > 0 else -360.0
        rows.append(
            {
                "want": want,
                "got": round(got, 1),
                "error": round(got - want, 1),
                "reported": None if reported is None else round(reported, 1),
                "s": round(took, 2),
            }
        )
        print(
            f"  turn {want:+6.0f}  got {got:+7.1f}  error {got - want:+6.1f}  in {took:4.1f}s",
            flush=True,
        )
    return rows


def bench_walk(robot, truth: Truth, mode: str) -> dict:
    time.sleep(0.6)
    x0, y0, a0 = truth.read()
    for _leg in range(2):
        if mode == "closed":
            walk(robot, 2.5, stop_at=0.0)  # straightness only: no distance stop here
        else:
            robot.drive_for(WALK_VX, 0.0, WALK_YAW_TRIM, duration=2.5)
    time.sleep(0.8)
    x1, y1, a1 = truth.read()
    dx, dy = x1 - x0, y1 - y0
    fwd = dx * math.cos(a0) + dy * math.sin(a0)
    side = -dx * math.sin(a0) + dy * math.cos(a0)
    row = {
        "forward_m": round(fwd, 2),
        "sideways_m": round(side, 2),
        "heading_change": round(_wrap_deg(math.degrees(a1 - a0)), 1),
    }
    print(
        f"  walk 2x2.5s  forward {fwd:.2f} m  sideways {side:+.2f} m  "
        f"heading {row['heading_change']:+.1f}",
        flush=True,
    )
    return row


def bench_approach(robot, truth: Truth, mode: str) -> dict:
    # Setup (not graded, the same in both modes): face the middle of the room, so there is a
    # long walk across it to the far wall.
    x, y, yaw = truth.read()
    turn_by(robot, _wrap_deg(math.degrees(math.atan2(-y, -x) - yaw)))
    time.sleep(0.6)
    start = truth.wall_ahead()
    t0 = time.monotonic()
    if mode == "closed":
        result = walk(robot, 24.0)
        sensed = result.range_m
    else:
        for _leg in range(8):  # the old explore: fixed legs, no idea where the wall is
            robot.drive_for(WALK_VX, 0.0, WALK_YAW_TRIM, duration=3.0)
        sensed = None
    took = time.monotonic() - t0
    time.sleep(0.8)
    end = truth.wall_ahead()
    row = {
        "start_m": round(start, 2),
        "end_m": round(end, 2),
        "sensed_m": sensed,
        "s": round(took, 1),
        "hit_wall": end < 0.15,
    }
    print(
        f"  approach  wall {start:.2f} m -> {end:.2f} m  (sensed {sensed})  "
        f"{'HIT THE WALL' if row['hit_wall'] else 'stopped clear'}",
        flush=True,
    )
    return row


def main() -> None:
    p = argparse.ArgumentParser(description=(__doc__ or "").split("\n")[0])
    p.add_argument("--mode", choices=("closed", "timed"), required=True)
    p.add_argument("--out", default="")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=7801, help="body server (ground truth)")
    args = p.parse_args()

    robot = build_robot("rpc", camera_url="")
    truth = Truth(args.host, args.port)
    time.sleep(1.0)
    print(f"mode={args.mode}  heading={robot.heading()}  range_ahead={robot.range_ahead()}")
    robot.drive_for(0.3, 0.0, 0.0, duration=1.0)  # stand up out of SIT
    robot.stop()

    print("turns:")
    turns = bench_turns(robot, truth, args.mode)
    print("walk:")
    walk_row = bench_walk(robot, truth, args.mode)
    print("approach:")
    approach = bench_approach(robot, truth, args.mode)
    robot.stop()

    errors = [abs(r["error"]) for r in turns]
    summary = {
        "turn_mean_abs_error": round(statistics.mean(errors), 1),
        "turn_worst_error": round(max(errors), 1),
        "turns_within_10deg": sum(e <= 10 for e in errors),
        "turn_mean_s": round(statistics.mean(r["s"] for r in turns), 2),
        "walk_sideways_m": walk_row["sideways_m"],
        "walk_heading_change": walk_row["heading_change"],
        "approach_end_m": approach["end_m"],
        "approach_hit_wall": approach["hit_wall"],
    }
    print("summary:", json.dumps(summary))
    if args.out:
        with open(args.out, "w") as f:
            json.dump(
                {
                    "mode": args.mode,
                    "summary": summary,
                    "turns": turns,
                    "walk": walk_row,
                    "approach": approach,
                },
                f,
                indent=1,
            )


if __name__ == "__main__":
    main()
