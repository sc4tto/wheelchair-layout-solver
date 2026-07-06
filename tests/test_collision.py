from wheelchair_layout_solver.collision import check_pose
from wheelchair_layout_solver.io import load_scene
from wheelchair_layout_solver.models import Pose


def test_central_pose_is_valid() -> None:
    scene = load_scene("samples/bathroom_01.json")
    result = check_pose(scene, Pose(x=1.25, y=1.25, angle_deg=0))
    assert result.valid
    assert result.collision_ids == []
    assert result.minimum_clearance is not None
    assert result.minimum_clearance > 0


def test_pose_on_toilet_is_invalid() -> None:
    scene = load_scene("samples/bathroom_01.json")
    result = check_pose(scene, Pose(x=2.45, y=0.50, angle_deg=0))
    assert not result.valid
    assert "WC_01" in result.collision_ids


def test_pose_outside_room_is_invalid() -> None:
    scene = load_scene("samples/bathroom_01.json")
    result = check_pose(scene, Pose(x=0.10, y=0.10, angle_deg=0))
    assert not result.valid
    assert not result.inside_room
