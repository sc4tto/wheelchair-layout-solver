from wheelchair_layout_solver.io import load_scene
from wheelchair_layout_solver.models import Pose
from wheelchair_layout_solver.path import interpolate_segment, validate_path


def test_interpolation_respects_angular_sampling() -> None:
    poses = interpolate_segment(
        Pose(x=1.0, y=1.0, angle_deg=0),
        Pose(x=1.0, y=1.0, angle_deg=90),
        spatial_step=0.02,
        angular_step_deg=5,
    )
    assert len(poses) == 19
    assert poses[-1].angle_deg == 90


def test_sample_path_detects_collision() -> None:
    scene = load_scene("samples/bathroom_01.json")
    result = validate_path(scene)
    assert not result.valid
    assert result.first_invalid_index is not None
    assert "WC_01" in result.collision_ids
