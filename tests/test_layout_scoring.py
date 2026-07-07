from pathlib import Path

import pytest

from wheelchair_layout_solver import layout_scoring
from wheelchair_layout_solver.cad.semantic_importer import DxfSemanticData
from wheelchair_layout_solver.candidates import (
    ElementPlacement,
    LayoutCandidate,
    LayoutCandidateSet,
)
from wheelchair_layout_solver.layout_scoring import (
    LayoutScoringError,
    score_valid_layout_candidates,
)
from wheelchair_layout_solver.layout_validation import (
    CandidateLayoutValidation,
    LayoutValidationSet,
)
from wheelchair_layout_solver.models import (
    ElementSpec,
    ElementType,
    ModificationCost,
    PolygonData,
    Pose,
    Transform,
)


def _element(
    element_id: str,
    *,
    transform: Transform | None = None,
    move_cost: float = 0.0,
    rotate_cost: float = 0.0,
) -> ElementSpec:
    return ElementSpec(
        id=element_id,
        type=ElementType.TOILET,
        layer="ACC_WC",
        geometry=PolygonData(coordinates=[(-0.5, -0.5), (0.5, -0.5), (0.0, 0.5)]),
        transform=transform or Transform(x=0.0, y=0.0, rotation_deg=0.0),
        costs=ModificationCost(move=move_cost, rotate=rotate_cost),
    )


def _semantic(elements: list[ElementSpec]) -> DxfSemanticData:
    return DxfSemanticData(
        room=PolygonData(coordinates=[(-10.0, -10.0), (10.0, -10.0), (10.0, 10.0)]),
        elements=elements,
        entry=Pose(x=0.0, y=0.0),
    )


def _candidate(
    candidate_id: str,
    elements: list[ElementSpec],
    transforms: dict[str, Transform] | None = None,
) -> LayoutCandidate:
    transforms = transforms or {}
    placements = [
        ElementPlacement(
            element_id=element.id,
            transform=transforms.get(element.id, element.transform),
        )
        for element in elements
    ]
    changed_ids = [
        element.id
        for element in elements
        if placements[elements.index(element)].transform != element.transform
    ]
    return LayoutCandidate(
        id=candidate_id,
        placements=placements,
        changed_element_ids=changed_ids,
    )


def _candidate_set(candidates: list[LayoutCandidate]) -> LayoutCandidateSet:
    return LayoutCandidateSet(
        generation_strategy="test",
        candidates=candidates,
    )


def _validation(
    candidates: list[LayoutCandidate],
    valid_ids: list[str],
) -> LayoutValidationSet:
    valid_id_set = set(valid_ids)
    return LayoutValidationSet(
        validation_strategy="test",
        results=[
            CandidateLayoutValidation(
                candidate_id=candidate.id,
                valid=candidate.id in valid_id_set,
            )
            for candidate in candidates
        ],
        valid_candidate_ids=valid_ids,
        rejected_candidate_ids=[
            candidate.id for candidate in candidates if candidate.id not in valid_id_set
        ],
    )


def _score_for(scoring_set: layout_scoring.LayoutScoringSet, candidate_id: str) -> float:
    return next(
        candidate.total_score
        for candidate in scoring_set.scored_candidates
        if candidate.candidate_id == candidate_id
    )


def test_only_valid_candidates_are_scored() -> None:
    elements = [_element("WC_01")]
    baseline = _candidate("baseline", elements)
    moved = _candidate(
        "moved",
        elements,
        {"WC_01": Transform(x=1.0, y=0.0, rotation_deg=0.0)},
    )
    candidates = [baseline, moved]

    result = score_valid_layout_candidates(
        _semantic(elements),
        _candidate_set(candidates),
        _validation(candidates, ["moved"]),
    )

    assert [candidate.candidate_id for candidate in result.scored_candidates] == ["moved"]
    assert result.best_candidate_id == "moved"


def test_baseline_has_zero_score() -> None:
    elements = [_element("WC_01")]
    baseline = _candidate("baseline", elements)

    result = score_valid_layout_candidates(
        _semantic(elements),
        _candidate_set([baseline]),
        _validation([baseline], ["baseline"]),
    )

    assert result.scored_candidates[0].total_score == pytest.approx(0.0)


