"""JSON input/output helpers."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from .models import Scene


def load_scene(path: str | Path) -> Scene:
    """Load and validate a scene from JSON."""

    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return Scene.model_validate(data)


def model_to_pretty_json(model: BaseModel) -> str:
    """Serialize a Pydantic model as readable JSON."""

    return json.dumps(model.model_dump(mode="json"), indent=2, ensure_ascii=False)


def write_json(path: str | Path, data: dict[str, Any]) -> None:
    """Write generic JSON using UTF-8."""

    Path(path).write_text(
        json.dumps(data, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
