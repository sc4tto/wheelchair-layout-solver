from pathlib import Path

from wheelchair_layout_solver.cad.dxf_importer import (
    DxfEntitySummary,
    DxfInspection,
    _parse_rhino_xdata,
    format_inspection,
)


def _entity(
    *,
    entity_type: str = "POLYLINE",
    vertices: list[tuple[float, float]] | None = None,
    point: tuple[float, float] | None = None,
    attributes: dict[str, str] | None = None,
) -> DxfEntitySummary:
    return DxfEntitySummary(
        handle="1",
        entity_type=entity_type,
        layer="ACC_TEST",
        is_closed=True if entity_type in {"POLYLINE", "LWPOLYLINE"} else None,
        point_count=len(vertices) if vertices is not None else (1 if point else None),
        xdata={},
        vertices=[] if vertices is None else vertices,
        point=point,
        attributes={} if attributes is None else attributes,
    )


def test_parse_rhino_xdata_reads_two_groups() -> None:
    attributes = _parse_rhino_xdata(
        {
            "Rhino": [
                (1002, "{"),
                (1000, "ID"),
                (1000, "WC_01"),
                (1002, "}"),
                (1002, "{"),
                (1000, "TYPE"),
                (1000, "WC"),
                (1002, "}"),
            ]
        }
    )

    assert attributes == {"ID": "WC_01", "TYPE": "WC"}


def test_parse_rhino_xdata_ignores_incomplete_group() -> None:
    attributes = _parse_rhino_xdata(
        {
            "Rhino": [
                (1002, "{"),
                (1000, "ID"),
                (1002, "}"),
            ]
        }
    )

    assert attributes == {}


def test_parse_rhino_xdata_ignores_other_appids() -> None:
    attributes = _parse_rhino_xdata(
        {
            "Other": [
                (1002, "{"),
                (1000, "ID"),
                (1000, "WC_01"),
                (1002, "}"),
            ]
        }
    )

    assert attributes == {}


def test_parse_rhino_xdata_keeps_last_duplicate_value() -> None:
    attributes = _parse_rhino_xdata(
        {
            "Rhino": [
                (1002, "{"),
                (1000, "MOVABLE"),
                (1000, "FALSE"),
                (1002, "}"),
                (1002, "{"),
                (1000, "MOVABLE"),
                (1000, "TRUE"),
                (1002, "}"),
            ]
        }
    )

    assert attributes == {"MOVABLE": "TRUE"}


def test_format_inspection_shows_vertices() -> None:
    inspection = DxfInspection(
        path=Path("sample.dxf"),
        insunits=6,
        entities=[_entity(vertices=[(1.25, 0.8), (2.0, 0.8)])],
    )

    report = format_inspection(inspection)

    assert "vertices:" in report
    assert "(1.250000, 0.800000)" in report


def test_format_inspection_shows_point() -> None:
    inspection = DxfInspection(
        path=Path("sample.dxf"),
        insunits=6,
        entities=[_entity(entity_type="POINT", point=(1.25, 0.8))],
    )

    report = format_inspection(inspection)

    assert "point: (1.250000, 0.800000)" in report


def test_format_inspection_shows_attributes() -> None:
    inspection = DxfInspection(
        path=Path("sample.dxf"),
        insunits=6,
        entities=[_entity(attributes={"ID": "WC_01", "TYPE": "WC"})],
    )

    report = format_inspection(inspection)

    assert "attributes:" in report
    assert "ID = WC_01" in report
    assert "TYPE = WC" in report
