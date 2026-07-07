"""Score valid layout candidates by deterministic geometric modification cost."""

from __future__ import annotations

import math
from pathlib import Path

from pydantic import Field

from wheelchair_layout_solver.cad.semantic_importer import DxfSemanticData, semantic_from_dxf
from wheelchair_layout_solver.candidates import (
    LayoutCandidate,
    LayoutCandidateSet,
    generate_layout_candidates,
)
from wheelchair_layout_solver.layout_validation import (
    LayoutValidationSet,
    validate_layout_candidates,
)
from wheelchair_layout_solver.models import ElementSpec, StrictModel, Transform


class LayoutScoringError(ValueError):
    """Raised when candidate and validation data cannot be scored consistently."""


class ElementScoreBreakdown(StrictModel):
    """Score contribution for one semantic element in one candidate."""

    element_id: str
    translation_distance_m: float = Field(ge=0)
    rotation_delta_deg: float = Field(ge=0, le=180)
    move_component: float = Field(ge=0)
    rotation_component: float = Field(ge=0)
    subtotal: float = Field(ge=0)


class ScoredLayoutCandidate(StrictModel):
    """One valid layout candidate with a deterministic rank and score."""

    rank: int = Field(ge=1)
    candidate_id: str
    total_score: float = Field(ge=0)
    changed_element_ids: list[str]
    element_scores: list[ElementScoreBreakdown]


class LayoutScoringSet(StrictModel):
    """Ranked valid candidates and scoring metadata."""

    scoring_strategy: str
    scored_candidates: list[ScoredLayoutCandidate]
    best_candidate_id: str | None = None
    warnings: list[str] = Field(default_factory=list)


def _duplicate_values(values: list[str]) -> list[str]:
    seen: set[str] = set()
    duplicates: set[str] = set()
    for value in values:
        if value in seen:
            duplicates.add(value)
        seen.add(value)
    return sorted(duplicates)


def _clean_float(value: float) -> float:
    rounded = round(float(value), 12)
    return 0.0 if rounded == 0 else rounded


def _shortest_rotation_delta_deg(actual: float, nominal: float) -> float:
    if not math.isfinite(actual) or not math.isfinite(nominal):
        raise LayoutScoringError("Rotation values must be finite.")
    delta = (actual - nominal + 180.0) % 360.0 - 180.0
    return _clean_float(abs(delta))


def _validate_unique_ids(semantic: DxfSemanticData, candidate_set: LayoutCandidateSet) -> None:
    element_duplicates = _duplicate_values([element.id for element in semantic.elements])
    if element_duplicates:
        joined = ", ".join(element_duplicates)
        raise LayoutScoringError(f"Duplicate semantic element IDs: {joined}.")

    candidate_duplicates = _duplicate_values(
        [candidate.id for candidate in candidate_set.candidates]
    )
    if candidate_duplicates:
        joined = ", ".join(candidate_duplicates)
        raise LayoutScoringError(f"Duplicate candidate IDs: {joined}.")


def _validate_validation_partition(
    candidate_set: LayoutCandidateSet,
    validation_set: LayoutValidationSet,
) -> None:
    candidate_ids = [candidate.id for candidate in candidate_set.candidates]
    candidate_id_set = set(candidate_ids)
    valid_ids = validation_set.valid_candidate_ids
    rejected_ids = validation_set.rejected_candidate_ids

    duplicate_valid = _duplicate_values(valid_ids)
    duplicate_rejected = _duplicate_values(rejected_ids)
    if duplicate_valid or duplicate_rejected:
        raise LayoutScoringError("Validation candidate partitions contain duplicate IDs.")

    overlap = sorted(set(valid_ids) & set(rejected_ids))
    if overlap:
        joined = ", ".join(overlap)
        raise LayoutScoringError(f"Validation partitions overlap: {joined}.")

    partition_ids = set(valid_ids) | set(rejected_ids)
    missing = [candidate_id for candidate_id in candidate_ids if candidate_id not in partition_ids]
    unknown = sorted(partition_ids - candidate_id_set)
    if missing or unknown:
        details: list[str] = []
        if missing:
            details.append(f"missing: {', '.join(missing)}")
        if unknown:
            details.append(f"unknown: {', '.join(unknown)}")
        raise LayoutScoringError(
            f"Validation partitions do not match candidate IDs ({'; '.join(details)})."
        )

    result_ids = [result.candidate_id for result in validation_set.results]
    duplicate_results = _duplicate_values(result_ids)
    if duplicate_results:
        joined = ", ".join(duplicate_results)
        raise LayoutScoringError(f"Duplicate validation result IDs: {joined}.")
    if result_ids != candidate_ids:
        raise LayoutScoringError("Validation results must match candidate order exactly.")

    valid_id_set = set(valid_ids)
    for result in validation_set.results:
        expected_valid = result.candidate_id in valid_id_set
        if result.valid != expected_valid:
            raise LayoutScoringError(
                f"Validation result for {result.candidate_id} disagrees with its partition."
            )


