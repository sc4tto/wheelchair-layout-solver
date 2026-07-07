from pathlib import Path

import pytest

from wheelchair_layout_solver import layout_validation
from wheelchair_layout_solver.cad.semantic_importer import DxfSemanticData
from wheelchair_layout_solver.candidates import (
    ElementPlacement,
    LayoutCandidate,
    LayoutCandidateSet,
)
from wheelchair_layout_solver.layout_validation import (
    LayoutValidationError,
    validate_layout_candidates,
)
from wheelchair_layout_solver.models import (
    ElementSpec,
    ElementType,
    Obstacle,
    PolygonData,
    Pose,
    Transform,
)


def _element(element_id: str, x: float, y: float) -> ElementSpec:
    return ElementSpec(
        id=element_id,
        type=ElementType.TOILET,
        layer="ACC_WC",
        geometry=PolygonData(coordinates=[(-0.5, -0.5), (0.5, -0.5), (0.5, 0.5), (-0.5, 0.5)]),
        transform=Transform(x=x, y=y),
    )


def _obstacle(obstacle_id: str, coordinates: list[tuple[float, float]]) -> Obstacle:
    return Obstacle(id=obstacle_id, polygon=PolygonData(coordinates=coordinates))


def _semantic(
    elements: list[ElementSpec],
    *,
    obstacles: list[Obstacle] | None = None,
) -> DxfSemanticData:
    return DxfSemanticData(
        room=PolygonData(coordinates=[(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0)]),
        obstacles=[] if obstacles is None else obstacles,
        elements=elements,
        entry=Pose(x=0.0, y=0.0),
    )


def _candidate(
    candidate_id: str,
    elements: list[ElementSpec],
    *,
    overrides: dict[str, Transform] | None = None,
) -> LayoutCandidate:
    replacement = {} if overrides is None else overrides
    return LayoutCandidate(
        id=candidate_id,
        placements=[
            ElementPlacement(
                element_id=element.id,
                transform=replacement.get(element.id, element.transform),
            )
            for element in elements
        ],
        changed_element_ids=list(replacement),
    )


def _candidate_set(candidates: list[LayoutCandidate]) -> LayoutCandidateSet:
    return LayoutCandidateSet(generation_strategy="test", candidates=candidates)


def test_valid_candidate_is_accepted() -> None:
    elements = [_element("WC_01", 2.0, 2.0), _element("SINK_01", 5.0, 5.0)]
    result = validate_layout_candidates(
        _semantic(elements),
        _candidate_set([_candidate("baseline", elements)]),
    )

    assert result.valid_candidate_ids == ["baseline"]
    assert result.rejected_candidate_ids == []
    assert result.results[0].issues == []


def test_element_outside_room_is_rejected() -> None:
    elements = [_element("WC_01", 0.25, 2.0)]
    result = validate_layout_candidates(
        _semantic(elements),
        _candidate_set([_candidate("baseline", elements)]),
    )

    assert result.rejected_candidate_ids == ["baseline"]
    assert result.results[0].issues[0].code == "outside_room"
    assert result.results[0].issues[0].element_ids == ["WC_01"]


def test_element_touching_room_boundary_is_allowed() -> None:
    elements = [_element("WC_01", 0.5, 2.0)]
    result = validate_layout_candidates(
        _semantic(elements),
        _candidate_set([_candidate("baseline", elements)]),
    )

    assert result.valid_candidate_ids == ["baseline"]


def test_obstacle_intersection_is_rejected() -> None:
    elements = [_element("WC_01", 2.0, 2.0)]
    obstacle = _obstacle("COLUMN_01", [(1.75, 1.75), (2.25, 1.75), (2.25, 2.25), (1.75, 2.25)])
    result = validate_layout_candidates(
        _semantic(elements, obstacles=[obstacle]),
        _candidate_set([_candidate("baseline", elements)]),
    )

    issue = result.results[0].issues[0]
    assert issue.code == "obstacle_collision"
    assert issue.element_ids == ["WC_01"]
    assert issue.obstacle_id == "COLUMN_01"


def test_touching_obstacle_counts_as_collision() -> None:
    elements = [_element("WC_01", 2.0, 2.0)]
    obstacle = _obstacle("WALL_01", [(2.5, 1.5), (3.0, 1.5), (3.0, 2.5), (2.5, 2.5)])
    result = validate_layout_candidates(
        _semantic(elements, obstacles=[obstacle]),
        _candidate_set([_candidate("baseline", elements)]),
    )

    assert result.results[0].issues[0].code == "obstacle_collision"


