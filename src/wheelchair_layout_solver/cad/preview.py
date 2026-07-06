"""Render 2D previews for inspected DXF accessibility layouts."""

from __future__ import annotations

from pathlib import Path
from typing import Final

import matplotlib.pyplot as plt
from matplotlib.axes import Axes
from matplotlib.patches import Polygon as MatplotlibPolygon

from .dxf_importer import DxfEntitySummary, DxfInspection, inspect_dxf

_LayerStyle = dict[str, str | float]

_DEFAULT_STYLE: Final[_LayerStyle] = {
    "edgecolor": "#4b5563",
    "facecolor": "#e5e7eb",
    "alpha": 0.35,
}

_LAYER_STYLES: Final[dict[str, _LayerStyle]] = {
    "ACC_ROOM": {
        "edgecolor": "#111827",
        "facecolor": "#f9fafb",
        "alpha": 0.18,
    },
    "ACC_WC": {
        "edgecolor": "#2563eb",
        "facecolor": "#bfdbfe",
        "alpha": 0.55,
    },
    "ACC_SINK": {
        "edgecolor": "#059669",
        "facecolor": "#a7f3d0",
        "alpha": 0.55,
    },
    "ACC_BIDET": {
        "edgecolor": "#7c3aed",
        "facecolor": "#ddd6fe",
        "alpha": 0.55,
    },
    "ACC_DOOR": {
        "edgecolor": "#d97706",
        "facecolor": "#fde68a",
        "alpha": 0.55,
    },
    "ACC_ENTRY": {
        "edgecolor": "#dc2626",
        "facecolor": "#dc2626",
        "alpha": 1.0,
    },
}


def _style_for_layer(layer: str) -> _LayerStyle:
    return _LAYER_STYLES.get(layer, _DEFAULT_STYLE)


def _entity_label(entity: DxfEntitySummary) -> str:
    return (
        entity.attributes.get("ID")
        or entity.attributes.get("TYPE")
        or entity.layer.removeprefix("ACC_")
    )


def _center_of_vertices(vertices: list[tuple[float, float]]) -> tuple[float, float]:
    count = len(vertices)
    return (
        sum(x for x, _ in vertices) / count,
        sum(y for _, y in vertices) / count,
    )


def _all_coordinates(
    inspection: DxfInspection,
) -> list[tuple[float, float]]:
    coordinates: list[tuple[float, float]] = []

    for entity in inspection.entities:
        coordinates.extend(entity.vertices)
        if entity.point is not None:
            coordinates.append(entity.point)

    return coordinates


def _apply_geometry_limits(ax: Axes, inspection: DxfInspection) -> None:
    coordinates = _all_coordinates(inspection)
    if not coordinates:
        return

    xs = [x for x, _ in coordinates]
    ys = [y for _, y in coordinates]

    min_x = min(xs)
    max_x = max(xs)
    min_y = min(ys)
    max_y = max(ys)

    width = max_x - min_x
    height = max_y - min_y
    fallback_span = max(width, height, 1.0)
    margin_x = (width if width > 0 else fallback_span) * 0.08
    margin_y = (height if height > 0 else fallback_span) * 0.08

    ax.set_xlim(min_x - margin_x, max_x + margin_x)
    ax.set_ylim(min_y - margin_y, max_y + margin_y)


def _draw_polygon(
    ax: Axes,
    entity: DxfEntitySummary,
    *,
    legend_layers: set[str],
) -> None:
    style = _style_for_layer(entity.layer)
    is_room = entity.layer == "ACC_ROOM"
    zorder = 1 if is_room else 2

    label = entity.layer if entity.layer not in legend_layers else None
    legend_layers.add(entity.layer)

    if entity.is_closed and len(entity.vertices) >= 3:
        patch = MatplotlibPolygon(
            entity.vertices,
            closed=True,
            fill=True,
            edgecolor=str(style["edgecolor"]),
            facecolor=str(style["facecolor"]),
            alpha=float(style["alpha"]),
            linewidth=2.2 if is_room else 1.6,
            label=label,
            zorder=zorder,
        )
        ax.add_patch(patch)
    else:
        xs = [x for x, _ in entity.vertices]
        ys = [y for _, y in entity.vertices]
        ax.plot(
            xs,
            ys,
            color=str(style["edgecolor"]),
            linewidth=2.2 if is_room else 1.6,
            label=label,
            zorder=zorder,
        )

    center = _center_of_vertices(entity.vertices)
    ax.text(
        center[0],
        center[1],
        _entity_label(entity),
        ha="center",
        va="center",
        fontsize=8,
        zorder=4,
    )


def _draw_point(
    ax: Axes,
    entity: DxfEntitySummary,
    *,
    legend_layers: set[str],
) -> None:
    if entity.point is None:
        return

    style = _style_for_layer(entity.layer)
    label = entity.layer if entity.layer not in legend_layers else None
    legend_layers.add(entity.layer)

    ax.scatter(
        [entity.point[0]],
        [entity.point[1]],
        color=str(style["facecolor"]),
        edgecolors=str(style["edgecolor"]),
        s=70,
        marker="o",
        label=label,
        zorder=5,
    )
    ax.annotate(
        _entity_label(entity),
        xy=entity.point,
        xytext=(6, 6),
        textcoords="offset points",
        fontsize=8,
        zorder=6,
    )


def render_preview(
    inspection: DxfInspection,
    output_path: str | Path,
    *,
    show: bool = False,
) -> Path:
    """Render a 2D DXF inspection and save it as an image."""

    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)

    fig, ax = plt.subplots(figsize=(8, 6), dpi=150)
    legend_layers: set[str] = set()

    for entity in inspection.entities:
        if entity.vertices:
            _draw_polygon(ax, entity, legend_layers=legend_layers)
        elif entity.point is not None:
            _draw_point(ax, entity, legend_layers=legend_layers)

    ax.set_title("DXF accessibility layout preview")
    ax.set_xlabel("X (m)")
    ax.set_ylabel("Y (m)")
    ax.set_aspect("equal", adjustable="box")
    ax.ticklabel_format(useOffset=False)
    ax.grid(True, color="#d1d5db", linewidth=0.6, alpha=0.7)
    _apply_geometry_limits(ax, inspection)

    if legend_layers:
        ax.legend(title="Layers", loc="best", fontsize=8)

    fig.tight_layout()
    fig.savefig(output, dpi=150)

    if show:
        plt.show()
    else:
        plt.close(fig)

    return output


def preview_dxf(
    input_path: str | Path,
    output_path: str | Path,
    *,
    show: bool = False,
) -> Path:
    """Inspect a DXF file and render its 2D preview."""

    inspection = inspect_dxf(input_path)
    return render_preview(inspection, output_path, show=show)


def main() -> None:
    """Run the DXF preview renderer from the command line."""

    import argparse

    parser = argparse.ArgumentParser(description="Render a 2D preview of a DXF layout.")
    parser.add_argument("path", type=Path)
    parser.add_argument("--output", type=Path, default=Path("dxf_preview.png"))
    parser.add_argument("--show", action="store_true")
    arguments = parser.parse_args()

    output = preview_dxf(arguments.path, arguments.output, show=arguments.show)
    print(f"Preview saved to: {output}")


if __name__ == "__main__":
    main()
