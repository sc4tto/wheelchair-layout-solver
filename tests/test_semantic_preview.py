from pathlib import Path

import matplotlib
import pytest

matplotlib.use("Agg")

from wheelchair_layout_solver.cad import semantic_preview
from wheelchair_layout_solver.cad.dxf_importer import DxfEntitySummary, DxfInspection
from wheelchair_layout_solver.cad.semantic_importer import DxfSemanticData
from wheelchair_layout_solver.models import (
    ElementSpec,
    ElementType,
    PolygonData,
    Pose,
    Transform,
    VariationBounds,
)


def _dxf_entity(
    *,
    layer: str = "ACC_WC",
    entity_id: str = "WC_01",
    vertices: list[tuple[float, float]] | None = None,
) -> DxfEntitySummary:
    return DxfEntitySummary(
        handle=entity_id,
        entity_type="POLYLINE",
        layer=layer,
        is_closed=True,
        point_count=4,
        xdata={},
        vertices=vertices
        if vertices is not None
        else [(0.5, 0.5), (1.0, 0.5), (1.0, 1.0), (0.5, 1.0)],
        point=None,
        attributes={"ID": entity_id},
    )


def _inspection(entities: list[DxfEntitySummary] | None = None) -> DxfInspection:
    return DxfInspection(
        path=Path("sample.dxf"),
        insunits=6,
        entities=[] if entities is None else entities,
    )


def _element(
    *,
    element_id: str = "WC_01",
    layer: str = "ACC_WC",
    variation_bounds: VariationBounds | None = None,
) -> ElementSpec:
    return ElementSpec(
        id=element_id,
        type=ElementType.TOILET,
        layer=layer,
        geometry=PolygonData(
            coordinates=[(-0.25, -0.25), (0.25, -0.25), (0.25, 0.25), (-0.25, 0.25)]
        ),
        transform=Transform(x=0.75, y=0.75, rotation_deg=0.0),
        movable=variation_bounds is not None,
        variation_bounds=variation_bounds,
    )


def _semantic(elements: list[ElementSpec] | None = None) -> DxfSemanticData:
    return DxfSemanticData(
        room=PolygonData(coordinates=[(0.0, 0.0), (3.0, 0.0), (3.0, 2.0), (0.0, 2.0)]),
        elements=[] if elements is None else elements,
        entry=Pose(x=2.5, y=0.25, angle_deg=0.0),
    )


def test_render_semantic_preview_creates_png(tmp_path: Path) -> None:
    output = tmp_path / "semantic.png"

    result = semantic_preview.render_semantic_preview(
        _inspection([_dxf_entity()]),
        _semantic([_element()]),
        output,
    )

    assert result == output
    assert output.is_file()
    assert output.stat().st_size > 0


def test_render_semantic_preview_creates_output_directory(tmp_path: Path) -> None:
    output = tmp_path / "nested" / "semantic.png"

    semantic_preview.render_semantic_preview(
        _inspection([_dxf_entity()]),
        _semantic([_element()]),
        output,
    )

    assert output.is_file()
    assert output.stat().st_size > 0


def test_render_semantic_preview_handles_room_entry_and_element(tmp_path: Path) -> None:
    output = tmp_path / "layout.png"

    semantic_preview.render_semantic_preview(
        _inspection([_dxf_entity()]),
        _semantic([_element()]),
        output,
    )

    assert output.is_file()
    assert output.stat().st_size > 0


def test_render_semantic_preview_handles_variation_bounds(tmp_path: Path) -> None:
    output = tmp_path / "bounds.png"
    element = _element(
        variation_bounds=VariationBounds(
            x_min=0.5,
            x_max=1.0,
            y_min=0.5,
            y_max=1.0,
            rotations_deg=[0.0],
        )
    )

    semantic_preview.render_semantic_preview(
        _inspection([_dxf_entity()]),
        _semantic([element]),
        output,
    )

    assert output.is_file()
    assert output.stat().st_size > 0


def test_render_semantic_preview_handles_element_without_bounds(tmp_path: Path) -> None:
    output = tmp_path / "without-bounds.png"

    semantic_preview.render_semantic_preview(
        _inspection([_dxf_entity()]),
        _semantic([_element()]),
        output,
    )

    assert output.is_file()
    assert output.stat().st_size > 0


def test_render_semantic_preview_handles_missing_matching_source(tmp_path: Path) -> None:
    output = tmp_path / "missing-source.png"

    semantic_preview.render_semantic_preview(
        _inspection([]),
        _semantic([_element()]),
        output,
    )

    assert output.is_file()
    assert output.stat().st_size > 0


def test_render_semantic_preview_handles_unknown_and_empty_source_layers(
    tmp_path: Path,
) -> None:
    output = tmp_path / "unknown.png"

    semantic_preview.render_semantic_preview(
        _inspection([_dxf_entity(layer="ACC_UNKNOWN", entity_id="UNKNOWN_01", vertices=[])]),
        _semantic([]),
        output,
    )

    assert output.is_file()
    assert output.stat().st_size > 0


def test_semantic_preview_from_dxf_uses_importers(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output = tmp_path / "from-dxf.png"
    inspection = _inspection([_dxf_entity()])
    semantic = _semantic([_element()])
    inspect_calls: list[Path] = []
    semantic_calls: list[Path] = []

    def fake_inspect_dxf(path: str | Path) -> DxfInspection:
        inspect_calls.append(Path(path))
        return inspection

    def fake_semantic_from_dxf(path: str | Path) -> DxfSemanticData:
        semantic_calls.append(Path(path))
        return semantic

    monkeypatch.setattr(semantic_preview, "inspect_dxf", fake_inspect_dxf)
    monkeypatch.setattr(semantic_preview, "semantic_from_dxf", fake_semantic_from_dxf)

    result = semantic_preview.semantic_preview_from_dxf("sample.dxf", output)

    assert result == output
    assert inspect_calls == [Path("sample.dxf")]
    assert semantic_calls == [Path("sample.dxf")]
    assert output.is_file()
    assert output.stat().st_size > 0
