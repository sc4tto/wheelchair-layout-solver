from pathlib import Path

import pytest

from wheelchair_layout_solver import candidates
from wheelchair_layout_solver.cad.semantic_importer import DxfSemanticData
from wheelchair_layout_solver.candidates import (
    CandidateGenerationError,
    generate_layout_candidates,
    transformed_coordinates,
)
from wheelchair_layout_solver.models import (
    ElementSpec,
    ElementType,
    PolygonData,
    Pose,
    Transform,
    VariationBounds,
)


def _element(
    element_id: str,
    *,
    movable: bool = False,
    bounds: VariationBounds | None = None,
    transform: Transform | None = None,
) -> ElementSpec:
    return ElementSpec(
        id=element_id,
        type=ElementType.TOILET,
        layer="ACC_WC",
        geometry=PolygonData(coordinates=[(-0.5, -0.5), (0.5, -0.5), (0.0, 0.5)]),
        transform=Transform(x=1.0, y=2.0, rotation_deg=0.0) if transform is None else transform,
        movable=movable,
        variation_bounds=bounds,
    )


def _mobile_element(element_id: str = "WC_01") -> ElementSpec:
    return _element(
        element_id,
        movable=True,
        bounds=VariationBounds(
            x_min=0.0,
            x_max=2.0,
            y_min=1.0,
            y_max=3.0,
            rotations_deg=[0.0, 90.0, 180.0, 270.0],
        ),
    )


def _semantic(elements: list[ElementSpec]) -> DxfSemanticData:
    return DxfSemanticData(
        room=PolygonData(coordinates=[(0.0, 0.0), (4.0, 0.0), (4.0, 3.0), (0.0, 3.0)]),
        elements=elements,
        entry=Pose(x=0.0, y=0.0),
    )


def _placement(candidate: candidates.LayoutCandidate, element_id: str) -> Transform:
    for placement in candidate.placements:
        if placement.element_id == element_id:
            return placement.transform
    raise AssertionError(f"Missing placement for {element_id}")


def test_baseline_is_always_present_and_first() -> None:
    candidate_set = generate_layout_candidates(_semantic([]))

    assert candidate_set.candidates[0].id == "baseline"
    assert candidate_set.candidates[0].changed_element_ids == []


def test_baseline_contains_all_elements() -> None:
    elements = [_element("FIXED_01"), _mobile_element("WC_01")]
    baseline = generate_layout_candidates(_semantic(elements)).candidates[0]

    assert [placement.element_id for placement in baseline.placements] == ["FIXED_01", "WC_01"]


def test_fixed_element_does_not_generate_variants() -> None:
    candidate_set = generate_layout_candidates(_semantic([_element("FIXED_01")]))

    assert [candidate.id for candidate in candidate_set.candidates] == ["baseline"]


def test_mobile_element_generates_min_nominal_and_max_x() -> None:
    candidate_set = generate_layout_candidates(_semantic([_mobile_element()]))
    x_values = {_placement(candidate, "WC_01").x for candidate in candidate_set.candidates[1:]}

    assert x_values == {0.0, 1.0, 2.0}


def test_mobile_element_generates_min_nominal_and_max_y() -> None:
    candidate_set = generate_layout_candidates(_semantic([_mobile_element()]))
    y_values = {_placement(candidate, "WC_01").y for candidate in candidate_set.candidates[1:]}

    assert y_values == {1.0, 2.0, 3.0}


def test_mobile_element_uses_all_rotations() -> None:
    candidate_set = generate_layout_candidates(_semantic([_mobile_element()]))
    rotations = {
        _placement(candidate, "WC_01").rotation_deg for candidate in candidate_set.candidates[1:]
    }

    assert rotations == {0.0, 90.0, 180.0, 270.0}


def test_nominal_pose_is_not_duplicated() -> None:
    candidate_set = generate_layout_candidates(_semantic([_mobile_element()]))

    assert len(candidate_set.candidates) == 36
    assert all(
        _placement(candidate, "WC_01") != Transform(x=1.0, y=2.0, rotation_deg=0.0)
        for candidate in candidate_set.candidates[1:]
    )


def test_only_one_element_changes_per_candidate() -> None:
    candidate_set = generate_layout_candidates(
        _semantic([_mobile_element("WC_01"), _mobile_element("DOOR_01")])
    )

    assert all(len(candidate.changed_element_ids) <= 1 for candidate in candidate_set.candidates)


def test_other_elements_remain_nominal() -> None:
    candidate_set = generate_layout_candidates(
        _semantic([_mobile_element("WC_01"), _mobile_element("DOOR_01")])
    )
    wc_candidate = next(
        candidate for candidate in candidate_set.candidates if candidate.id == "WC_01__001"
    )

    assert _placement(wc_candidate, "DOOR_01") == Transform(x=1.0, y=2.0, rotation_deg=0.0)


