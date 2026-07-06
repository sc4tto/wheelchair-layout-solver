from pathlib import Path

import pytest

from wheelchair_layout_solver.cad.dxf_importer import DxfEntitySummary, DxfInspection
from wheelchair_layout_solver.cad.semantic_importer import (
    SemanticImportError,
    build_scene,
    semantic_from_dxf,
    semantic_from_inspection,
    world_coordinates,
)
from wheelchair_layout_solver.models import ElementType, PathSettings, WheelchairSpec


def _entity(
    *,
    layer: str,
    handle: str | None = None,
    entity_type: str = "POLYLINE",
    vertices: list[tuple[float, float]] | None = None,
    point: tuple[float, float] | None = None,
    attributes: dict[str, str] | None = None,
    is_closed: bool | None = None,
) -> DxfEntitySummary:
    actual_vertices = [] if vertices is None else vertices
    return DxfEntitySummary(
        handle=layer if handle is None else handle,
        entity_type=entity_type,
        layer=layer,
        is_closed=(bool(actual_vertices) if is_closed is None else is_closed),
        point_count=len(actual_vertices) if actual_vertices else (1 if point else None),
        xdata={},
        vertices=actual_vertices,
        point=point,
        attributes={} if attributes is None else attributes,
    )


def _room() -> DxfEntitySummary:
    return _entity(
        layer="ACC_ROOM",
        vertices=[(0.0, 0.0), (4.0, 0.0), (4.0, 3.0), (0.0, 3.0)],
    )


def _entry() -> DxfEntitySummary:
    return _entity(layer="ACC_ENTRY", entity_type="POINT", point=(1.0, 0.0))


def _element(
    *,
    layer: str = "ACC_WC",
    element_id: str = "WC_01",
    type_value: str | None = "WC",
    movable: str | None = None,
    attributes: dict[str, str] | None = None,
    vertices: list[tuple[float, float]] | None = None,
) -> DxfEntitySummary:
    actual_attributes = {"ID": element_id}
    if type_value is not None:
        actual_attributes["TYPE"] = type_value
    if movable is not None:
        actual_attributes["MOVABLE"] = movable
    if attributes:
        actual_attributes.update(attributes)
    return _entity(
        layer=layer,
        vertices=vertices
        if vertices is not None
        else [(1.0, 1.0), (2.0, 1.0), (2.0, 2.0), (1.0, 2.0)],
        attributes=actual_attributes,
    )


def _inspection(*entities: DxfEntitySummary, insunits: int = 6) -> DxfInspection:
    return DxfInspection(path=Path("sample.dxf"), insunits=insunits, entities=list(entities))


def _basic_semantic(*extra: DxfEntitySummary, insunits: int = 6) -> DxfInspection:
    return _inspection(_room(), _entry(), *extra, insunits=insunits)


def test_room_converts_to_absolute_polygon_data() -> None:
    semantic = semantic_from_inspection(_basic_semantic())

    assert semantic.room.coordinates == _room().vertices


def test_entry_converts_to_pose() -> None:
    semantic = semantic_from_inspection(_basic_semantic())

    assert semantic.entry.x == pytest.approx(1.0)
    assert semantic.entry.y == pytest.approx(0.0)
    assert semantic.entry.angle_deg == pytest.approx(0.0)


def test_target_converts_when_present() -> None:
    target = _entity(layer="ACC_TARGET", entity_type="POINT", point=(3.0, 2.0))

    semantic = semantic_from_inspection(_basic_semantic(target))

    assert semantic.target is not None
    assert semantic.target.x == pytest.approx(3.0)
    assert semantic.target.y == pytest.approx(2.0)


def test_wc_layer_maps_to_toilet() -> None:
    semantic = semantic_from_inspection(_basic_semantic(_element()))

    assert semantic.elements[0].type is ElementType.TOILET


