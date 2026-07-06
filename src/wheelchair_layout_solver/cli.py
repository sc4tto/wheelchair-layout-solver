"""Command-line interface."""

from __future__ import annotations

import argparse

from .collision import check_pose
from .io import load_scene, model_to_pretty_json
from .models import Pose
from .path import validate_path


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="wheelchair-solver")
    subparsers = parser.add_subparsers(dest="command", required=True)

    pose_parser = subparsers.add_parser("check-pose", help="Check one wheelchair pose.")
    pose_parser.add_argument("scene")
    pose_parser.add_argument("--x", type=float, required=True)
    pose_parser.add_argument("--y", type=float, required=True)
    pose_parser.add_argument("--angle", type=float, default=0.0)

    path_parser = subparsers.add_parser("check-path", help="Validate the scene manual path.")
    path_parser.add_argument("scene")

    serve_parser = subparsers.add_parser("serve", help="Run the local FastAPI service.")
    serve_parser.add_argument("--host", default="127.0.0.1")
    serve_parser.add_argument("--port", type=int, default=8000)

    return parser


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()

    if args.command == "check-pose":
        scene = load_scene(args.scene)
        result = check_pose(scene, Pose(x=args.x, y=args.y, angle_deg=args.angle))
        print(model_to_pretty_json(result))
        return

    if args.command == "check-path":
        scene = load_scene(args.scene)
        print(model_to_pretty_json(validate_path(scene)))
        return

    if args.command == "serve":
        try:
            import uvicorn
        except ImportError as exc:
            raise SystemExit(
                'Install API dependencies with: python -m pip install -e ".[api]"'
            ) from exc
        uvicorn.run(
            "wheelchair_layout_solver.api:app",
            host=args.host,
            port=args.port,
            reload=False,
        )
        return

    parser.error(f"Unknown command: {args.command}")


if __name__ == "__main__":
    main()
