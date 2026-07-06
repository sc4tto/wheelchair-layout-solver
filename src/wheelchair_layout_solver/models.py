"""Validated data models used by the solver."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class StrictModel(BaseModel):
    """Base model that rejects unknown fields."""

    model_config = ConfigDict(extra="forbid")


class Pose(StrictModel):
    """A wheelchair pose in metres and degrees."""

    x: float
    y: float
    angle_deg: float = 0.0
    reverse: bool = False


class PolygonData(StrictModel):
    """A planar polygon represented by at least three XY coordinates."""

    coordinates: list[tuple[float, float]]

    @field_validator("coordinates")
    @classmethod
    def validate_coordinates(cls, value: list[tuple[float, float]]) -> list[tuple[float, float]]:
        if len(value) < 3:
            raise ValueError("A polygon requires at least three coordinates.")
        return value


class Obstacle(StrictModel):
    """A fixed obstacle in the scene."""

    id: str = Field(min_length=1)
    polygon: PolygonData


class WheelchairSpec(StrictModel):
    """Simplified wheelchair footprint parameters."""

    width: float = Field(gt=0)
    length: float = Field(gt=0)
    safety_margin: float = Field(default=0.0, ge=0)
    reference_offset_x: float = 0.0
    can_rotate_in_place: bool = True
    can_reverse: bool = True
    minimum_turning_radius: float = Field(default=0.0, ge=0)


class PathSettings(StrictModel):
    """Sampling settings for manual path validation."""

    spatial_step: float = Field(default=0.02, gt=0)
    angular_step_deg: float = Field(default=2.0, gt=0)


class Scene(StrictModel):
    """Complete input scene for pose and path checks."""

    schema_version: str = "0.1"
    units: str = "meters"
    room: PolygonData
    obstacles: list[Obstacle] = Field(default_factory=list)
    elements: list[ElementSpec] = Field(default_factory=list)
    wheelchair: WheelchairSpec
    path_settings: PathSettings = Field(default_factory=PathSettings)
    manual_path: list[Pose] = Field(default_factory=list)

    @field_validator("units")
    @classmethod
    def validate_units(cls, value: str) -> str:
        if value != "meters":
            raise ValueError("The internal schema currently accepts only metres.")
        return value


class ElementType(str, Enum):
    """Supported semantic CAD element types."""

    DOOR = "door"
    TOILET = "toilet"
    SINK = "sink"
    BIDET = "bidet"
    SHOWER = "shower"
    OBSTACLE = "obstacle"


class Transform(StrictModel):
    """Nominal position and orientation of a CAD element."""

    x: float = 0.0
    y: float = 0.0
    rotation_deg: float = 0.0


class VariationBounds(StrictModel):
    """Allowed absolute positions and rotations for a movable element."""

    x_min: float | None = None
    x_max: float | None = None
    y_min: float | None = None
    y_max: float | None = None
    rotations_deg: list[float] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_ranges(self) -> VariationBounds:
        if self.x_min is not None and self.x_max is not None:
            if self.x_min > self.x_max:
                raise ValueError("x_min cannot be greater than x_max.")

        if self.y_min is not None and self.y_max is not None:
            if self.y_min > self.y_max:
                raise ValueError("y_min cannot be greater than y_max.")

        if len(self.rotations_deg) != len(set(self.rotations_deg)):
            raise ValueError("rotations_deg cannot contain duplicate values.")

        return self


class DimensionBounds(StrictModel):
    """Allowed dimensional ranges for an element."""

    width_min: float | None = Field(default=None, gt=0)
    width_max: float | None = Field(default=None, gt=0)
    depth_min: float | None = Field(default=None, gt=0)
    depth_max: float | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def validate_ranges(self) -> DimensionBounds:
        if self.width_min is not None and self.width_max is not None:
            if self.width_min > self.width_max:
                raise ValueError("width_min cannot be greater than width_max.")

        if self.depth_min is not None and self.depth_max is not None:
            if self.depth_min > self.depth_max:
                raise ValueError("depth_min cannot be greater than depth_max.")

        return self


class FunctionalRequirements(StrictModel):
    """Initial functional metadata associated with an element."""

    transfer_side: str | None = None
    front_approach: bool | None = None
    knee_clearance: bool | None = None


class ModificationCost(StrictModel):
    """Relative costs used by future layout optimization."""

    move: float = Field(default=0.0, ge=0)
    rotate: float = Field(default=0.0, ge=0)
    resize: float = Field(default=0.0, ge=0)
    replace: float = Field(default=0.0, ge=0)


class ElementSpec(StrictModel):
    """Parametric semantic element imported from CAD."""

    id: str = Field(min_length=1)
    type: ElementType
    layer: str = Field(min_length=1)
    geometry: PolygonData
    transform: Transform = Field(default_factory=Transform)
    movable: bool = False
    variation_bounds: VariationBounds | None = None
    dimension_bounds: DimensionBounds | None = None
    functional: FunctionalRequirements = Field(default_factory=FunctionalRequirements)
    costs: ModificationCost = Field(default_factory=ModificationCost)


class PoseCheckResult(StrictModel):
    """Result of checking one pose."""

    valid: bool
    collision_ids: list[str]
    inside_room: bool
    minimum_clearance: float | None
    footprint: list[tuple[float, float]]


class PathCheckResult(StrictModel):
    """Result of validating a sampled path."""

    valid: bool
    checked_pose_count: int
    first_invalid_index: int | None
    first_invalid_pose: Pose | None
    collision_ids: list[str]
    minimum_clearance: float | None
    sampled_path: list[Pose]