def test_candidate_order_is_deterministic() -> None:
    first = generate_layout_candidates(
        _semantic([_mobile_element("WC_01"), _mobile_element("DOOR_01")])
    )
    second = generate_layout_candidates(
        _semantic([_mobile_element("WC_01"), _mobile_element("DOOR_01")])
    )

    assert [candidate.id for candidate in first.candidates] == [
        candidate.id for candidate in second.candidates
    ]


def test_candidate_ids_are_deterministic() -> None:
    candidate_set = generate_layout_candidates(_semantic([_mobile_element("WC_01")]))

    assert candidate_set.candidates[0].id == "baseline"
    assert candidate_set.candidates[1].id == "WC_01__001"
    assert candidate_set.candidates[-1].id == "WC_01__035"


def test_duplicate_sample_values_are_removed() -> None:
    element = _element(
        "WC_01",
        movable=True,
        bounds=VariationBounds(
            x_min=1.0,
            x_max=1.0,
            y_min=2.0,
            y_max=3.0,
            rotations_deg=[0.0],
        ),
    )

    candidate_set = generate_layout_candidates(_semantic([element]))

    assert len(candidate_set.candidates) == 2
    assert _placement(candidate_set.candidates[1], "WC_01").y == pytest.approx(3.0)


def test_partial_bounds_use_nominal_for_missing_axis() -> None:
    element = _element(
        "WC_01",
        movable=True,
        bounds=VariationBounds(x_min=0.0, x_max=2.0, rotations_deg=[0.0]),
    )

    candidate_set = generate_layout_candidates(_semantic([element]))

    assert len(candidate_set.candidates) == 3
    assert {_placement(candidate, "WC_01").y for candidate in candidate_set.candidates} == {2.0}


def test_nominal_transform_outside_bounds_is_rejected() -> None:
    element = _element(
        "WC_01",
        movable=True,
        bounds=VariationBounds(x_min=2.0, x_max=3.0, rotations_deg=[0.0]),
    )

    with pytest.raises(CandidateGenerationError):
        generate_layout_candidates(_semantic([element]))


def test_duplicate_element_ids_are_rejected() -> None:
    with pytest.raises(CandidateGenerationError):
        generate_layout_candidates(_semantic([_element("DUPLICATE"), _element("DUPLICATE")]))


def test_transformed_coordinates_handles_translation_only() -> None:
    element = _element("WC_01")

    coordinates = transformed_coordinates(element, Transform(x=10.0, y=20.0, rotation_deg=0.0))

    assert coordinates == pytest.approx([(9.5, 19.5), (10.5, 19.5), (10.0, 20.5)])


def test_transformed_coordinates_handles_90_degree_rotation() -> None:
    element = _element("WC_01")

    coordinates = transformed_coordinates(element, Transform(x=0.0, y=0.0, rotation_deg=90.0))

    expected = [(0.5, -0.5), (0.5, 0.5), (-0.5, 0.0)]
    for actual, expected_coordinate in zip(coordinates, expected, strict=True):
        assert actual == pytest.approx(expected_coordinate)


def test_transformed_coordinates_does_not_modify_element() -> None:
    element = _element("WC_01")
    original = list(element.geometry.coordinates)

    transformed_coordinates(element, Transform(x=10.0, y=20.0, rotation_deg=90.0))

    assert element.geometry.coordinates == original


def test_candidate_set_serializes_to_json() -> None:
    candidate_set = generate_layout_candidates(_semantic([_mobile_element()]))

    payload = candidate_set.model_dump_json(indent=2)

    assert '"baseline"' in payload
    assert '"WC_01__001"' in payload


def test_cli_uses_semantic_from_dxf(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    output = tmp_path / "layout_candidates.json"
    calls: list[Path] = []

    def fake_semantic_from_dxf(path: str | Path) -> DxfSemanticData:
        calls.append(Path(path))
        return _semantic([_mobile_element()])

    monkeypatch.setattr(candidates, "semantic_from_dxf", fake_semantic_from_dxf)
    monkeypatch.setattr(
        "sys.argv",
        ["candidates", "input.dxf", "--output", str(output)],
    )

    candidates.main()

    assert calls == [Path("input.dxf")]
    assert output.is_file()
    assert "Candidates generated: 36" in capsys.readouterr().out


def test_four_equivalent_mobile_elements_generate_141_total_candidates() -> None:
    candidate_set = generate_layout_candidates(
        _semantic(
            [
                _mobile_element("WC_01"),
                _mobile_element("DOOR_01"),
                _mobile_element("SINK_01"),
                _mobile_element("BIDET_01"),
            ]
        )
    )

    assert len(candidate_set.candidates) == 141
