"""Render semantic comparison previews for DXF accessibility layouts."""

from __future__ import annotations

from pathlib import Path
from typing import Final

import matplotlib.pyplot as plt
from matplotlib.axes import Axes
from matplotlib.patches import Polygon as MatplotlibPolygon
from matplotlib.patches import Rectangle

from wheelchair_layout_solver.models import ElementSpec, VariationBounds

from .dxf_importer import DxfEntitySummary, DxfInspection, inspect_dxf
from .semantic_importer import DxfSemanticData, semantic_from_dxf, world_coordinates

_LayerColor = dict[str, str]

_LAYER_COLORS: Final[dict[str, _LayerColor]] = {
    "ACC_WC": {"edge": "#2563eb", "fill": "#bfdbfe"},
    "ACC_SINK": {"edge": "#059669", "fill": "#a7f3d0"},
    "ACC_BIDET": {"edge": "#7c3aed", "fill": "#ddd6fe"},
    "ACC_DOOR": {"edge": "#d97706", "fill": "#fde68a"},
    "ACC_SHOWER": {"edge": "#0891b2", "fill": "#a5f3fc"},
}

_DEFAULT_COLOR: Final[_LayerColor] = {"edge": "#4b5563", "fill": "#e5e7eb"}


def _colors_for_layer(layer: str) -> _LayerColor:
    return _LAYER_COLORS.get(layer, _DEFAULT_COLOR)


def _polygon_center(vertices: list[tuple[float, float]]) -> tuple[float, float]:
    count = len(vertices)
    return (
        sum(x for x, _ in vertices) / count,
        sum(y for _, y in vertices) / count,
    )


def _semantic_label(element: ElementSpec) -> str:
    return f"{element.id}\n{element.type.value}"


def _source_entities_by_id(
    inspection: DxfInspection,
) -> dict[str, DxfEntitySummary]:
    result: dict[str, DxfEntitySummary] = {}
    for entity in inspection.entities:
        entity_id = entity.attributes.get("ID")
        if entity_id:
            result[entity_id] = entity
    return result


def _bounds_from_variation(bounds: VariationBounds) -> tuple[float, float, float, float]:
    if bounds.x_min is None or bounds.x_max is None or bounds.y_min is None or bounds.y_max is None:
        return (0.0, 0.0, 0.0, 0.0)
    return (bounds.x_min, bounds.y_min, bounds.x_max - bounds.x_min, bounds.y_max - bounds.y_min)


def _plot_polygon(
    ax: Axes,
    vertices: list[tuple[float, float]],
    *,
    edgecolor: str,
    facecolor: str = "none",
    linestyle: str = "-",
    alpha: float = 1.0,
    linewidth: float = 1.6,
    label: str | None = None,
    zorder: int = 2,
) -> None:
    patch = MatplotlibPolygon(
        vertices,
        closed=True,
        fill=facecolor != "none",
        edgecolor=edgecolor,
        facecolor=facecolor,
        linestyle=linestyle,
        alpha=alpha,
        linewidth=linewidth,
        label=label,
        zorder=zorder,
    )
    ax.add_patch(patch)


def _plot_variation_bounds(
    ax: Axes,
    bounds: VariationBounds,
    *,
    edgecolor: str,
    label: str | None,
) -> None:
    x, y, width, height = _bounds_from_variation(bounds)
    rectangle = Rectangle(
        (x, y),
        width,
        height,
        fill=True,
        facecolor=edgecolor,
        edgecolor=edgecolor,
        alpha=0.12,
        linestyle=":",
        linewidth=1.2,
        label=label,
        zorder=1,
    )
    ax.add_patch(rectangle)


def _all_coordinates(
    inspection: DxfInspection,
    semantic: DxfSemanticData,
) -> list[tuple[float, float]]:
    coordinates: list[tuple[float, float]] = []
    coordinates.extend(semantic.room.coordinates)
    coordinates.append((semantic.entry.x, semantic.entry.y))
    if semantic.target is not None:
        coordinates.append((semantic.target.x, semantic.target.y))

    for entity in inspection.entities:
        coordinates.extend(entity.vertices)
        if entity.point is not None:
            coordinates.append(entity.point)

    for element in semantic.elements:
        coordinates.extend(world_coordinates(element))
        bounds = element.variation_bounds
        if bounds is not None:
            x, y, width, height = _bounds_from_variation(bounds)
            coordinates.extend(
                [
                    (x, y),
                    (x + width, y),
                    (x + width, y + height),
                    (x, y + height),
                ]
            )

    return coordinates


def _apply_geometry_limits(
    ax: Axes,
    inspection: DxfInspection,
    semantic: DxfSemanticData,
) -> None:
    coordinates = _all_coordinates(inspection, semantic)
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