def test_translation_uses_euclidean_distance() -> None:
    elements = [_element("WC_01")]
    moved = _candidate(
        "moved",
        elements,
        {"WC_01": Transform(x=3.0, y=4.0, rotation_deg=0.0)},
    )

    result = score_valid_layout_candidates(
        _semantic(elements),
        _candidate_set([moved]),
        _validation([moved], ["moved"]),
    )

    score = result.scored_candidates[0].element_scores[0]
    assert score.translation_distance_m == pytest.approx(5.0)
    assert score.move_component == pytest.approx(5.0)


def test_rotation_uses_shortest_angular_delta() -> None:
    elements = [_element("WC_01", transform=Transform(rotation_deg=10.0))]
    rotated = _candidate(
        "rotated",
        elements,
        {"WC_01": Transform(rotation_deg=350.0)},
    )

    result = score_valid_layout_candidates(
        _semantic(elements),
        _candidate_set([rotated]),
        _validation([rotated], ["rotated"]),
    )

    score = result.scored_candidates[0].element_scores[0]
    assert score.rotation_delta_deg == pytest.approx(20.0)
    assert score.rotation_component == pytest.approx(20.0 / 90.0)


def test_move_cost_weights_translation_component() -> None:
    elements = [_element("WC_01", move_cost=1.5)]
    moved = _candidate(
        "moved",
        elements,
        {"WC_01": Transform(x=2.0, y=0.0)},
    )

    result = score_valid_layout_candidates(
        _semantic(elements),
        _candidate_set([moved]),
        _validation([moved], ["moved"]),
    )

    assert result.scored_candidates[0].total_score == pytest.approx(5.0)


def test_rotation_cost_weights_quarter_turn_component() -> None:
    elements = [_element("WC_01", rotate_cost=2.0)]
    rotated = _candidate(
        "rotated",
        elements,
        {"WC_01": Transform(rotation_deg=90.0)},
    )

    result = score_valid_layout_candidates(
        _semantic(elements),
        _candidate_set([rotated]),
        _validation([rotated], ["rotated"]),
    )

    assert result.scored_candidates[0].total_score == pytest.approx(3.0)


def test_scores_are_summed_across_elements() -> None:
    elements = [_element("WC_01"), _element("SINK_01")]
    candidate = _candidate(
        "combined",
        elements,
        {
            "WC_01": Transform(x=1.0),
            "SINK_01": Transform(rotation_deg=90.0),
        },
    )

    result = score_valid_layout_candidates(
        _semantic(elements),
        _candidate_set([candidate]),
        _validation([candidate], ["combined"]),
    )

    assert result.scored_candidates[0].total_score == pytest.approx(2.0)


def test_candidates_are_ranked_by_ascending_score() -> None:
    elements = [_element("WC_01")]
    farther = _candidate("farther", elements, {"WC_01": Transform(x=2.0)})
    nearer = _candidate("nearer", elements, {"WC_01": Transform(x=1.0)})
    candidates = [farther, nearer]

    result = score_valid_layout_candidates(
        _semantic(elements),
        _candidate_set(candidates),
        _validation(candidates, ["farther", "nearer"]),
    )

    assert [(item.rank, item.candidate_id) for item in result.scored_candidates] == [
        (1, "nearer"),
        (2, "farther"),
    ]


def test_candidate_id_breaks_score_ties() -> None:
    elements = [_element("WC_01")]
    second = _candidate("B_candidate", elements, {"WC_01": Transform(x=1.0)})
    first = _candidate("A_candidate", elements, {"WC_01": Transform(x=-1.0)})
    candidates = [second, first]

    result = score_valid_layout_candidates(
        _semantic(elements),
        _candidate_set(candidates),
        _validation(candidates, ["B_candidate", "A_candidate"]),
    )

    assert [item.candidate_id for item in result.scored_candidates] == [
        "A_candidate",
        "B_candidate",
    ]


def test_empty_valid_partition_has_no_best_candidate() -> None:
    elements = [_element("WC_01")]
    baseline = _candidate("baseline", elements)

    result = score_valid_layout_candidates(
        _semantic(elements),
        _candidate_set([baseline]),
        _validation([baseline], []),
    )

    assert result.scored_candidates == []
    assert result.best_candidate_id is None


