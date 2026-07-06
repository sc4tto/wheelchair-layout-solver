"""Tests for parametric CAD element models."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from wheelchair_layout_solver.models import (
    DimensionBounds,
    ElementSpec,
    ElementType,
    PolygonData,
    Scene,
    Transform,
    VariationBounds,
)


def test_valid_parametric_element() -> None:
    element = ElementSpec(
        id="WC_01",
        type=ElementType.TOILET,
        layer="ACC_WC",
        geometry=PolygonData(
            coordinates=[
                (0.0, 0.0),
                (0.4, 0.0),
                (0.4, 0.6),
                (0.0, 0.6),
            ]
        ),
        transform=Transform(
            x=1.25,
            y=0.40,
            rotation_deg=90.0,
        ),
        movable=True,
        variation_bounds=VariationBounds(
            x_min=1.20,
            x_max=1.35,
            y_min=0.35,
            y_max=0.50,
            rotations_deg=[0.0, 90.0, 180.0, 270.0],
        ),
    )

    assert element.id == "WC_01"
    assert element.type is ElementType.TOILET
    assert element.movable is True
    assert element.transform.rotation_deg == 90.0


def test_variation_bounds_reject_invalid_x_range() -> None:
    with pytest.raises(ValidationError, match="x_min cannot be greater"):
        VariationBounds(x_min=2.0, x_max=1.0)


def test_variation_bounds_reject_duplicate_rotations() -> None:
    with pytest.raises(ValidationError, match="duplicate"):
        VariationBounds(rotations_deg=[0.0, 90.0, 90.0])


def test_dimension_bounds_reject_invalid_width_range() -> None:
    with pytest.raises(ValidationError, match="width_min cannot be greater"):
        DimensionBounds(width_min=0.70, width_max=0.50)


def test_scene_v01_remains_compatible() -> None:
    scene = Scene.model_validate(
        {
            "schema_version": "0.1",
            "units": "meters",
            "room": {
                "coordinates": [
                    [0.0, 0.0],
                    [3.0, 0.0],
                    [3.0, 2.5],
                    [0.0, 2.5],
                ]
            },
            "wheelchair": {
                "width": 0.70,
                "length": 1.20,
            },
        }
    )

    assert scene.schema_version == "0.1"
    assert scene.elements == []


def test_scene_v02_accepts_elements() -> None:
    scene = Scene.model_validate(
        {
            "schema_version": "0.2",
            "units": "meters",
            "room": {
                "coordinates": [
                    [0.0, 0.0],
                    [3.0, 0.0],
                    [3.0, 2.5],
                    [0.0, 2.5],
                ]
            },
            "elements": [
                {
                    "id": "SINK_01",
                    "type": "sink",
                    "layer": "ACC_SINK",
                    "geometry": {
                        "coordinates": [
                            [0.0, 0.0],
                            [0.6, 0.0],
                            [0.6, 0.5],
                            [0.0, 0.5],
                        ]
                    },
                    "movable": True,
                }
            ],
            "wheelchair": {
                "width": 0.70,
                "length": 1.20,
            },
        }
    )

    assert scene.schema_version == "0.2"
    assert len(scene.elements) == 1
    assert scene.elements[0].id == "SINK_01"
    assert scene.elements[0].type is ElementType.SINK
