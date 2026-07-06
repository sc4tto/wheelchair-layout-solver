"""Shapely geometry conversion and wheelchair footprint functions."""

from __future__ import annotations

from shapely import affinity
from shapely.geometry import Polygon, box

from .models import PolygonData, Pose, WheelchairSpec


def polygon_from_data(data: PolygonData) -> Polygon:
    """Create a valid Shapely polygon or raise a descriptive error."""

    polygon = Polygon(data.coordinates)
    if polygon.is_empty:
        raise ValueError("Polygon is empty.")
    if not polygon.is_valid:
        raise ValueError("Polygon is invalid; repair it in the CAD source.")
    if polygon.area <= 0:
        raise ValueError("Polygon has zero area.")
    return polygon


def wheelchair_local_footprint(spec: WheelchairSpec) -> Polygon:
    """Create the local rectangular wheelchair footprint.

    The local +X axis points forward and +Y points left.
    The pose reference lies at the origin before applying reference_offset_x.
    """

    footprint = box(
        -spec.length / 2,
        -spec.width / 2,
        spec.length / 2,
        spec.width / 2,
    )
    if spec.reference_offset_x:
        footprint = affinity.translate(footprint, xoff=spec.reference_offset_x)
    if spec.safety_margin:
        footprint = footprint.buffer(spec.safety_margin, join_style="mitre")
    return footprint


def footprint_at_pose(spec: WheelchairSpec, pose: Pose) -> Polygon:
    """Rotate and translate the wheelchair footprint to a world pose."""

    footprint = wheelchair_local_footprint(spec)
    footprint = affinity.rotate(footprint, pose.angle_deg, origin=(0, 0))
    return affinity.translate(footprint, xoff=pose.x, yoff=pose.y)


def exterior_coordinates(polygon: Polygon) -> list[tuple[float, float]]:
    """Return exterior XY coordinates without the repeated closing coordinate."""

    return [(float(x), float(y)) for x, y in list(polygon.exterior.coords)[:-1]]
