"""Manual path interpolation and validation."""

from __future__ import annotations

from math import ceil, hypot

from .collision import check_pose
from .models import PathCheckResult, Pose, Scene


def _shortest_angle_delta(start: float, end: float) -> float:
    return (end - start + 180.0) % 360.0 - 180.0


def interpolate_segment(
    start: Pose,
    end: Pose,
    spatial_step: float,
    angular_step_deg: float,
) -> list[Pose]:
    """Interpolate one segment with spatial and angular sampling limits."""

    distance = hypot(end.x - start.x, end.y - start.y)
    angle_delta = _shortest_angle_delta(start.angle_deg, end.angle_deg)
    step_count = max(
        1,
        ceil(distance / spatial_step),
        ceil(abs(angle_delta) / angular_step_deg),
    )

    poses: list[Pose] = []
    for index in range(step_count + 1):
        t = index / step_count
        poses.append(
            Pose(
                x=start.x + (end.x - start.x) * t,
                y=start.y + (end.y - start.y) * t,
                angle_deg=start.angle_deg + angle_delta * t,
                reverse=end.reverse if t > 0 else start.reverse,
            )
        )
    return poses


def sample_path(scene: Scene, control_poses: list[Pose]) -> list[Pose]:
    """Sample a complete control-pose path without duplicate junctions."""

    if not control_poses:
        return []
    if len(control_poses) == 1:
        return list(control_poses)

    sampled: list[Pose] = []
    for index in range(len(control_poses) - 1):
        segment = interpolate_segment(
            control_poses[index],
            control_poses[index + 1],
            scene.path_settings.spatial_step,
            scene.path_settings.angular_step_deg,
        )
        sampled.extend(segment if index == 0 else segment[1:])
    return sampled


def validate_path(scene: Scene, control_poses: list[Pose] | None = None) -> PathCheckResult:
    """Validate all sampled poses along a manual path."""

    controls = scene.manual_path if control_poses is None else control_poses
    sampled = sample_path(scene, controls)
    minimum_clearance: float | None = None

    for index, pose in enumerate(sampled):
        result = check_pose(scene, pose)
        if not result.valid:
            return PathCheckResult(
                valid=False,
                checked_pose_count=index + 1,
                first_invalid_index=index,
                first_invalid_pose=pose,
                collision_ids=result.collision_ids,
                minimum_clearance=minimum_clearance,
                sampled_path=sampled,
            )
        if result.minimum_clearance is not None:
            minimum_clearance = (
                result.minimum_clearance
                if minimum_clearance is None
                else min(minimum_clearance, result.minimum_clearance)
            )

    return PathCheckResult(
        valid=True,
        checked_pose_count=len(sampled),
        first_invalid_index=None,
        first_invalid_pose=None,
        collision_ids=[],
        minimum_clearance=minimum_clearance,
        sampled_path=sampled,
    )
