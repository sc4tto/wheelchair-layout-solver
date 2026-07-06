"""Validate generated layout candidates against room and collision geometry."""

from __future__ import annotations

from itertools import combinations
from pathlib import Path
from typing import Literal

from pydantic import Field
from shapely.geometry import Polygon  # type: ignore[import-untyped]

from wheelchair_layout_solver.cad.semantic_importer import DxfSemanticData, semantic_from_dxf
from wheelchair_layout_solver.candidates import (
    LayoutCandidate,
    LayoutCandidateSet,
    generate_layout_candidates,
    transformed_coordinates,
)
from wheelchair_layout_solver.geometry import polygon_from_data
from wheelchair_layout_solver.models import ElementSpec, PolygonData, StrictModel, Transform

LayoutValidationCode = Literal[
    "outside_room",
    "obstacle_collision",
    "element_collision",
]


class LayoutValidationError(ValueError):
    """Raised when a candidate set cannot be validated consistently."""


class LayoutValidationIssue(StrictModel):
    """One deterministic reason why a layout candidate is invalid."""

    code: LayoutValidationCode
    element_ids: list[str]
    obstacle_id: str | None = None


class CandidateLayoutValidation(StrictModel):
    """Validation result for one complete layout candidate."""

    candidate_id: str
    valid: bool
    issues: list[LayoutValidationIssue] = Field(default_factory=list)


class LayoutValidationSet(StrictModel):
    """Validation results with deterministic valid and rejected partitions."""

    validation_strategy: str
    results: list[CandidateLayoutValidation]
    valid_candidate_ids: list[str]
    rejected_candidate_ids: list[str]
    warnings: list[str] = Field(default_factory=list)


def _duplicate_values(values: list[str]) -> list[str]:
    seen: set[str] = set()
    duplicates: set[str] = set()
    for value in values:
        if value in seen:
            duplicates.add(value)
        seen.add(value)
    return sorted(duplicates)


def _validate_semantic_ids(semantic: DxfSemanticData) -> None:
    element_duplicates = _duplicate_values([element.id for element in semantic.elements])
    if element_duplicates:
        joined = ", ".join(element_duplicates)
        raise LayoutValidationError(f"Duplicate semantic element IDs: {joined}.")

    obstacle_duplicates = _duplicate_values([obstacle.id for obstacle in semantic.obstacles])
    if obstacle_duplicates:
        joined = ", ".join(obstacle_duplicates)
        raise LayoutValidationError(f"Duplicate obstacle IDs: {joined}.")


def _candidate_transform_map(
    candidate: LayoutCandidate,
    elements: list[ElementSpec],
) -> dict[str, Transform]:
    placement_ids = [placement.element_id for placement in candidate.placements]
    duplicates = _duplicate_values(placement_ids)
    if duplicates:
        joined = ", ".join(duplicates)
        raise LayoutValidationError(
            f"Candidate {candidate.id} has duplicate element placements: {joined}."
        )

    expected_ids = [element.id for element in elements]
    expected_set = set(expected_ids)
    placement_set = set(placement_ids)
    missing = [element_id for element_id in expected_ids if element_id not in placement_set]
    unknown = [element_id for element_id in placement_ids if element_id not in expected_set]
    if missing or unknown:
        details: list[str] = []
        if missing:
            details.append(f"missing: {', '.join(missing)}")
        if unknown:
            details.append(f"unknown: {', '.join(unknown)}")
        detail_text = "; ".join(details)
        raise LayoutValidationError(
            f"Candidate {candidate.id} placements do not match semantic elements "
            f"({detail_text})."
        )

    return {placement.element_id: placement.transform for placement in candidate.placements}


def _element_polygon(element: ElementSpec, transform: Transform) -> Polygon:
    coordinates = transformed_coordinates(element, transform)
    try:
        return polygon_from_data(PolygonData(coordinates=coordinates))
    except ValueError as exc:
        raise LayoutValidationError(
            f"Element {element.id} produces invalid geometry after transformation."
        ) from exc


