"""Convert inspected DXF accessibility data into semantic solver models."""

from __future__ import annotations

import math
from pathlib import Path
from typing import Final

from pydantic import Field

from wheelchair_layout_solver.models import (
    ElementSpec,
    ElementType,
    Obstacle,
    PathSettings,
    PolygonData,
    Pose,
    Scene,
    StrictModel,
    Transform,
    VariationBounds,
    WheelchairSpec,
)

from .dxf_importer import DxfEntitySummary, DxfInspection, inspect_dxf


class SemanticImportError(ValueError):
    """Raised when DXF content cannot form a valid semantic layout."""


class DxfSemanticData(StrictModel):
    """Semantic CAD layout data extracted from a DXF inspection."""

    room: PolygonData
    obstacles: list[Obstacle] = Field(default_factory=list)
    elements: list[ElementSpec] = Field(default_factory=list)
    entry: Pose
    target: Pose | None = None
    warnings: list[str] = Field(default_factory=list)


_LAYER_TO_TYPE: Final[dict[str, ElementType]] = {
    "ACC_WC": ElementType.TOILET,
    "ACC_SINK": ElementType.SINK,
    "ACC_BIDET": ElementType.BIDET,
    "ACC_DOOR": ElementType.DOOR,
    "ACC_SHOWER": ElementType.SHOWER,
}

_TYPE_ALIASES: Final[dict[str, set[str]]] = {
    "ACC_WC": {"WC", "TOILET"},
    "ACC_SINK": {"SINK", "LAVABO"},
    "ACC_BIDET": {"BIDET"},
    "ACC_DOOR": {"DOOR", "PORTA"},
    "ACC_SHOWER": {"SHOWER", "DOCCIA"},
}

_IGNORED_WARNING_LAYERS: Final[set[str]] = {"ACC_WALL", "ACC_FUNCTIONAL_AREA"}


def _require_supported_units(inspection: DxfInspection) -> None:
    if inspection.insunits != 6:
        raise SemanticImportError(
            f"Unsupported DXF units code {inspection.insunits}; "
            "only INSUNITS=6 metres are supported."
        )


def _is_closed_polygon(entity: DxfEntitySummary) -> bool:
    return (
        entity.entity_type in {"POLYLINE", "LWPOLYLINE"}
        and entity.is_closed is True
        and len(entity.vertices) >= 3
    )


def _polygon_data_from_vertices(
    vertices: list[tuple[float, float]],
    *,
    message: str,
) -> PolygonData:
    if len(vertices) < 3:
        raise SemanticImportError(message)
    try:
        return PolygonData(coordinates=vertices)
    except ValueError as exc:
        raise SemanticImportError(message) from exc


def _required_id(entity: DxfEntitySummary) -> str:
    raw_id = entity.attributes.get("ID")
    if raw_id is None:
        raise SemanticImportError(f"Element on layer {entity.layer} is missing required ID.")

    element_id = raw_id.strip()
    if not element_id:
        raise SemanticImportError(f"Element on layer {entity.layer} has an empty ID.")

    return element_id


def _optional_id(entity: DxfEntitySummary, *, fallback_prefix: str) -> str:
    raw_id = entity.attributes.get("ID")
    if raw_id is None:
        return f"{fallback_prefix}_{entity.handle}"

    object_id = raw_id.strip()
    if not object_id:
        raise SemanticImportError(f"Object on layer {entity.layer} has an empty ID.")

    return object_id


def _validate_type_alias(entity: DxfEntitySummary, *, element_id: str) -> None:
    raw_type = entity.attributes.get("TYPE")
    if raw_type is None:
        return

    normalized = raw_type.strip().upper()
    if normalized not in _TYPE_ALIASES[entity.layer]:
        raise SemanticImportError(
            f"Element {element_id} has TYPE={raw_type!r}, incompatible with layer {entity.layer}."
        )


def _parse_bool(value: str, *, field_name: str, element_id: str) -> bool:
    normalized = value.strip().upper()
    if normalized in {"TRUE", "1", "YES"}:
        return True
    if normalized in {"FALSE", "0", "NO"}:
        return False
    raise SemanticImportError(f"Element {element_id} has invalid boolean {field_name}={value!r}.")


def _parse_nonnegative_float(
    value: str,
    *,
    field_name: str,
    element_id: str,
) -> float:
    try:
        number = float(value.strip())
    except ValueError as exc:
        raise SemanticImportError(
            f"Element {element_id} has invalid numeric {field_name}={value!r}."
        ) from exc

    if not math.isfinite(number) or number < 0:
        raise SemanticImportError(
            f"Element {element_id} requires non-negative finite {field_name}, got {value!r}."
        )

    return number


