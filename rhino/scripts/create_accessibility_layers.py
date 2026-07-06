"""Create the standard Wheelchair Layout Solver layers in Rhino.

The script reads the layer definitions from:
config/element_classes.json

When the configuration file cannot be found automatically, Rhino asks the
user to select it manually.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import rhinoscriptsyntax as rs
from System.Drawing import Color

LAYER_COLORS = {
    "room": Color.FromArgb(40, 40, 40),
    "wall": Color.FromArgb(90, 90, 90),
    "obstacle": Color.FromArgb(180, 60, 60),
    "door": Color.FromArgb(220, 140, 40),
    "toilet": Color.FromArgb(70, 120, 220),
    "sink": Color.FromArgb(70, 180, 220),
    "bidet": Color.FromArgb(100, 150, 220),
    "shower": Color.FromArgb(70, 190, 170),
    "entry": Color.FromArgb(70, 180, 80),
    "target": Color.FromArgb(180, 80, 200),
    "functional_area": Color.FromArgb(220, 200, 60),
}


def find_config_file() -> Path | None:
    """Find element_classes.json relative to this script."""

    if "__file__" in globals():
        script_path = Path(__file__).resolve()

        candidates = [
            script_path.parents[2] / "config" / "element_classes.json",
            script_path.parent / "element_classes.json",
        ]

        for candidate in candidates:
            if candidate.exists():
                return candidate

    selected = rs.OpenFileName(
        title="Select element_classes.json",
        filter="JSON files (*.json)|*.json||",
    )

    return Path(selected) if selected else None


def load_config(path: Path) -> dict[str, Any]:
    """Read and validate the layer configuration."""

    with path.open("r", encoding="utf-8") as file:
        config = json.load(file)

    layers = config.get("layers")

    if not isinstance(layers, list):
        raise ValueError("The configuration file must contain a 'layers' list.")

    return config


def create_or_update_layer(layer_data: dict[str, Any]) -> str:
    """Create one Rhino layer or update its basic properties."""

    name = str(layer_data["name"])
    element_class = str(layer_data.get("class", "unknown"))

    color = LAYER_COLORS.get(
        element_class,
        Color.FromArgb(160, 160, 160),
    )

    if rs.IsLayer(name):
        rs.LayerColor(name, color)
        print(f"Updated layer: {name}")
        return name

    created_layer = rs.AddLayer(
        name=name,
        color=color,
        visible=True,
        locked=False,
    )

    if not created_layer:
        raise RuntimeError(f"Rhino could not create layer '{name}'.")

    print(f"Created layer: {name}")
    return created_layer


def create_accessibility_layers() -> None:
    """Create all configured accessibility layers."""

    config_path = find_config_file()

    if config_path is None:
        print("Operation cancelled: configuration file not selected.")
        return

    try:
        config = load_config(config_path)

        created_layers = []

        for layer_data in config["layers"]:
            created_layers.append(create_or_update_layer(layer_data))

        print("")
        print("Accessibility layer setup completed.")
        print(f"Configuration: {config_path}")
        print(f"Layers processed: {len(created_layers)}")

        rs.Redraw()

    except Exception as error:
        print(f"Layer setup failed: {error}")
        raise


if __name__ == "__main__":
    create_accessibility_layers()
