"""Validated data models used by the solver."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator


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
    def validate_coordinates(
        cls, value: list[tuple[float, float]]
    ) -> list[tuple[float, float]]:
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
    wheelchair: WheelchairSpec
    path_settings: PathSettings = Field(default_factory=PathSettings)
    manual_path: list[Pose] = Field(default_factory=list)

    @field_validator("units")
    @classmethod
    def validate_units(cls, value: str) -> str:
        if value != "meters":
            raise ValueError("The internal schema currently accepts only metres.")
        return value


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