@pytest.mark.parametrize(
    ("layer", "type_value", "expected"),
    [
        ("ACC_SINK", "SINK", ElementType.SINK),
        ("ACC_BIDET", "BIDET", ElementType.BIDET),
        ("ACC_DOOR", "DOOR", ElementType.DOOR),
        ("ACC_SHOWER", "SHOWER", ElementType.SHOWER),
    ],
)
def test_supported_layers_map_to_element_types(
    layer: str,
    type_value: str,
    expected: ElementType,
) -> None:
    semantic = semantic_from_inspection(
        _basic_semantic(_element(layer=layer, element_id=f"{layer}_01", type_value=type_value))
    )

    assert semantic.elements[0].type is expected


def test_element_id_is_required() -> None:
    element = _element()
    element.attributes.pop("ID")

    with pytest.raises(SemanticImportError):
        semantic_from_inspection(_basic_semantic(element))


def test_duplicate_ids_are_rejected() -> None:
    first = _element(element_id="DUPLICATE")
    second = _element(layer="ACC_SINK", element_id="DUPLICATE", type_value="SINK")

    with pytest.raises(SemanticImportError):
        semantic_from_inspection(_basic_semantic(first, second))


def test_compatible_type_alias_is_accepted() -> None:
    semantic = semantic_from_inspection(
        _basic_semantic(_element(layer="ACC_DOOR", element_id="DOOR_01", type_value=" porta "))
    )

    assert semantic.elements[0].type is ElementType.DOOR


def test_incompatible_type_is_rejected() -> None:
    with pytest.raises(SemanticImportError):
        semantic_from_inspection(
            _basic_semantic(_element(layer="ACC_WC", element_id="WC_01", type_value="SINK"))
        )


def test_movable_true_creates_variation_bounds() -> None:
    semantic = semantic_from_inspection(_basic_semantic(_element(movable="TRUE")))

    assert semantic.elements[0].movable is True
    assert semantic.elements[0].variation_bounds is not None


def test_movable_false_ignores_variation_bounds() -> None:
    semantic = semantic_from_inspection(
        _basic_semantic(
            _element(
                movable="FALSE",
                attributes={"X_TOL_MINUS": "0.5", "ROTATION_VALUES": "0,90"},
            )
        )
    )

    assert semantic.elements[0].movable is False
    assert semantic.elements[0].variation_bounds is None


def test_invalid_boolean_is_rejected() -> None:
    with pytest.raises(SemanticImportError):
        semantic_from_inspection(_basic_semantic(_element(movable="MAYBE")))


def test_element_geometry_is_local() -> None:
    semantic = semantic_from_inspection(_basic_semantic(_element()))

    assert semantic.elements[0].geometry.coordinates == [
        (-0.5, -0.5),
        (0.5, -0.5),
        (0.5, 0.5),
        (-0.5, 0.5),
    ]


def test_transform_is_at_average_vertex_position() -> None:
    semantic = semantic_from_inspection(_basic_semantic(_element()))

    assert semantic.elements[0].transform.x == pytest.approx(1.5)
    assert semantic.elements[0].transform.y == pytest.approx(1.5)


def test_world_coordinates_reconstruct_original_vertices() -> None:
    element = semantic_from_inspection(_basic_semantic(_element())).elements[0]

    for actual, expected in zip(world_coordinates(element), _element().vertices, strict=True):
        assert actual == pytest.approx(expected)


def test_variation_bounds_come_from_tolerances() -> None:
    semantic = semantic_from_inspection(
        _basic_semantic(
            _element(
                movable="TRUE",
                attributes={
                    "X_TOL_MINUS": "0.25",
                    "X_TOL_PLUS": "0.75",
                    "Y_TOL_MINUS": "0.10",
                    "Y_TOL_PLUS": "0.20",
                },
            )
        )
    )

    bounds = semantic.elements[0].variation_bounds
    assert bounds is not None
    assert bounds.x_min == pytest.approx(1.25)
    assert bounds.x_max == pytest.approx(2.25)
    assert bounds.y_min == pytest.approx(1.4)
    assert bounds.y_max == pytest.approx(1.7)


