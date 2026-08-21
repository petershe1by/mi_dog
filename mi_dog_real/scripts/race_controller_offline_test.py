#!/usr/bin/env python3
"""Dependency-free regression test; never connects to a robot."""
import importlib.util
import math
from pathlib import Path

path = Path(__file__).with_name("race_controller.py")
spec = importlib.util.spec_from_file_location("race_controller", path)
module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
profiles = tuple(module.StageProfile(
    p.name, 1.0, p.speed_mps, p.steer_gain, p.min_clearance_m)
    for p in module.DEFAULT_STAGES)
assert module.DEFAULT_STAGES[0].speed_mps == 0.40
assert module.DEFAULT_STAGES[0].distance_m == 3.2
assert module.DEFAULT_STAGES[1].distance_m == 5.25
assert module.DEFAULT_STAGES[1].min_clearance_m == 0.12
assert all(profile.speed_mps <= 0.40 for profile in module.DEFAULT_STAGES)
guard = module.StraightLineGuard()
straight = guard.correct(0.0, 0.0, 0.0, 0.4, 0.0)
assert straight[:2] == (0.4, 0.0) and straight[4] == "TRACK_HOLD"
right_pull = guard.correct(1.0, 0.10, 0.0, 0.4, 0.0)
assert 0.0 < right_pull[0] < 0.4 and right_pull[1] < 0.0
heading_pull = guard.correct(1.0, 0.0, 0.10, 0.4, 0.0)
assert heading_pull[0] == 0.4 and heading_pull[1] < 0.0
escaped = guard.correct(1.0, 0.19, 0.0, 0.4, 0.0)
assert escaped[0] == 0.0 and escaped[1] == 0.0
assert escaped[4] == "TRACK_DEVIATION"
guard.reset()
assert guard.origin is None
assert module.stage_1_entry_guard_required(1, {})
assert module.stage_1_entry_guard_required(1, {"stones_passed": 3})
assert not module.stage_1_entry_guard_required(1, {"stones_passed": 4})
assert not module.stage_1_entry_guard_required(2, {"stones_passed": 0})
assert not module.stage_1_entry_guard_required(1, {"stones_passed": "4"})
assert module.stage_motion_enabled(1, 2)
assert module.stage_motion_enabled(2, 2)
assert not module.stage_motion_enabled(3, 2)
assert not module.stage_motion_enabled(1, 0)
assert not module.stage_motion_enabled(True, 2)
orange = module.OrangeAnnouncementGate(confirm_frames=3, clear_frames=2, cooldown_sec=1.0)
assert not orange.update(True, 0.0)
assert not orange.update(True, 0.1)
assert orange.update(True, 0.2)
assert not orange.update(True, 0.3)
assert not orange.update(False, 0.4)
assert not orange.update(False, 0.5)
assert not orange.update(True, 0.6)
assert not orange.update(True, 0.7)
assert orange.update(True, 1.3)
boundary = module.CourseBoundaryGuard(4.0, 16.0, keepout_m=0.08)
clear = boundary.correct((2.0, 2.0, 0.0), 0.4, 0.0)
assert clear[:2] == (0.4, 0.0) and clear[4] == "BOUNDARY_CLEAR"
near_left = boundary.correct((0.20, 2.0, math.pi / 2.0), 0.2, 0.0)
assert 0.0 < near_left[0] < 0.2 and near_left[1] < 0.0
predicted_exit = boundary.correct((3.90, 2.0, 0.0), 0.4, 0.0)
assert predicted_exit[0] == 0.0 and predicted_exit[4] == "BOUNDARY_PREDICTED_STOP"
at_keepout = boundary.correct((0.08, 2.0, 0.0), 0.1, 0.0)
assert at_keepout[0] == 0.0 and at_keepout[4] == "BOUNDARY_STOP"
invalid_pose = boundary.correct(None, 0.1, 0.0)
assert invalid_pose[0] == 0.0 and invalid_pose[4] == "BOUNDARY_POSE_INVALID"
uncalibrated = module.RaceCore(profiles)
assert uncalibrated.geometry["course_width_m"] == 4.0
assert uncalibrated.geometry["course_length_m"] == 16.0
assert uncalibrated.geometry["solid_boundary_keepout_m"] == 0.15
assert uncalibrated.geometry["stone_count"] == 4
assert uncalibrated.geometry["ball_grid_columns"] == 4
assert uncalibrated.geometry["search_channel_count"] == 3
assert uncalibrated.geometry["stage_3_exit_center_y_m"] == 7.0
assert uncalibrated.geometry["stage_4_lane_2_center_x_m"] == 1.5
assert uncalibrated.geometry["bridge_width_m"] == 0.5
assert uncalibrated.geometry["stage_5_bridge_jump_line_y_m"] == 11.5
assert uncalibrated.geometry["stage_6_football_x_m"] == 1.0
assert uncalibrated.geometry["stage_6_finish_center_y_m"] == 13.25
blocked = uncalibrated.step(0.0, 0.0, 1.0, 2.0, 1.0, True, True)
assert blocked[0] == 0.0 and blocked[1] == 0.0
assert blocked[2] is None and blocked[4] == "COURSE_UNCALIBRATED"
far_beyond_placeholder = uncalibrated.step(10.0, 0.0, 1.0, 2.0, 1.0, True, True)
assert far_beyond_placeholder[0] == 0.0 and far_beyond_placeholder[1] == 0.0
assert far_beyond_placeholder[2] is None
assert far_beyond_placeholder[4] == "COURSE_UNCALIBRATED"

for key, bad_value in (
        ("course_width_m", 0.0),
        ("stone_count", 3),
        ("ball_grid_rows", 5),
        ("search_channel_count", 2),
        ("stage_5_bridge_jump_line_y_m", 11.4),
        ("solid_boundary_keepout_m", 0.05)):
    invalid = dict(module.OFFICIAL_GEOMETRY_DEFAULTS)
    invalid[key] = bad_value
    try:
        module.RaceCore(profiles, geometry=invalid)
    except ValueError:
        pass
    else:
        raise AssertionError("invalid geometry accepted: " + key)

core = module.RaceCore(profiles, course_calibrated=True)
for stage in range(1, 7):
    core.select_stage(stage, float(stage * 10), 0.0)
    assert core.step(stage * 10, 0, 1, 2, 1, False, True)[0] == 0
    assert core.step(stage * 10, 0, 1, 2, 1, True, False)[0] == 0
    assert core.step(stage * 10, 0, 1, float("nan"), 1, True, True)[4] == "INVALID_SCAN"
    close_result = core.step(stage * 10, 0, 1, 0.2, 1.2, True, True)
    if stage == 2:
        assert close_result[0] > 0
    else:
        assert close_result[0] == 0
    running = core.step(stage * 10 + 0.2, 0, 1, 2, 1, True, True)
    assert running[0] > 0 and running[2] is None
    done = core.step(stage * 10 + 1.01, 0, 1, 2, 1, True, True)
    assert done[0] == 0 and done[2] == stage
    assert core.step(stage * 10 + 1.02, 0, 1, 2, 1, True, True)[2] is None
print("race_controller_offline=PASS")
print("six_stage_sequence=PASS")
print("fail_closed_inputs=PASS")
print("uncalibrated_course_gate=PASS")
print("official_course_geometry=PASS")
print("invalid_geometry_fail_closed=PASS")
print("course_boundary_guard=PASS")