def _parse_rotations(
    value: str | None,
    *,
    element_id: str,
) -> list[float]:
    """Parse comma-separated rotations, removing duplicates while preserving order."""

    if value is None:
        return [0.0]

    rotations: list[float] = []
    seen: set[float] = set()

    for part in value.split(","):
        stripped = part.strip()
        if not stripped:
            raise SemanticImportError(f"Element {element_id} has an empty ROTATION_VALUES entry.")
        try:
            rotation = float(stripped)
        except ValueError as exc:
            raise SemanticImportError(
                f"Element {element_id} has invalid ROTATION_VALUES entry {stripped!r}."
            ) from exc
        if not math.isfinite(rotation):
            raise SemanticImportError(
                f"Element {element_id} has non-finite ROTATION_VALUES entry {stripped!r}."
            )
        if rotation not in seen:
            rotations.append(rotation)
            seen.add(rotation)

    return rotations


def _anchor(vertices: list[tuple[float, float]]) -> tuple[float, float]:
    count = len(vertices)
    return (
        sum(x for x, _ in vertices) / count,
        sum(y for _, y in vertices) / count,
    )


def _build_variation_bounds(
    entity: DxfEntitySummary,
    *,
    element_id: str,
    transform: Transform,
    movable: bool,
) -> VariationBounds | None:
    if not movable:
        return None

    x_tol_minus = _parse_nonnegative_float(
        entity.attributes.get("X_TOL_MINUS", "0.0"),
        field_name="X_TOL_MINUS",
        element_id=element_id,
    )
    x_tol_plus = _parse_nonnegative_float(
        entity.attributes.get("X_TOL_PLUS", "0.0"),
        field_name="X_TOL_PLUS",
        element_id=element_id,
    )
    y_tol_minus = _parse_nonnegative_float(
        entity.attributes.get("Y_TOL_MINUS", "0.0"),
        field_name="Y_TOL_MINUS",
        element_id=element_id,
    )
    y_tol_plus = _parse_nonnegative_float(
        entity.attributes.get("Y_TOL_PLUS", "0.0"),
        field_name="Y_TOL_PLUS",
        element_id=element_id,
    )
    rotations = _parse_rotations(
        entity.attributes.get("ROTATION_VALUES"),
        element_id=element_id,
    )

    return VariationBounds(
        x_min=transform.x - x_tol_minus,
        x_max=transform.x + x_tol_plus,
        y_min=transform.y - y_tol_minus,
        y_max=transform.y + y_tol_plus,
        rotations_deg=rotations,
    )


def _element_from_entity(entity: DxfEntitySummary) -> ElementSpec:
    element_id = _required_id(entity)
    _validate_type_alias(entity, element_id=element_id)

    if not _is_closed_polygon(entity):
        raise SemanticImportError(f"Element {element_id} has invalid polygon geometry.")

    anchor_x, anchor_y = _anchor(entity.vertices)
    local_vertices = [(x - anchor_x, y - anchor_y) for x, y in entity.vertices]
    geometry = _polygon_data_from_vertices(
        local_vertices,
        message=f"Element {element_id} has invalid polygon geometry.",
    )
    transform = Transform(x=anchor_x, y=anchor_y, rotation_deg=0.0)

    raw_movable = entity.attributes.get("MOVABLE")
    movable = (
        _parse_bool(raw_movable, field_name="MOVABLE", element_id=element_id)
        if raw_movable is not None
        else False
    )

    return ElementSpec(
        id=element_id,
        type=_LAYER_TO_TYPE[entity.layer],
        layer=entity.layer,
        geometry=geometry,
        transform=transform,
        movable=movable,
        variation_bounds=_build_variation_bounds(
            entity,
            element_id=element_id,
            transform=transform,
            movable=movable,
        ),
    )


def _obstacle_from_entity(entity: DxfEntitySummary) -> Obstacle:
    obstacle_id = _optional_id(entity, fallback_prefix="OBSTACLE")
    if len(entity.vertices) < 3:
        raise SemanticImportError(f"Obstacle {obstacle_id} has invalid polygon geometry.")
    return Obstacle(
        id=obstacle_id,
        polygon=_polygon_data_from_vertices(
            entity.vertices,
            message=f"Obstacle {obstacle_id} has invalid polygon geometry.",
        ),
    )


