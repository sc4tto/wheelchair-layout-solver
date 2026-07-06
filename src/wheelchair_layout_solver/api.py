"""FastAPI application for external clients."""

from __future__ import annotations

from fastapi import FastAPI
from pydantic import BaseModel, ConfigDict

from .collision import check_pose
from .models import Pose, PoseCheckResult, Scene
from .path import validate_path

app = FastAPI(
    title="Wheelchair Layout Solver",
    version="0.1.0",
    description="Deterministic 2D wheelchair pose and path checks.",
)


class PoseRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    scene: Scene
    pose: Pose


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/v1/check-pose", response_model=PoseCheckResult)
def check_pose_endpoint(request: PoseRequest) -> PoseCheckResult:
    return check_pose(request.scene, request.pose)


@app.post("/v1/check-path")
def check_path_endpoint(scene: Scene) -> dict[str, object]:
    return validate_path(scene).model_dump(mode="json")