def _validate_candidate(
    semantic: DxfSemanticData,
    candidate: LayoutCandidate,
    room: Polygon,
    obstacle_polygons: list[tuple[str, Polygon]],
) -> CandidateLayoutValidation:
    transforms = _candidate_transform_map(candidate, semantic.elements)
    element_polygons = [
        (element.id, _element_polygon(element, transforms[element.id]))
        for element in semantic.elements
    ]
    issues: list[LayoutValidationIssue] = []

    for element_id, polygon in element_polygons:
        if not room.covers(polygon):
            issues.append(
                LayoutValidationIssue(code="outside_room", element_ids=[element_id])
            )

    for element_id, polygon in element_polygons:
        for obstacle_id, obstacle_polygon in obstacle_polygons:
            if polygon.intersects(obstacle_polygon):
                issues.append(
                    LayoutValidationIssue(
                        code="obstacle_collision",
                        element_ids=[element_id],
                        obstacle_id=obstacle_id,
                    )
                )

    for (first_id, first_polygon), (second_id, second_polygon) in combinations(
        element_polygons,
        2,
    ):
        if first_polygon.intersects(second_polygon):
            issues.append(
                LayoutValidationIssue(
                    code="element_collision",
                    element_ids=[first_id, second_id],
                )
            )

    return CandidateLayoutValidation(
        candidate_id=candidate.id,
        valid=not issues,
        issues=issues,
    )


def validate_layout_candidates(
    semantic: DxfSemanticData,
    candidate_set: LayoutCandidateSet,
) -> LayoutValidationSet:
    """Validate candidates without modifying semantic data or candidate transforms."""

    _validate_semantic_ids(semantic)
    candidate_ids = [candidate.id for candidate in candidate_set.candidates]
    duplicate_candidate_ids = _duplicate_values(candidate_ids)
    if duplicate_candidate_ids:
        joined = ", ".join(duplicate_candidate_ids)
        raise LayoutValidationError(f"Duplicate candidate IDs: {joined}.")

    try:
        room = polygon_from_data(semantic.room)
        obstacle_polygons = [
            (obstacle.id, polygon_from_data(obstacle.polygon))
            for obstacle in semantic.obstacles
        ]
    except ValueError as exc:
        raise LayoutValidationError("Semantic room or obstacle geometry is invalid.") from exc

    results = [
        _validate_candidate(semantic, candidate, room, obstacle_polygons)
        for candidate in candidate_set.candidates
    ]
    valid_candidate_ids = [result.candidate_id for result in results if result.valid]
    rejected_candidate_ids = [result.candidate_id for result in results if not result.valid]

    return LayoutValidationSet(
        validation_strategy="room_containment_and_polygon_collisions",
        results=results,
        valid_candidate_ids=valid_candidate_ids,
        rejected_candidate_ids=rejected_candidate_ids,
        warnings=list(candidate_set.warnings),
    )


def main() -> None:
    """Generate and validate layout candidates from a DXF file."""

    import argparse

    parser = argparse.ArgumentParser(description="Validate generated layout candidates.")
    parser.add_argument("path", type=Path)
    parser.add_argument("--output", type=Path, default=Path("layout_validation.json"))
    arguments = parser.parse_args()

    semantic = semantic_from_dxf(arguments.path)
    candidate_set = generate_layout_candidates(semantic)
    validation_set = validate_layout_candidates(semantic, candidate_set)
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(validation_set.model_dump_json(indent=2), encoding="utf-8")
    print(f"Layout validation saved to: {arguments.output}")
    print(f"Candidates checked: {len(validation_set.results)}")
    print(f"Valid candidates: {len(validation_set.valid_candidate_ids)}")
    print(f"Rejected candidates: {len(validation_set.rejected_candidate_ids)}")


if __name__ == "__main__":
    main()
