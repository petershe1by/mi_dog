#!/usr/bin/env python3
"""Dependency-free regression test; never connects to a robot."""
import importlib.util
from pathlib import Path

path = Path(__file__).with_name("race_controller.py")
spec = importlib.util.spec_from_file_location("race_controller", path)
module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
profiles = tuple(module.StageProfile(
    p.name, 1.0, p.speed_mps, p.steer_gain, p.min_clearance_m)
    for p in module.DEFAULT_STAGES)
uncalibrated = module.RaceCore(profiles)
assert uncalibrated.geometry["course_width_m"] == 4.0
assert uncalibrated.geometry["course_length_m"] == 16.0
assert uncalibrated.geometry["solid_boundary_keepout_m"] == 0.15
assert uncalibrated.geometry["stone_count"] == 4
assert uncalibrated.geometry["ball_grid_columns"] == 4
assert uncalibrated.geometry["search_channel_count"] == 3
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
    assert core.step(stage * 10, 0, 1, 0.2, 1.2, True, True)[0] == 0
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