def test_element_intersection_is_rejected() -> None:
    elements = [_element("WC_01", 2.0, 2.0), _element("SINK_01", 2.25, 2.0)]
    result = validate_layout_candidates(
        _semantic(elements),
        _candidate_set([_candidate("baseline", elements)]),
    )

    issue = result.results[0].issues[0]
    assert issue.code == "element_collision"
    assert issue.element_ids == ["WC_01", "SINK_01"]


def test_touching_elements_count_as_collision() -> None:
    elements = [_element("WC_01", 2.0, 2.0), _element("SINK_01", 3.0, 2.0)]
    result = validate_layout_candidates(
        _semantic(elements),
        _candidate_set([_candidate("baseline", elements)]),
    )

    assert result.results[0].issues[0].code == "element_collision"


def test_valid_and_rejected_candidates_preserve_input_order() -> None:
    elements = [_element("WC_01", 2.0, 2.0)]
    candidates = [
        _candidate("baseline", elements),
        _candidate(
            "WC_01__001",
            elements,
            overrides={"WC_01": Transform(x=0.0, y=2.0)},
        ),
        _candidate(
            "WC_01__002",
            elements,
            overrides={"WC_01": Transform(x=5.0, y=5.0)},
        ),
    ]

    result = validate_layout_candidates(_semantic(elements), _candidate_set(candidates))

    assert result.valid_candidate_ids == ["baseline", "WC_01__002"]
    assert result.rejected_candidate_ids == ["WC_01__001"]
    assert [item.candidate_id for item in result.results] == [
        "baseline",
        "WC_01__001",
        "WC_01__002",
    ]


def test_issue_order_is_deterministic() -> None:
    elements = [_element("WC_01", 0.25, 2.0), _element("SINK_01", 0.5, 2.0)]
    obstacle = _obstacle("COLUMN_01", [(0.0, 1.5), (1.0, 1.5), (1.0, 2.5), (0.0, 2.5)])
    result = validate_layout_candidates(
        _semantic(elements, obstacles=[obstacle]),
        _candidate_set([_candidate("baseline", elements)]),
    )

    assert [issue.code for issue in result.results[0].issues] == [
        "outside_room",
        "obstacle_collision",
        "obstacle_collision",
        "element_collision",
    ]


def test_missing_candidate_placement_is_rejected() -> None:
    elements = [_element("WC_01", 2.0, 2.0), _element("SINK_01", 5.0, 5.0)]
    candidate = LayoutCandidate(
        id="broken",
        placements=[ElementPlacement(element_id="WC_01", transform=elements[0].transform)],
        changed_element_ids=[],
    )

    with pytest.raises(LayoutValidationError, match="missing: SINK_01"):
        validate_layout_candidates(_semantic(elements), _candidate_set([candidate]))


def test_duplicate_candidate_ids_are_rejected() -> None:
    elements = [_element("WC_01", 2.0, 2.0)]
    candidate = _candidate("baseline", elements)

    with pytest.raises(LayoutValidationError, match="Duplicate candidate IDs"):
        validate_layout_candidates(_semantic(elements), _candidate_set([candidate, candidate]))


def test_validation_does_not_modify_candidates() -> None:
    elements = [_element("WC_01", 2.0, 2.0)]
    candidate_set = _candidate_set([_candidate("baseline", elements)])
    before = candidate_set.model_dump()

    validate_layout_candidates(_semantic(elements), candidate_set)

    assert candidate_set.model_dump() == before


def test_validation_set_serializes_to_json() -> None:
    elements = [_element("WC_01", 2.0, 2.0)]
    result = validate_layout_candidates(
        _semantic(elements),
        _candidate_set([_candidate("baseline", elements)]),
    )

    payload = result.model_dump_json(indent=2)
    assert '"baseline"' in payload
    assert '"room_containment_and_polygon_collisions"' in payload


def test_cli_generates_and_validates_candidates(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    elements = [_element("WC_01", 2.0, 2.0)]
    semantic = _semantic(elements)
    candidate_set = _candidate_set([_candidate("baseline", elements)])
    output = tmp_path / "layout_validation.json"

    monkeypatch.setattr(layout_validation, "semantic_from_dxf", lambda path: semantic)
    monkeypatch.setattr(layout_validation, "generate_layout_candidates", lambda data: candidate_set)
    monkeypatch.setattr(
        "sys.argv",
        ["layout_validation", "input.dxf", "--output", str(output)],
    )

    layout_validation.main()

    assert output.is_file()
    stdout = capsys.readouterr().out
    assert "Candidates checked: 1" in stdout
    assert "Valid candidates: 1" in stdout
    assert "Rejected candidates: 0" in stdout