def _candidate_transform_map(
    candidate: LayoutCandidate,
    elements: list[ElementSpec],
) -> dict[str, Transform]:
    placement_ids = [placement.element_id for placement in candidate.placements]
    duplicates = _duplicate_values(placement_ids)
    if duplicates:
        joined = ", ".join(duplicates)
        raise LayoutScoringError(
            f"Candidate {candidate.id} has duplicate element placements: {joined}."
        )

    expected_ids = [element.id for element in elements]
    if placement_ids != expected_ids:
        raise LayoutScoringError(
            f"Candidate {candidate.id} placements must match semantic element order."
        )

    return {placement.element_id: placement.transform for placement in candidate.placements}


def _score_element(element: ElementSpec, transform: Transform) -> ElementScoreBreakdown:
    values = (
        transform.x,
        transform.y,
        transform.rotation_deg,
        element.transform.x,
        element.transform.y,
        element.transform.rotation_deg,
    )
    if not all(math.isfinite(value) for value in values):
        raise LayoutScoringError(f"Element {element.id} has non-finite transform data.")

    translation_distance = _clean_float(
        math.hypot(
            transform.x - element.transform.x,
            transform.y - element.transform.y,
        )
    )
    rotation_delta = _shortest_rotation_delta_deg(
        transform.rotation_deg,
        element.transform.rotation_deg,
    )
    move_component = _clean_float(translation_distance * (1.0 + element.costs.move))
    rotation_component = _clean_float((rotation_delta / 90.0) * (1.0 + element.costs.rotate))
    subtotal = _clean_float(move_component + rotation_component)

    return ElementScoreBreakdown(
        element_id=element.id,
        translation_distance_m=translation_distance,
        rotation_delta_deg=rotation_delta,
        move_component=move_component,
        rotation_component=rotation_component,
        subtotal=subtotal,
    )


def _score_candidate(
    semantic: DxfSemanticData,
    candidate: LayoutCandidate,
) -> tuple[float, list[ElementScoreBreakdown]]:
    transforms = _candidate_transform_map(candidate, semantic.elements)
    element_scores = [
        _score_element(element, transforms[element.id]) for element in semantic.elements
    ]
    actual_changed_ids = [
        element.id for element in semantic.elements if transforms[element.id] != element.transform
    ]
    if candidate.changed_element_ids != actual_changed_ids:
        raise LayoutScoringError(
            f"Candidate {candidate.id} changed_element_ids do not match its transforms."
        )
    return _clean_float(sum(score.subtotal for score in element_scores)), element_scores


def _merge_warnings(*warning_groups: list[str]) -> list[str]:
    merged: list[str] = []
    seen: set[str] = set()
    for warnings in warning_groups:
        for warning in warnings:
            if warning not in seen:
                merged.append(warning)
                seen.add(warning)
    return merged


def score_valid_layout_candidates(
    semantic: DxfSemanticData,
    candidate_set: LayoutCandidateSet,
    validation_set: LayoutValidationSet,
) -> LayoutScoringSet:
    """Score and rank only geometrically valid layout candidates."""

    _validate_unique_ids(semantic, candidate_set)
    _validate_validation_partition(candidate_set, validation_set)

    valid_id_set = set(validation_set.valid_candidate_ids)
    scored_rows: list[tuple[float, str, LayoutCandidate, list[ElementScoreBreakdown]]] = []
    for candidate in candidate_set.candidates:
        if candidate.id not in valid_id_set:
            continue
        total_score, element_scores = _score_candidate(semantic, candidate)
        scored_rows.append((total_score, candidate.id, candidate, element_scores))

    scored_rows.sort(key=lambda row: (row[0], row[1]))
    scored_candidates = [
        ScoredLayoutCandidate(
            rank=index,
            candidate_id=candidate.id,
            total_score=total_score,
            changed_element_ids=list(candidate.changed_element_ids),
            element_scores=element_scores,
        )
        for index, (total_score, _, candidate, element_scores) in enumerate(
            scored_rows,
            start=1,
        )
    ]

    return LayoutScoringSet(
        scoring_strategy="translation_m_and_quarter_turns_weighted_by_modification_costs",
        scored_candidates=scored_candidates,
        best_candidate_id=(scored_candidates[0].candidate_id if scored_candidates else None),
        warnings=_merge_warnings(candidate_set.warnings, validation_set.warnings),
    )


def main() -> None:
    """Generate, validate, score, and rank layout candidates from a DXF file."""

    import argparse

    parser = argparse.ArgumentParser(description="Score valid layout candidates.")
    parser.add_argument("path", type=Path)
    parser.add_argument("--output", type=Path, default=Path("layout_scoring.json"))
    arguments = parser.parse_args()

    semantic = semantic_from_dxf(arguments.path)
    candidate_set = generate_layout_candidates(semantic)
    validation_set = validate_layout_candidates(semantic, candidate_set)
    scoring_set = score_valid_layout_candidates(semantic, candidate_set, validation_set)
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(scoring_set.model_dump_json(indent=2), encoding="utf-8")

    print(f"Layout scoring saved to: {arguments.output}")
    print(f"Valid candidates scored: {len(scoring_set.scored_candidates)}")
    print(f"Best candidate: {scoring_set.best_candidate_id or 'none'}")
    if scoring_set.scored_candidates:
        print(f"Best score: {scoring_set.scored_candidates[0].total_score}")


if __name__ == "__main__":
    main()
