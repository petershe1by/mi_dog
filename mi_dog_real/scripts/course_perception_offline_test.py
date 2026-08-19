#!/usr/bin/env python3
import importlib.util, math, pathlib
p = pathlib.Path(__file__).with_name("course_perception.py")
s = importlib.util.spec_from_file_location("course_perception", p)
m = importlib.util.module_from_spec(s); s.loader.exec_module(m)
width, height, step = 72, 48, 216
image = bytearray(step * height)
for y in range(height // 3, height):
    for x in list(range(6, 18)) + list(range(54, 66)):
        o = y * step + x * 3; image[o:o+3] = bytes((20, 210, 220))
    for x in range(30, 42):
        o = y * step + x * 3; image[o:o+3] = bytes((30, 100, 230))
f = m.extract_colour_features(image, width, height, "bgr8", step, 3, 6)
assert f["orange_seen"] and f["lane_boundaries_seen"]
assert abs(f["heading_error_rad"]) < .03
blank = bytearray(step * height)
f = m.extract_colour_features(blank, width, height, "bgr8", step, 3, 6)
assert not f["orange_seen"] and not f["lane_boundaries_seen"] and f["heading_error_rad"] == 0.
ranges = [2.] * 25; ranges[12] = .4
assert .4 <= m.front_clearance(ranges, -1.2, .1, .1, 10.) <= 2.
assert m.front_clearance([], -1., .1, .1, 10.) == 0.
u = m.SiteLocalization(transform_valid=False)
pose, confidence, state = u.update(1., 2., 0.)
assert pose is None and confidence == 0. and state == "SITE_TRANSFORM_UNCALIBRATED"
l = m.SiteLocalization(1., 2., math.pi/2., True)
pose, confidence, state = l.update(1., 3., math.pi/2.)
assert abs(pose[0]-1.) < 1e-9 and abs(pose[1]) < 1e-9 and confidence >= .65
pose, confidence, state = l.update(2., 3., math.pi/2.)
assert pose is None and confidence == 0. and state == "ODOM_JUMP"
assert abs(m.yaw_from_quaternion(0., 0., 0., 1.)) < 1e-9
try: m.extract_colour_features(blank, width, height, "mono8", step, 3, 6); raise AssertionError()
except ValueError: pass
print("course_perception_colour=PASS")
print("course_perception_localization_fail_closed=PASS")
print("course_perception_no_synthetic_facts=PASS")
