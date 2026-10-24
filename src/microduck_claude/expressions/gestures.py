"""The gesture vocabulary: high-level expressions → robot intents.

Each gesture is a small, named routine of :class:`RobotInterface` calls. The model
picks a gesture by name (the ``perform_gesture`` tool constrains it to this set);
the expression layer owns *how* it is actuated, so swapping FakeRobot for a real
robot needs no change here. Vocabulary is inspired by Pollen's `microduck_emotions`.

Angle conventions are nominal for Milestone 1 (the FakeRobot only records them);
they get tuned against the real body in Milestone 2.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from ..robot.interface import RobotInterface

GestureFn = Callable[[RobotInterface], None]


@dataclass(frozen=True)
class Gesture:
    """A named expression: either a primitive ``run`` routine or a sim ``skill``.

    A ``skill`` gesture is a trained behaviour invoked via ``robot.do``; it only
    happens if the robot accepts it (otherwise the duck admits it couldn't).
    """

    name: str
    description: str
    run: GestureFn | None = None
    skill: str | None = None
    consequential: bool = False  # a dynamic whole-body trick: confirm even under trust


def _nod(robot: RobotInterface) -> None:
    robot.set_head(head_pitch=0.3)
    robot.set_head(head_pitch=-0.15)
    robot.set_head()


def _shake(robot: RobotInterface) -> None:
    robot.set_head(head_yaw=0.4)
    robot.set_head(head_yaw=-0.4)
    robot.set_head()


def _tilt(robot: RobotInterface) -> None:
    robot.set_head(head_roll=0.35)


def _look_left(robot: RobotInterface) -> None:
    robot.set_head(head_yaw=0.5)


def _look_right(robot: RobotInterface) -> None:
    robot.set_head(head_yaw=-0.5)


def _look_up(robot: RobotInterface) -> None:
    robot.set_head(head_pitch=-0.4)


def _look_down(robot: RobotInterface) -> None:
    robot.set_head(head_pitch=0.4)


def _recenter(robot: RobotInterface) -> None:
    robot.set_head()


def _greet(robot: RobotInterface) -> None:
    robot.set_head()
    robot.play_sound("greet")


def _bow(robot: RobotInterface) -> None:
    robot.set_pose(pitch=0.4)
    robot.set_pose()
    robot.play_sound("greet")


def _happy(robot: RobotInterface) -> None:
    robot.set_pose(roll=0.2)
    robot.set_pose(roll=-0.2)
    robot.set_pose()
    robot.play_sound("wheee")


def _thinking(robot: RobotInterface) -> None:
    robot.set_head(head_roll=0.3, head_pitch=-0.1)
    robot.play_sound("inquire")


def _confused(robot: RobotInterface) -> None:
    robot.set_head(head_roll=0.3)
    robot.set_head(head_roll=-0.2, head_yaw=0.2)
    robot.play_sound("inquire")


def _dance(robot: RobotInterface) -> None:
    robot.set_pose(roll=0.25)
    robot.set_pose(roll=-0.25)
    robot.set_pose(roll=0.25)
    robot.set_pose()
    robot.play_sound("wheee")


def _sad(robot: RobotInterface) -> None:
    robot.set_head(head_pitch=0.4)  # droop
    robot.set_pose(z=-0.02)
    robot.play_sound("coo")


def _angry(robot: RobotInterface) -> None:
    robot.set_pose(pitch=0.3)  # lean in
    robot.set_head(head_yaw=0.3)
    robot.set_head(head_yaw=-0.3)
    robot.set_head()
    robot.play_sound("alarm")


def _surprised(robot: RobotInterface) -> None:
    robot.set_head(head_pitch=-0.4)  # jerk up
    robot.set_pose(z=0.03)
    robot.set_pose()
    robot.play_sound("inquire")


def _scared(robot: RobotInterface) -> None:
    robot.set_pose(z=-0.03)  # shrink
    robot.set_head(head_pitch=-0.2, head_roll=0.2)
    robot.play_sound("alarm")


def _sleepy(robot: RobotInterface) -> None:
    robot.set_head(head_pitch=0.3, head_roll=0.3)
    robot.set_mouth(0.2)
    robot.set_mouth(0.0)
    robot.play_sound("coo")


def _excited(robot: RobotInterface) -> None:
    robot.set_pose(roll=0.3)
    robot.set_pose(roll=-0.3)
    robot.set_pose(roll=0.3)
    robot.set_pose()
    robot.play_sound("wheee")


def _proud(robot: RobotInterface) -> None:
    robot.set_pose(z=0.03)  # puff up tall
    robot.set_head(head_pitch=-0.2)
    robot.play_sound("chirp")


def _shy(robot: RobotInterface) -> None:
    robot.set_head(head_yaw=0.4, head_pitch=0.2)  # turn away and down
    robot.play_sound("coo")


_ALL: tuple[Gesture, ...] = (
    Gesture("nod", "Dip the head and return — 'yes' / acknowledgement.", _nod),
    Gesture("shake", "Swivel the head side to side — 'no' / disagreement.", _shake),
    Gesture("tilt", "Tilt the head — curiosity.", _tilt),
    Gesture("look_left", "Turn the head to the left.", _look_left),
    Gesture("look_right", "Turn the head to the right.", _look_right),
    Gesture("look_up", "Raise the gaze upward.", _look_up),
    Gesture("look_down", "Lower the gaze downward.", _look_down),
    Gesture("recenter", "Return the head to neutral, facing forward.", _recenter),
    Gesture("greet", "Face forward and chirp a greeting.", _greet),
    Gesture("bow", "Dip the body forward in a little bow, with a greeting sound.", _bow),
    Gesture("happy", "Wiggle side to side with a cheerful sound.", _happy),
    Gesture("thinking", "Tilt and give an inquisitive chirp while considering.", _thinking),
    Gesture("confused", "Tilt and glance about with a puzzled chirp.", _confused),
    Gesture("dance", "A short celebratory wiggle with a sound.", _dance),
    Gesture("sit", "Sit down or stand up (needs a robot that supports it).", skill="sit_toggle"),
    Gesture(
        "roulade",
        "A forward roll / somersault — a real trained trick.",
        skill="roulade",
        consequential=True,
    ),
    Gesture(
        "kick_left",
        "A left-footed kick — a real trained trick.",
        skill="kick_left",
        consequential=True,
    ),
    Gesture(
        "kick_right",
        "A right-footed kick — a real trained trick.",
        skill="kick_right",
        consequential=True,
    ),
    Gesture("sad", "Droop the head and sink a little, with a soft sound.", _sad),
    Gesture("angry", "Lean in and shake, with an alarmed sound.", _angry),
    Gesture("surprised", "Jerk the head up and rise, with a surprised chirp.", _surprised),
    Gesture("scared", "Shrink down and back, with an alarmed sound.", _scared),
    Gesture("sleepy", "Let the head droop, with a sleepy coo.", _sleepy),
    Gesture("excited", "Bounce side to side, with an excited sound.", _excited),
    Gesture("proud", "Puff up tall, with a proud chirp.", _proud),
    Gesture("shy", "Turn the head away and down, with a shy coo.", _shy),
)

GESTURES: dict[str, Gesture] = {gesture.name: gesture for gesture in _ALL}