def test_negative_tolerance_is_rejected() -> None:
    with pytest.raises(SemanticImportError):
        semantic_from_inspection(
            _basic_semantic(_element(movable="TRUE", attributes={"X_TOL_MINUS": "-0.1"}))
        )


def test_rotation_values_are_parsed() -> None:
    semantic = semantic_from_inspection(
        _basic_semantic(_element(movable="TRUE", attributes={"ROTATION_VALUES": "0, 90, 90, 180"}))
    )

    bounds = semantic.elements[0].variation_bounds
    assert bounds is not None
    assert bounds.rotations_deg == [0.0, 90.0, 180.0]


def test_non_meter_units_are_rejected() -> None:
    with pytest.raises(SemanticImportError):
        semantic_from_inspection(_basic_semantic(insunits=4))


def test_missing_room_is_rejected() -> None:
    with pytest.raises(SemanticImportError):
        semantic_from_inspection(_inspection(_entry()))


def test_multiple_rooms_are_rejected() -> None:
    with pytest.raises(SemanticImportError):
        semantic_from_inspection(_inspection(_room(), _room(), _entry()))


def test_missing_entry_is_rejected() -> None:
    with pytest.raises(SemanticImportError):
        semantic_from_inspection(_inspection(_room()))


def test_multiple_entries_are_rejected() -> None:
    with pytest.raises(SemanticImportError):
        semantic_from_inspection(_inspection(_room(), _entry(), _entry()))


def test_unknown_layer_produces_warning() -> None:
    semantic = semantic_from_inspection(_basic_semantic(_entity(layer="ACC_UNKNOWN")))

    assert semantic.warnings == ["Ignored unknown layer ACC_UNKNOWN."]


def test_obstacle_layer_produces_obstacle() -> None:
    semantic = semantic_from_inspection(
        _basic_semantic(
            _entity(
                layer="ACC_OBSTACLE",
                handle="99",
                vertices=[(2.0, 2.0), (3.0, 2.0), (3.0, 3.0)],
            )
        )
    )

    assert semantic.obstacles[0].id == "OBSTACLE_99"
    assert semantic.obstacles[0].polygon.coordinates == [(2.0, 2.0), (3.0, 2.0), (3.0, 3.0)]


def test_build_scene_copies_semantic_data() -> None:
    semantic = semantic_from_inspection(_basic_semantic(_element()))
    wheelchair = WheelchairSpec(width=0.7, length=1.2)
    path_settings = PathSettings(spatial_step=0.1, angular_step_deg=10.0)

    scene = build_scene(semantic, wheelchair, path_settings=path_settings)

    assert scene.units == "meters"
    assert scene.room == semantic.room
    assert scene.elements == semantic.elements
    assert scene.entry == semantic.entry
    assert scene.target == semantic.target
    assert scene.wheelchair == wheelchair
    assert scene.path_settings == path_settings
    assert scene.manual_path == []


def test_semantic_data_serializes_to_json() -> None:
    semantic = semantic_from_inspection(_basic_semantic(_element()))

    payload = semantic.model_dump_json(indent=2)

    assert '"room"' in payload
    assert '"elements"' in payload
    assert "WC_01" in payload


def test_semantic_from_dxf_calls_inspect_dxf(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    inspection = _basic_semantic(_element())
    calls: list[Path] = []

    def fake_inspect_dxf(path: str | Path) -> DxfInspection:
        calls.append(Path(path))
        return inspection

    monkeypatch.setattr(
        "wheelchair_layout_solver.cad.semantic_importer.inspect_dxf",
        fake_inspect_dxf,
    )

    semantic = semantic_from_dxf("sample.dxf")

    assert calls == [Path("sample.dxf")]
    assert semantic.elements[0].id == "WC_01"