def _single_room(rooms: list[DxfEntitySummary]) -> PolygonData:
    if not rooms:
        raise SemanticImportError("DXF semantic layout requires exactly one ACC_ROOM.")
    if len(rooms) > 1:
        raise SemanticImportError("DXF semantic layout contains more than one ACC_ROOM.")
    room = rooms[0]
    if not _is_closed_polygon(room):
        raise SemanticImportError(
            "ACC_ROOM must be a closed POLYLINE or LWPOLYLINE with at least 3 vertices."
        )
    return _polygon_data_from_vertices(
        room.vertices,
        message="ACC_ROOM has invalid polygon geometry.",
    )


def _single_point_pose(
    entities: list[DxfEntitySummary],
    *,
    layer: str,
    required: bool,
) -> Pose | None:
    if not entities:
        if required:
            raise SemanticImportError(f"DXF semantic layout requires exactly one {layer}.")
        return None
    if len(entities) > 1:
        raise SemanticImportError(f"DXF semantic layout contains more than one {layer}.")
    point = entities[0].point
    if point is None:
        raise SemanticImportError(f"{layer} must be a POINT entity.")
    return Pose(x=point[0], y=point[1], angle_deg=0.0)


def world_coordinates(element: ElementSpec) -> list[tuple[float, float]]:
    """Reconstruct nominal world coordinates without applying rotation."""

    return [
        (x + element.transform.x, y + element.transform.y) for x, y in element.geometry.coordinates
    ]


def semantic_from_inspection(
    inspection: DxfInspection,
) -> DxfSemanticData:
    """Convert an inspected DXF into semantic layout data."""

    _require_supported_units(inspection)

    rooms: list[DxfEntitySummary] = []
    entries: list[DxfEntitySummary] = []
    targets: list[DxfEntitySummary] = []
    elements: list[ElementSpec] = []
    obstacles: list[Obstacle] = []
    warnings: list[str] = []
    used_ids: set[str] = set()

    for entity in inspection.entities:
        if entity.layer == "ACC_ROOM":
            rooms.append(entity)
        elif entity.layer == "ACC_ENTRY":
            entries.append(entity)
        elif entity.layer == "ACC_TARGET":
            targets.append(entity)
        elif entity.layer in _LAYER_TO_TYPE:
            element = _element_from_entity(entity)
            if element.id in used_ids:
                raise SemanticImportError(f"Duplicate semantic ID: {element.id}.")
            used_ids.add(element.id)
            elements.append(element)
        elif entity.layer == "ACC_OBSTACLE":
            obstacle = _obstacle_from_entity(entity)
            if obstacle.id in used_ids:
                raise SemanticImportError(f"Duplicate semantic ID: {obstacle.id}.")
            used_ids.add(obstacle.id)
            obstacles.append(obstacle)
        elif entity.layer in _IGNORED_WARNING_LAYERS:
            warnings.append(f"Ignored layer {entity.layer} in this semantic import milestone.")
        else:
            warnings.append(f"Ignored unknown layer {entity.layer}.")

    entry = _single_point_pose(entries, layer="ACC_ENTRY", required=True)
    if entry is None:
        raise SemanticImportError("DXF semantic layout requires exactly one ACC_ENTRY.")

    return DxfSemanticData(
        room=_single_room(rooms),
        obstacles=obstacles,
        elements=elements,
        entry=entry,
        target=_single_point_pose(targets, layer="ACC_TARGET", required=False),
        warnings=warnings,
    )


def semantic_from_dxf(
    path: str | Path,
) -> DxfSemanticData:
    """Inspect a DXF file and convert it into semantic layout data."""

    return semantic_from_inspection(inspect_dxf(path))


def build_scene(
    semantic: DxfSemanticData,
    wheelchair: WheelchairSpec,
    *,
    path_settings: PathSettings | None = None,
) -> Scene:
    """Build a solver Scene from semantic CAD data."""

    return Scene(
        units="meters",
        room=semantic.room,
        obstacles=semantic.obstacles,
        elements=semantic.elements,
        entry=semantic.entry,
        target=semantic.target,
        wheelchair=wheelchair,
        path_settings=PathSettings() if path_settings is None else path_settings,
        manual_path=[],
    )


def main() -> None:
    """Run the semantic DXF importer from the command line."""

    import argparse

    parser = argparse.ArgumentParser(description="Convert a DXF layout to semantic JSON.")
    parser.add_argument("path", type=Path)
    parser.add_argument("--output", type=Path, default=Path("semantic_layout.json"))
    arguments = parser.parse_args()

    semantic = semantic_from_dxf(arguments.path)
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(semantic.model_dump_json(indent=2), encoding="utf-8")
    print(f"Semantic layout saved to: {arguments.output}")


if __name__ == "__main__":
    main()
