"""Generate deterministic layout candidate transforms from semantic CAD data."""

from __future__ import annotations

import math
from pathlib import Path

from pydantic import Field

from wheelchair_layout_solver.cad.semantic_importer import DxfSemanticData, semantic_from_dxf
from wheelchair_layout_solver.models import ElementSpec, StrictModel, Transform, VariationBounds


class CandidateGenerationError(ValueError):
    """Raised when semantic variation data cannot generate valid candidates."""


class ElementPlacement(StrictModel):
    """A candidate transform for one semantic element."""

    element_id: str
    transform: Transform


class LayoutCandidate(StrictModel):
    """One complete set of element transforms."""

    id: str
    placements: list[ElementPlacement]
    changed_element_ids: list[str]


class LayoutCandidateSet(StrictModel):
    """A deterministic collection of generated layout candidates."""

    generation_strategy: str
    candidates: list[LayoutCandidate]
    warnings: list[str] = Field(default_factory=list)


def _ensure_finite(value: float, *, label: str) -> None:
    if not math.isfinite(value):
        raise CandidateGenerationError(f"{label} must be finite, got {value!r}.")


def _copy_transform(transform: Transform) -> Transform:
    return Transform(
        x=float(transform.x),
        y=float(transform.y),
        rotation_deg=float(transform.rotation_deg),
    )


def _dedupe(values: list[float]) -> list[float]:
    result: list[float] = []
    seen: set[float] = set()
    for value in values:
        _ensure_finite(value, label="candidate sample")
        if value not in seen:
            result.append(float(value))
            seen.add(value)
    return result


def _validate_bounds(
    bounds: VariationBounds,
    *,
    element_id: str,
    nominal: Transform,
) -> None:
    for field_name in ("x_min", "x_max", "y_min", "y_max"):
        value = getattr(bounds, field_name)
        if value is not None:
            _ensure_finite(value, label=f"{element_id}.{field_name}")

    if bounds.x_min is not None and bounds.x_max is not None and bounds.x_min > bounds.x_max:
        raise CandidateGenerationError(f"Element {element_id} has inverted x bounds.")

    if bounds.y_min is not None and bounds.y_max is not None and bounds.y_min > bounds.y_max:
        raise CandidateGenerationError(f"Element {element_id} has inverted y bounds.")

    if bounds.x_min is not None and nominal.x < bounds.x_min:
        raise CandidateGenerationError(
            f"Element {element_id} nominal x is outside variation bounds."
        )

    if bounds.x_max is not None and nominal.x > bounds.x_max:
        raise CandidateGenerationError(
            f"Element {element_id} nominal x is outside variation bounds."
        )

    if bounds.y_min is not None and nominal.y < bounds.y_min:
        raise CandidateGenerationError(
            f"Element {element_id} nominal y is outside variation bounds."
        )

    if bounds.y_max is not None and nominal.y > bounds.y_max:
        raise CandidateGenerationError(
            f"Element {element_id} nominal y is outside variation bounds."
        )

    for rotation in bounds.rotations_deg:
        _ensure_finite(rotation, label=f"{element_id}.rotation")


def _samples_for_axis(
    minimum: float | None,
    nominal: float,
    maximum: float | None,
) -> list[float]:
    values: list[float] = []
    if minimum is not None:
        values.append(minimum)
    values.append(nominal)
    if maximum is not None:
        values.append(maximum)
    return _dedupe(values)


def _rotation_samples(bounds: VariationBounds, nominal: Transform) -> list[float]:
    if bounds.rotations_deg:
        return _dedupe(bounds.rotations_deg)
    return _dedupe([nominal.rotation_deg])


def _placement_for(element: ElementSpec, transform: Transform) -> ElementPlacement:
    return ElementPlacement(element_id=element.id, transform=_copy_transform(transform))


def _placements_for(
    elements: list[ElementSpec],
    changed_element_id: str | None = None,
    changed_transform: Transform | None = None,
) -> list[ElementPlacement]:
    placements: list[ElementPlacement] = []
    for element in elements:
        transform = (
            changed_transform
            if changed_element_id == element.id and changed_transform is not None
            else element.transform
        )
        placements.append(_placement_for(element, transform))
    return placements


