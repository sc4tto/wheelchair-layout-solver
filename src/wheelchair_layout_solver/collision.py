"""Deterministic pose collision checks."""

from __future__ import annotations

from math import inf

from shapely.geometry import Polygon  # type: ignore[import-untyped]

from .geometry import exterior_coordinates, footprint_at_pose, polygon_from_data
from .models import Pose, PoseCheckResult, Scene


def _minimum_clearance(
    footprint: Polygon,
    room: Polygon,
    obstacle_polygons: list[Polygon],
) -> float:
    distances = [footprint.distance(room.boundary)]
    distances.extend(footprint.distance(obstacle) for obstacle in obstacle_polygons)
    return float(min(distances, default=inf))


def check_pose(scene: Scene, pose: Pose) -> PoseCheckResult:
    """Check whether a wheelchair pose is inside the room and collision-free."""

    room = polygon_from_data(scene.room)
    footprint = footprint_at_pose(scene.wheelchair, pose)
    obstacle_polygons = [polygon_from_data(item.polygon) for item in scene.obstacles]

    inside_room = bool(room.covers(footprint))
    collision_ids = [
        obstacle.id
        for obstacle, polygon in zip(scene.obstacles, obstacle_polygons, strict=True)
        if footprint.intersects(polygon)
    ]
    valid = inside_room and not collision_ids
    clearance = _minimum_clearance(footprint, room, obstacle_polygons) if valid else None

    return PoseCheckResult(
        valid=valid,
        collision_ids=collision_ids,
        inside_room=inside_room,
        minimum_clearance=clearance,
        footprint=exterior_coordinates(footprint),
    )
