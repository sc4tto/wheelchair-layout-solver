from pathlib import Path

import matplotlib
import pytest

matplotlib.use("Agg")

from wheelchair_layout_solver.cad import preview
from wheelchair_layout_solver.cad.dxf_importer import DxfEntitySummary, DxfInspection


def _entity(
    *,
    layer: str,
    entity_type: str = "POLYLINE",
    vertices: list[tuple[float, float]] | None = None,
    point: tuple[float, float] | None = None,
    attributes: dict[str, str] | None = None,
) -> DxfEntitySummary:
    return DxfEntitySummary(
        handle=layer,
        entity_type=entity_type,
        layer=layer,
        is_closed=True if vertices else None,
        point_count=len(vertices) if vertices is not None else (1 if point else None),
        xdata={},
        vertices=[] if vertices is None else vertices,
        point=point,
        attributes={} if attributes is None else attributes,
    )


def _inspection(entities: list[DxfEntitySummary]) -> DxfInspection:
    return DxfInspection(path=Path("sample.dxf"), insunits=6, entities=entities)


def test_render_preview_creates_png_from_inspection(tmp_path: Path) -> None:
    output = tmp_path / "preview.png"
    inspection = _inspection(
        [
            _entity(
                layer="ACC_ROOM",
                vertices=[(0.0, 0.0), (3.0, 0.0), (3.0, 2.0), (0.0, 2.0)],
            )
        ]
    )

    result = preview.render_preview(inspection, output)

    assert result == output
    assert output.is_file()
    assert output.stat().st_size > 0


def test_render_preview_creates_output_directory(tmp_path: Path) -> None:
    output = tmp_path / "nested" / "bathroom.png"
    inspection = _inspection(
        [
            _entity(
                layer="ACC_ROOM",
                vertices=[(0.0, 0.0), (3.0, 0.0), (3.0, 2.0), (0.0, 2.0)],
            )
        ]
    )

    preview.render_preview(inspection, output)

    assert output.is_file()
    assert output.stat().st_size > 0


def test_render_preview_handles_room_element_and_entry_point(tmp_path: Path) -> None:
    output = tmp_path / "layout.png"
    inspection = _inspection(
        [
            _entity(
                layer="ACC_ROOM",
                vertices=[(0.0, 0.0), (3.0, 0.0), (3.0, 2.0), (0.0, 2.0)],
            ),
            _entity(
                layer="ACC_WC",
                vertices=[(0.5, 0.5), (1.0, 0.5), (1.0, 1.0), (0.5, 1.0)],
                attributes={"ID": "WC_01"},
            ),
            _entity(layer="ACC_ENTRY", entity_type="POINT", point=(2.5, 0.25)),
        ]
    )

    preview.render_preview(inspection, output)

    assert output.is_file()
    assert output.stat().st_size > 0


def test_render_preview_handles_unknown_layer(tmp_path: Path) -> None:
    output = tmp_path / "unknown.png"
    inspection = _inspection(
        [
            _entity(
                layer="ACC_UNKNOWN",
                vertices=[(0.0, 0.0), (1.0, 0.0), (1.0, 1.0)],
            )
        ]
    )

    preview.render_preview(inspection, output)

    assert output.is_file()
    assert output.stat().st_size > 0


def test_render_preview_ignores_entity_without_geometry(tmp_path: Path) -> None:
    output = tmp_path / "empty-entity.png"
    inspection = _inspection(
        [
            _entity(layer="ACC_NOTE", entity_type="TEXT"),
        ]
    )

    preview.render_preview(inspection, output)

    assert output.is_file()
    assert output.stat().st_size > 0


def test_preview_dxf_uses_inspect_dxf(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output = tmp_path / "patched.png"
    inspection = _inspection(
        [
            _entity(
                layer="ACC_ROOM",
                vertices=[(0.0, 0.0), (2.0, 0.0), (2.0, 2.0), (0.0, 2.0)],
            )
        ]
    )
    calls: list[Path] = []

    def fake_inspect_dxf(input_path: str | Path) -> DxfInspection:
        calls.append(Path(input_path))
        return inspection

    monkeypatch.setattr(preview, "inspect_dxf", fake_inspect_dxf)

    result = preview.preview_dxf("fake.dxf", output)

    assert result == output
    assert calls == [Path("fake.dxf")]
    assert output.is_file()
    assert output.stat().st_size > 0