def test_duplicate_candidate_ids_are_rejected() -> None:
    elements = [_element("WC_01")]
    first = _candidate("duplicate", elements)
    second = _candidate("duplicate", elements)

    with pytest.raises(LayoutScoringError, match="Duplicate candidate IDs"):
        score_valid_layout_candidates(
            _semantic(elements),
            _candidate_set([first, second]),
            _validation([first, second], ["duplicate"]),
        )


def test_unknown_validation_candidate_is_rejected() -> None:
    elements = [_element("WC_01")]
    baseline = _candidate("baseline", elements)
    validation = _validation([baseline], ["baseline"])
    validation.valid_candidate_ids = ["unknown"]
    validation.rejected_candidate_ids = ["baseline"]
    validation.results[0].valid = False

    with pytest.raises(LayoutScoringError, match="unknown: unknown"):
        score_valid_layout_candidates(
            _semantic(elements),
            _candidate_set([baseline]),
            validation,
        )


def test_validation_result_order_must_match_candidates() -> None:
    elements = [_element("WC_01")]
    first = _candidate("first", elements)
    second = _candidate("second", elements)
    validation = _validation([second, first], ["first", "second"])

    with pytest.raises(LayoutScoringError, match="candidate order"):
        score_valid_layout_candidates(
            _semantic(elements),
            _candidate_set([first, second]),
            validation,
        )


def test_candidate_changed_ids_must_match_transforms() -> None:
    elements = [_element("WC_01")]
    moved = _candidate("moved", elements, {"WC_01": Transform(x=1.0)})
    moved.changed_element_ids = []

    with pytest.raises(LayoutScoringError, match="changed_element_ids"):
        score_valid_layout_candidates(
            _semantic(elements),
            _candidate_set([moved]),
            _validation([moved], ["moved"]),
        )


def test_scoring_does_not_modify_inputs() -> None:
    elements = [_element("WC_01")]
    moved = _candidate("moved", elements, {"WC_01": Transform(x=1.0)})
    semantic = _semantic(elements)
    candidate_set = _candidate_set([moved])
    validation = _validation([moved], ["moved"])
    original_semantic = semantic.model_dump()
    original_candidates = candidate_set.model_dump()
    original_validation = validation.model_dump()

    score_valid_layout_candidates(semantic, candidate_set, validation)

    assert semantic.model_dump() == original_semantic
    assert candidate_set.model_dump() == original_candidates
    assert validation.model_dump() == original_validation


def test_scoring_set_serializes_to_json() -> None:
    elements = [_element("WC_01")]
    baseline = _candidate("baseline", elements)

    result = score_valid_layout_candidates(
        _semantic(elements),
        _candidate_set([baseline]),
        _validation([baseline], ["baseline"]),
    )

    payload = result.model_dump_json(indent=2)
    assert '"best_candidate_id": "baseline"' in payload
    assert '"total_score": 0.0' in payload


def test_cli_writes_ranked_json(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    elements = [_element("WC_01")]
    semantic = _semantic(elements)
    baseline = _candidate("baseline", elements)
    candidate_set = _candidate_set([baseline])
    validation = _validation([baseline], ["baseline"])
    output = tmp_path / "layout_scoring.json"

    monkeypatch.setattr(layout_scoring, "semantic_from_dxf", lambda _: semantic)
    monkeypatch.setattr(layout_scoring, "generate_layout_candidates", lambda _: candidate_set)
    monkeypatch.setattr(layout_scoring, "validate_layout_candidates", lambda *_: validation)
    monkeypatch.setattr(
        "sys.argv",
        ["layout_scoring", "input.dxf", "--output", str(output)],
    )

    layout_scoring.main()

    assert output.is_file()
    stdout = capsys.readouterr().out
    assert "Valid candidates scored: 1" in stdout
    assert "Best candidate: baseline" in stdout
    assert _score_for(
        layout_scoring.LayoutScoringSet.model_validate_json(output.read_text()),
        "baseline",
    ) == pytest.approx(0.0)
