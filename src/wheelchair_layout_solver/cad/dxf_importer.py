"""Inspection utilities for Rhino-exported DXF files."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ezdxf.filemanagement import readfile


@dataclass(frozen=True)
class DxfEntitySummary:
    """Minimal information collected from one DXF entity."""

    handle: str
    entity_type: str
    layer: str
    is_closed: bool | None
    point_count: int | None
    xdata: dict[str, list[tuple[int, str]]]
    vertices: list[tuple[float, float]]
    point: tuple[float, float] | None
    attributes: dict[str, str]


@dataclass(frozen=True)
class DxfInspection:
    """Summary of the modelspace content of a DXF document."""

    path: Path
    insunits: int
    entities: list[DxfEntitySummary]


def _appid_names(document: Any) -> list[str]:
    """Return all registered DXF application identifiers."""

    return [str(entry.dxf.name) for entry in document.appids]


def _entity_is_closed(entity: Any) -> bool | None:
    """Return the closed state for supported polyline entities."""

    if entity.dxftype() in {"LWPOLYLINE", "POLYLINE"}:
        return bool(entity.is_closed)

    return None


def _entity_point_count(entity: Any) -> int | None:
    """Return a point count for supported geometry entities."""

    entity_type = entity.dxftype()

    if entity_type == "LWPOLYLINE":
        return len(entity)

    if entity_type == "POLYLINE":
        return len(list(entity.vertices))

    if entity_type == "POINT":
        return 1

    return None


def _polyline_vertices(entity: Any) -> list[tuple[float, float]]:
    """Return XY vertices for supported polyline entities."""

    entity_type = entity.dxftype()

    if entity_type == "POLYLINE":
        return [
            (float(vertex.dxf.location.x), float(vertex.dxf.location.y))
            for vertex in entity.vertices
        ]

    if entity_type == "LWPOLYLINE":
        return [(float(x), float(y)) for x, y in entity.get_points("xy")]

    return []


def _point_coordinates(entity: Any) -> tuple[float, float] | None:
    """Return XY coordinates for a POINT entity."""

    if entity.dxftype() != "POINT":
        return None

    location = entity.dxf.location
    return (float(location.x), float(location.y))


def _entity_xdata(
    entity: Any,
    appids: list[str],
) -> dict[str, list[tuple[int, str]]]:
    """Collect all XDATA attached to an entity."""

    result: dict[str, list[tuple[int, str]]] = {}

    for appid in appids:
        if not entity.has_xdata(appid):
            continue

        tags = entity.get_xdata(appid)
        result[appid] = [(int(tag.code), str(tag.value)) for tag in tags]

    return result


def _parse_rhino_xdata(
    xdata: dict[str, list[tuple[int, str]]],
) -> dict[str, str]:
    """Parse Rhino XDATA groups into flat key/value attributes."""

    attributes: dict[str, str] = {}
    current_group: list[str] | None = None

    for code, value in xdata.get("Rhino", []):
        if code == 1002 and value == "{":
            current_group = []
            continue

        if code == 1002 and value == "}":
            if current_group is not None and len(current_group) >= 2:
                attributes[current_group[0]] = current_group[1]
            current_group = None
            continue

        if current_group is not None and code == 1000:
            current_group.append(value)

    return attributes


def inspect_dxf(path: str | Path) -> DxfInspection:
    """Read a DXF file and summarize its modelspace entities."""

    dxf_path = Path(path)

    if not dxf_path.is_file():
        raise FileNotFoundError(f"DXF file not found: {dxf_path}")

    document = readfile(dxf_path)
    modelspace = document.modelspace()
    appids = _appid_names(document)

    entities: list[DxfEntitySummary] = []

    for entity in modelspace:
        xdata = _entity_xdata(entity, appids)
        entities.append(
            DxfEntitySummary(
                handle=str(entity.dxf.handle),
                entity_type=str(entity.dxftype()),
                layer=str(entity.dxf.layer),
                is_closed=_entity_is_closed(entity),
                point_count=_entity_point_count(entity),
                xdata=xdata,
                vertices=_polyline_vertices(entity),
                point=_point_coordinates(entity),
                attributes=_parse_rhino_xdata(xdata),
            )
        )

    return DxfInspection(
        path=dxf_path,
        insunits=int(document.header.get("$INSUNITS", 0)),
        entities=entities,
    )


def _format_xy(point: tuple[float, float]) -> str:
    """Format XY coordinates for stable text reports."""

    return f"({point[0]:.6f}, {point[1]:.6f})"


def format_inspection(inspection: DxfInspection) -> str:
    """Create a readable text report."""

    layer_counts = Counter(entity.layer for entity in inspection.entities)

    lines = [
        f"DXF: {inspection.path}",
        f"$INSUNITS: {inspection.insunits}",
        f"Entities: {len(inspection.entities)}",
        "",
        "Layers:",
    ]

    for layer, count in sorted(layer_counts.items()):
        lines.append(f"  {layer}: {count}")

    lines.append("")
    lines.append("Entities:")

    for entity in inspection.entities:
        lines.append(
            "  "
            f"handle={entity.handle} "
            f"type={entity.entity_type} "
            f"layer={entity.layer} "
            f"closed={entity.is_closed} "
            f"points={entity.point_count}"
        )

        if entity.vertices:
            lines.append("    vertices:")
            for vertex in entity.vertices:
                lines.append(f"      {_format_xy(vertex)}")

        if entity.point is not None:
            lines.append(f"    point: {_format_xy(entity.point)}")

        if entity.attributes:
            lines.append("    attributes:")
            for key, value in sorted(entity.attributes.items()):
                lines.append(f"      {key} = {value}")

        for appid, tags in entity.xdata.items():
            lines.append(f"    XDATA {appid}:")
            for code, value in tags:
                lines.append(f"      {code}: {value}")

    return "\n".join(lines)


def main() -> None:
    """Run the DXF inspector from the command line."""

    import argparse

    parser = argparse.ArgumentParser(
        description="Inspect layers, geometry and XDATA in a DXF file."
    )
    parser.add_argument("path", type=Path)
    arguments = parser.parse_args()

    inspection = inspect_dxf(arguments.path)
    print(format_inspection(inspection))


if __name__ == "__main__":
    main()
