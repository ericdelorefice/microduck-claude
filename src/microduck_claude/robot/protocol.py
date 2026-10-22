"""duck-ipc-proto method names and constants, in one place.

These mirror the Microduck `duck-ipc-proto` contract (a Rust crate; the serde types
are the contract — there is no published schema). Verified against the live repo at
release 0.17.x. Centralised so they are the single place to update as the contract
evolves. Wire format: JSON-RPC 2.0, one object per line (NDJSON), over a Unix socket;
a message is a NOTIFICATION when it has no ``id`` and a REQUEST when it does. Param
field names are snake_case and param objects reject unknown fields.
"""

from __future__ import annotations

# Handshake (informational; a version mismatch is reported, not refused).
HELLO = "hello"  # {api_version} -> {api_version, daemon_version, revision}
API_VERSION = 44

# Continuous control — JSON-RPC NOTIFICATIONS (no id), last-writer-wins.
ROBOT_MOVE = "robot.move"  # {vx, vy, vyaw}
ROBOT_HEAD = "robot.head"  # {neck_pitch, head_pitch, head_yaw, head_roll}
ROBOT_POSE = "robot.pose"  # {z, roll, pitch, active}
ROBOT_MOUTH = "robot.mouth"  # {open}

# Discrete control — JSON-RPC REQUESTS (carry an id, return a result).
ROBOT_STOP = "robot.stop"  # (no params) -> IntentResult
ROBOT_LOOK = "robot.look"  # {x, y, z, neck_pitch} -> LookResult{head, clamped}
ROBOT_DO = "robot.do"  # {skill} -> IntentResult{accepted, reason}
ROBOT_SOUND = "robot.sound"  # {tag, hold?} -> IntentResult
ROBOT_SUBSCRIBE = "robot.subscribe"  # {hz?} -> SubscribeResult; then robot.state notifications
ROBOT_POLICIES = "robot.policies"  # (no params) -> PoliciesResult{skills, slots, ...}
ROBOT_HEALTH = "robot.health"  # (no params) -> HealthResult{battery: {volts, percent}?, ...}
ROBOT_INIT = "robot.init"  # stand to home -> IntentResult
ROBOT_RELAX = "robot.relax"  # cut torque -> IntentResult

# Inbound notifications (received, not sent).
ROBOT_STATE = "robot.state"  # {t, move, head, joints, imu, ...}; battery is NOT here

# Local duck-sim control socket. scripts/duck-sim binds ~/.cache/duck-sim/duck-a.sock
# (with a convenience symlink ~/.cache/duck-sim/duck.sock -> it). Override with the
# MICRODUCK_ROBOT_SOCKET environment variable.
DEFAULT_SIM_SOCKET = "~/.cache/duck-sim/duck-a.sock"