def _validate_candidate(candidate: LayoutCandidate, elements: list[ElementSpec]) -> None:
    expected_ids = [element.id for element in elements]
    placement_ids = [placement.element_id for placement in candidate.placements]

    if len(placement_ids) != len(set(placement_ids)):
        raise CandidateGenerationError(f"Candidate {candidate.id} has duplicate placements.")

    if placement_ids != expected_ids:
        raise CandidateGenerationError(f"Candidate {candidate.id} does not place every element.")


def _validate_element_ids(elements: list[ElementSpec]) -> None:
    element_ids = [element.id for element in elements]
    duplicates = {element_id for element_id in element_ids if element_ids.count(element_id) > 1}
    if duplicates:
        duplicate_list = ", ".join(sorted(duplicates))
        raise CandidateGenerationError(f"Duplicate element IDs: {duplicate_list}.")


def _is_nominal(transform: Transform, nominal: Transform) -> bool:
    return (
        transform.x == nominal.x
        and transform.y == nominal.y
        and transform.rotation_deg == nominal.rotation_deg
    )


def transformed_coordinates(
    element: ElementSpec,
    transform: Transform,
) -> list[tuple[float, float]]:
    """Transform local element coordinates into world coordinates."""

    radians = math.radians(transform.rotation_deg)
    cos_angle = math.cos(radians)
    sin_angle = math.sin(radians)
    coordinates: list[tuple[float, float]] = []

    for local_x, local_y in element.geometry.coordinates:
        rotated_x = local_x * cos_angle - local_y * sin_angle
        rotated_y = local_x * sin_angle + local_y * cos_angle
        coordinates.append((float(rotated_x + transform.x), float(rotated_y + transform.y)))

    return coordinates


def generate_layout_candidates(
    semantic: DxfSemanticData,
) -> LayoutCandidateSet:
    """Generate deterministic one-element-at-a-time layout candidates."""

    elements = semantic.elements
    _validate_element_ids(elements)

    baseline = LayoutCandidate(
        id="baseline",
        placements=_placements_for(elements),
        changed_element_ids=[],
    )
    _validate_candidate(baseline, elements)
    candidates = [baseline]

    for element in elements:
        _ensure_finite(element.transform.x, label=f"{element.id}.transform.x")
        _ensure_finite(element.transform.y, label=f"{element.id}.transform.y")
        _ensure_finite(element.transform.rotation_deg, label=f"{element.id}.transform.rotation_deg")

        bounds = element.variation_bounds
        if not element.movable or bounds is None:
            continue

        _validate_bounds(bounds, element_id=element.id, nominal=element.transform)
        x_samples = _samples_for_axis(bounds.x_min, element.transform.x, bounds.x_max)
        y_samples = _samples_for_axis(bounds.y_min, element.transform.y, bounds.y_max)
        rotation_samples = _rotation_samples(bounds, element.transform)

        element_candidate_index = 1
        for x_value in x_samples:
            for y_value in y_samples:
                for rotation in rotation_samples:
                    transform = Transform(x=x_value, y=y_value, rotation_deg=rotation)
                    if _is_nominal(transform, element.transform):
                        continue

                    candidate = LayoutCandidate(
                        id=f"{element.id}__{element_candidate_index:03d}",
                        placements=_placements_for(
                            elements,
                            changed_element_id=element.id,
                            changed_transform=transform,
                        ),
                        changed_element_ids=[element.id],
                    )
                    _validate_candidate(candidate, elements)
                    candidates.append(candidate)
                    element_candidate_index += 1

    return LayoutCandidateSet(
        generation_strategy="deterministic_one_element_at_a_time",
        candidates=candidates,
    )


def main() -> None:
    """Run the layout candidate generator from a DXF file."""

    import argparse

    parser = argparse.ArgumentParser(description="Generate deterministic layout candidates.")
    parser.add_argument("path", type=Path)
    parser.add_argument("--output", type=Path, default=Path("layout_candidates.json"))
    arguments = parser.parse_args()

    semantic = semantic_from_dxf(arguments.path)
    candidate_set = generate_layout_candidates(semantic)
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(candidate_set.model_dump_json(indent=2), encoding="utf-8")
    print(f"Layout candidates saved to: {arguments.output}")
    print(f"Candidates generated: {len(candidate_set.candidates)}")


if __name__ == "__main__":
    main()