def _draw_room(ax: Axes, semantic: DxfSemanticData) -> None:
    _plot_polygon(
        ax,
        semantic.room.coordinates,
        edgecolor="#111827",
        facecolor="#f9fafb",
        alpha=0.22,
        linewidth=2.2,
        label="room",
        zorder=0,
    )


def _draw_entry(ax: Axes, semantic: DxfSemanticData) -> None:
    ax.scatter(
        [semantic.entry.x],
        [semantic.entry.y],
        color="#dc2626",
        edgecolors="#991b1b",
        s=80,
        marker="o",
        label="entry",
        zorder=5,
    )
    ax.annotate(
        "ENTRY",
        xy=(semantic.entry.x, semantic.entry.y),
        xytext=(6, 6),
        textcoords="offset points",
        fontsize=8,
        zorder=6,
    )


def _draw_element(
    ax: Axes,
    element: ElementSpec,
    *,
    source_entity: DxfEntitySummary | None,
    legend_labels: set[str],
) -> None:
    colors = _colors_for_layer(element.layer)
    semantic_vertices = world_coordinates(element)

    if source_entity is not None and source_entity.vertices:
        label = "DXF original" if "DXF original" not in legend_labels else None
        legend_labels.add("DXF original")
        _plot_polygon(
            ax,
            source_entity.vertices,
            edgecolor=colors["edge"],
            linestyle="--",
            alpha=0.75,
            linewidth=1.2,
            label=label,
            zorder=2,
        )

    label = "semantic reconstruction" if "semantic reconstruction" not in legend_labels else None
    legend_labels.add("semantic reconstruction")
    _plot_polygon(
        ax,
        semantic_vertices,
        edgecolor=colors["edge"],
        facecolor=colors["fill"],
        alpha=0.38,
        linewidth=1.8,
        label=label,
        zorder=3,
    )

    if element.variation_bounds is not None:
        bounds_label = "variation bounds" if "variation bounds" not in legend_labels else None
        legend_labels.add("variation bounds")
        _plot_variation_bounds(
            ax,
            element.variation_bounds,
            edgecolor=colors["edge"],
            label=bounds_label,
        )

    center = _polygon_center(semantic_vertices)
    ax.text(
        center[0],
        center[1],
        _semantic_label(element),
        ha="center",
        va="center",
        fontsize=8,
        zorder=6,
    )


def render_semantic_preview(
    inspection: DxfInspection,
    semantic: DxfSemanticData,
    output_path: str | Path,
    *,
    show: bool = False,
) -> Path:
    """Render a semantic comparison preview and save it as an image."""

    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)

    fig, ax = plt.subplots(figsize=(8, 6), dpi=150)
    legend_labels: set[str] = set()
    source_by_id = _source_entities_by_id(inspection)

    _draw_room(ax, semantic)
    _draw_entry(ax, semantic)

    for element in semantic.elements:
        _draw_element(
            ax,
            element,
            source_entity=source_by_id.get(element.id),
            legend_labels=legend_labels,
        )

    ax.set_title("Semantic accessibility layout preview")
    ax.set_xlabel("X (m)")
    ax.set_ylabel("Y (m)")
    ax.set_aspect("equal", adjustable="box")
    ax.ticklabel_format(useOffset=False)
    ax.grid(True, color="#d1d5db", linewidth=0.6, alpha=0.7)
    _apply_geometry_limits(ax, inspection, semantic)
    ax.legend(loc="best", fontsize=8)

    fig.tight_layout()
    fig.savefig(output, dpi=150)

    if show:
        plt.show()
    else:
        plt.close(fig)

    return output


def semantic_preview_from_dxf(
    path: str | Path,
    output_path: str | Path,
    *,
    show: bool = False,
) -> Path:
    """Inspect a DXF file, build semantic data and render the preview."""

    inspection = inspect_dxf(path)
    semantic = semantic_from_dxf(path)
    return render_semantic_preview(inspection, semantic, output_path, show=show)


def main() -> None:
    """Run the semantic DXF preview renderer from the command line."""

    import argparse

    parser = argparse.ArgumentParser(
        description="Render a semantic comparison preview of a DXF layout."
    )
    parser.add_argument("path", type=Path)
    parser.add_argument("--output", type=Path, default=Path("semantic_preview.png"))
    parser.add_argument("--show", action="store_true")
    arguments = parser.parse_args()

    output = semantic_preview_from_dxf(arguments.path, arguments.output, show=arguments.show)
    print(f"Semantic preview saved to: {output}")


if __name__ == "__main__":
    main()
