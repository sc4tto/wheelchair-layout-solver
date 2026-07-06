"""Basic Grasshopper Hops adapter.

Install optional dependencies first:
    python -m pip install -e ".[hops]"
"""

from __future__ import annotations

import json

try:
    import ghhops_server as hs  # type: ignore[import-untyped]
    from flask import Flask
except ImportError as exc:  # pragma: no cover
    raise SystemExit('Install Hops dependencies with: python -m pip install -e ".[hops]"') from exc

from .collision import check_pose
from .models import Pose, Scene

app = Flask(__name__)
hops = hs.Hops(app)


@hops.component(  # type: ignore[untyped-decorator]
    "/check_pose",
    name="Check Wheelchair Pose",
    nickname="CheckPose",
    description="Check a wheelchair pose against a JSON scene.",
    inputs=[
        hs.HopsString("Scene", "S", "Complete scene JSON"),
        hs.HopsNumber("X", "X", "Pose X in metres"),
        hs.HopsNumber("Y", "Y", "Pose Y in metres"),
        hs.HopsNumber("Angle", "A", "Pose angle in degrees"),
    ],
    outputs=[
        hs.HopsString("Result", "R", "Result JSON"),
    ],
)
def check_pose_hops(scene_json: str, x: float, y: float, angle: float) -> str:
    scene = Scene.model_validate_json(scene_json)
    result = check_pose(scene, Pose(x=x, y=y, angle_deg=angle))
    return json.dumps(result.model_dump(mode="json"), ensure_ascii=False)


def main() -> None:
    app.run(host="127.0.0.1", port=5000, debug=False)


if __name__ == "__main__":
    main()
