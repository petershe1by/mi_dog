#!/usr/bin/env python3
"""Fail-closed six-stage real-robot race controller.

The ROS wrapper is deliberately thin; RaceCore is dependency-free and replay-testable.
Physical limits and the final obstacle stop remain enforced by mi_dog_real_node.
"""

from collections import namedtuple
import json
import math
import os
import subprocess
import time


StageProfile = namedtuple(
    "StageProfile", "name distance_m speed_mps steer_gain min_clearance_m")


DEFAULT_STAGES = (
    # Official page-3 map: start at x=0.50, cross to the right-side opening
    # centre x=3.70, then turn into the ball field.  Stage 2 crosses the 4 m
    # field diagonally between the two 0.60 m openings (about 5.25 m).
    StageProfile("stone", 3.2, 0.40, 0.55, 0.42),
    StageProfile("balls", 5.25, 0.08, 0.75, 0.12),
    StageProfile("curve", 2.5, 0.09, 0.95, 0.42),
    StageProfile("tunnel", 2.0, 0.08, 1.10, 0.38),
    StageProfile("bridge", 2.2, 0.06, 1.20, 0.45),
    StageProfile("finish", 2.0, 0.12, 0.45, 0.40),
)


class StraightLineGuard:
    """Hold the stage-entry odom line and stop before lateral escape."""
    def __init__(self, heading_gain=1.2, lateral_gain=1.5, max_yaw=0.25,
                 slow_lateral_m=0.08, stop_lateral_m=0.18):
        values = (heading_gain, lateral_gain, max_yaw,
                  slow_lateral_m, stop_lateral_m)
        if (not all(math.isfinite(v) and v > 0.0 for v in values) or
                stop_lateral_m <= slow_lateral_m):
            raise ValueError("invalid straight-line guard parameters")
        self.heading_gain = heading_gain
        self.lateral_gain = lateral_gain
        self.max_yaw = max_yaw
        self.slow_lateral_m = slow_lateral_m
        self.stop_lateral_m = stop_lateral_m
        self.origin = None

    def reset(self):
        self.origin = None

    def correct(self, x, y, yaw, linear, base_yaw):
        if not all(math.isfinite(v) for v in (x, y, yaw, linear, base_yaw)):
            return 0.0, 0.0, None, None, "TRACK_INVALID"
        if self.origin is None:
            self.origin = (x, y, yaw)
        x0, y0, yaw0 = self.origin
        dx, dy = x - x0, y - y0
        lateral = -math.sin(yaw0) * dx + math.cos(yaw0) * dy
        heading = math.atan2(math.sin(yaw - yaw0), math.cos(yaw - yaw0))
        if abs(lateral) >= self.stop_lateral_m:
            return 0.0, 0.0, lateral, heading, "TRACK_DEVIATION"
        correction = -self.heading_gain * heading - self.lateral_gain * lateral
        corrected_yaw = max(
            -self.max_yaw, min(self.max_yaw, base_yaw + correction))
        scale = 1.0
        if abs(lateral) > self.slow_lateral_m:
            scale = max(0.35, (self.stop_lateral_m - abs(lateral)) /
                        (self.stop_lateral_m - self.slow_lateral_m))
        state = "TRACK_CORRECTING" if abs(lateral) > self.slow_lateral_m else "TRACK_HOLD"
        return linear * scale, corrected_yaw, lateral, heading, state


class OrangeAnnouncementGate:
    """Debounce visual orange encounters without affecting motion decisions."""
    def __init__(self, confirm_frames=3, clear_frames=8, cooldown_sec=3.0):
        if (confirm_frames < 1 or clear_frames < 1 or
                not math.isfinite(cooldown_sec) or cooldown_sec < 0.0):
            raise ValueError("invalid orange announcement gate")
        self.confirm_frames = int(confirm_frames)
        self.clear_frames = int(clear_frames)
        self.cooldown_sec = float(cooldown_sec)
        self.seen_count = 0
        self.clear_count = 0
        self.latched = False
        self.last_announcement = -math.inf

    def reset(self):
        self.seen_count = 0
        self.clear_count = 0
        self.latched = False

    def update(self, seen, now):
        if not math.isfinite(now):
            return False
        if seen:
            self.clear_count = 0
            self.seen_count = min(self.confirm_frames, self.seen_count + 1)
            if (not self.latched and self.seen_count >= self.confirm_frames and
                    now - self.last_announcement >= self.cooldown_sec):
                self.latched = True
                self.last_announcement = now
                return True
            return False
        self.seen_count = 0
        self.clear_count = min(self.clear_frames, self.clear_count + 1)
        if self.clear_count >= self.clear_frames:
            self.latched = False
        return False


def stage_1_entry_guard_required(stage, facts):
    """Use the odom straight-line guard only before the official exit turn."""
    return (stage == 1 and isinstance(facts, dict) and
            isinstance(facts.get("stones_passed", 0), int) and
            not isinstance(facts.get("stones_passed", 0), bool) and
            facts.get("stones_passed", 0) < 4)


def stage_motion_enabled(stage, max_enabled_stage):
    """Return whether physical acceptance authorizes this stage to move."""
    if (isinstance(stage, bool) or isinstance(max_enabled_stage, bool) or
            not isinstance(stage, int) or not isinstance(max_enabled_stage, int)):
        return False
    return 1 <= stage <= 6 and 1 <= max_enabled_stage <= 6 and stage <= max_enabled_stage


class CourseBoundaryGuard:
    """Keep the robot pose and its conservative stopping point inside the course."""
    def __init__(self, width_m, length_m, keepout_m=0.08,
                 reaction_sec=0.20, decel_mps2=0.40,
                 correction_start_m=0.30, correction_gain=0.65,
                 max_correction_yaw=0.20):
        values = (width_m, length_m, keepout_m, reaction_sec, decel_mps2,
                  correction_start_m, correction_gain, max_correction_yaw)
        if (not all(math.isfinite(v) and v > 0.0 for v in values) or
                keepout_m >= min(width_m, length_m) / 2.0 or
                correction_start_m <= keepout_m):
            raise ValueError("invalid course-boundary guard parameters")
        self.width_m = width_m
        self.length_m = length_m
        self.keepout_m = keepout_m
        self.reaction_sec = reaction_sec
        self.decel_mps2 = decel_mps2
        self.correction_start_m = correction_start_m
        self.correction_gain = correction_gain
        self.max_correction_yaw = max_correction_yaw

    def _margin(self, x, y):
        return min(x, self.width_m - x, y, self.length_m - y)

    def correct(self, pose, linear, yaw):
        if (not isinstance(pose, (list, tuple)) or len(pose) != 3 or
                not all(math.isfinite(v) for v in pose) or
                not all(math.isfinite(v) for v in (linear, yaw))):
            return 0.0, 0.0, None, None, "BOUNDARY_POSE_INVALID"
        x, y, heading = pose
        margin = self._margin(x, y)
        if margin <= self.keepout_m:
            return 0.0, 0.0, margin, margin, "BOUNDARY_STOP"

        # Account for the adapter's acceleration limiting: requesting zero at
        # the keepout itself is too late at stage-1 speed.
        stopping_m = (abs(linear) * self.reaction_sec +
                      linear * linear / (2.0 * self.decel_mps2))
        predicted_x = x + math.cos(heading) * stopping_m
        predicted_y = y + math.sin(heading) * stopping_m
        predicted_margin = self._margin(predicted_x, predicted_y)
        if linear > 0.0 and predicted_margin <= self.keepout_m:
            return 0.0, 0.0, margin, predicted_margin, "BOUNDARY_PREDICTED_STOP"

        if margin < self.correction_start_m:
            target = math.atan2(self.length_m / 2.0 - y,
                                self.width_m / 2.0 - x)
            error = math.atan2(math.sin(target - heading),
                               math.cos(target - heading))
            correction = max(-self.max_correction_yaw,
                             min(self.max_correction_yaw,
                                 self.correction_gain * error))
            scale = max(0.35, min(1.0,
                        (margin - self.keepout_m) /
                        (self.correction_start_m - self.keepout_m)))
            return linear * scale, max(-0.25, min(0.25, yaw + correction)), \
                margin, predicted_margin, "BOUNDARY_CORRECTING"
        return linear, yaw, margin, predicted_margin, "BOUNDARY_CLEAR"

# Values transcribed from page 3 and the dimension list in the official 2026
# Xiaomi Cup problem PDF.  They describe fixed construction geometry only;
# randomized object poses and the real start transform remain site calibration.
OFFICIAL_GEOMETRY_DEFAULTS = {
    "course_width_m": 4.0,
    "course_length_m": 16.0,
    "nominal_lane_width_m": 1.0,
    # The prose says 15 cm (10 cm on curves), while the drawing legend says
    # 10 cm.  Use the larger keepout until the organizer/site resolves it.
    "solid_boundary_keepout_m": 0.15,
    "curve_boundary_width_m": 0.10,
    "start_width_m": 4.0,
    "start_length_m": 1.0,
    "stone_length_m": 1.0,
    "stone_width_m": 0.30,
    "stone_height_m": 0.05,
    "stone_gap_m": 0.20,
    "stone_count": 4,
    "ball_grid_width_m": 4.0,
    "ball_grid_length_m": 4.0,
    "ball_grid_columns": 4,
    "ball_grid_rows": 4,
    "ball_column_spacing_m": 1.0,
    "ball_row_spacing_m": 0.64,
    "ball_diameter_m": 0.20,
    "stage_2_ball_bottom_height_m": 0.20,
    "stage_1_start_center_x_m": 0.50,
    "stage_1_start_center_y_m": 0.50,
    "stage_1_exit_opening_width_m": 0.60,
    "stage_1_exit_center_x_m": 3.70,
    "stage_1_exit_center_y_m": 1.00,
    "stage_1_exit_clear_y_m": 1.30,
    "stage_2_exit_opening_width_m": 0.60,
    "stage_2_exit_center_x_m": 0.30,
    "stage_2_exit_center_y_m": 5.00,
    "stage_2_exit_clear_y_m": 5.30,
    "curve_lane_width_m": 0.60,
    "curve_longitudinal_span_m": 2.0,
    "stage_3_entry_center_x_m": 0.30,
    "stage_3_entry_center_y_m": 5.00,
    "stage_3_entry_clear_y_m": 5.30,
    "stage_3_exit_center_x_m": 3.70,
    "stage_3_exit_center_y_m": 7.00,
    "stage_3_exit_clear_y_m": 7.30,
    "search_area_width_m": 4.0,
    "search_area_length_m": 4.0,
    "searchable_channel_width_m": 3.0,
    "search_channel_count": 3,
    "search_channel_width_m": 1.0,
    "search_channel_length_m": 2.5,
    "stage_4_entry_center_x_m": 3.70,
    "stage_4_entry_center_y_m": 7.30,
    "stage_4_lane_1_center_x_m": 0.50,
    "stage_4_lane_2_center_x_m": 1.50,
    "stage_4_lane_3_center_x_m": 2.50,
    "stage_4_cross_channel_start_y_m": 7.00,
    "stage_4_channel_partition_y_m": 8.50,
    "stage_4_channel_end_y_m": 11.00,
    "obstacle_random_span_m": 1.5,
    "stage_4_ball_bottom_height_m": 0.60,
    "low_bar_length_m": 1.10,
    "low_bar_section_m": 0.10,
    "low_bar_clearance_m": 0.40,
    "obstacle_cube_size_m": 0.20,
    "obstacle_cube_gap_m": 0.20,
    "goal_width_m": 0.50,
    "goal_height_m": 0.30,
    "goal_depth_m": 0.50,
    "bridge_width_m": 0.50,
    "bridge_height_m": 0.05,
    "bridge_jump_before_end_m": 0.50,
    "stage_5_bridge_center_x_m": 3.75,
    "stage_5_bridge_start_y_m": 7.00,
    "stage_5_bridge_jump_line_y_m": 11.50,
    "stage_5_bridge_end_y_m": 12.00,
    "stage_6_area_start_y_m": 12.00,
    "stage_6_track_width_m": 0.50,
    "stage_6_bottom_center_y_m": 12.25,
    "stage_6_left_center_x_m": 0.25,
    "stage_6_top_center_y_m": 15.75,
    "stage_6_right_center_x_m": 3.75,
    "stage_6_track_exit_y_m": 13.50,
    "stage_6_football_x_m": 1.00,
    "stage_6_football_y_m": 15.00,
    "stage_6_finish_center_x_m": 3.75,
    "stage_6_finish_center_y_m": 13.25,
}

INTEGER_GEOMETRY_KEYS = {
    "stone_count", "ball_grid_columns", "ball_grid_rows", "search_channel_count"
}


def validate_course_geometry(values):
    """Return an immutable normalized geometry mapping or raise fail-closed."""
    if set(values) != set(OFFICIAL_GEOMETRY_DEFAULTS):
        missing = sorted(set(OFFICIAL_GEOMETRY_DEFAULTS) - set(values))
        extra = sorted(set(values) - set(OFFICIAL_GEOMETRY_DEFAULTS))
        raise ValueError("course geometry key mismatch: missing=%r extra=%r" % (missing, extra))
    normalized = {}
    for key, value in values.items():
        if key in INTEGER_GEOMETRY_KEYS:
            if isinstance(value, bool) or int(value) != value or int(value) <= 0:
                raise ValueError("invalid positive integer geometry value: " + key)
            normalized[key] = int(value)
        else:
            candidate = float(value)
            if not math.isfinite(candidate) or candidate <= 0.0:
                raise ValueError("invalid positive geometry value: " + key)
            normalized[key] = candidate
    if normalized["nominal_lane_width_m"] > normalized["course_width_m"]:
        raise ValueError("nominal lane exceeds course width")
    if normalized["solid_boundary_keepout_m"] < normalized["curve_boundary_width_m"]:
        raise ValueError("straight boundary keepout must conservatively cover curve width")
    if normalized["stone_count"] != 4:
        raise ValueError("official stone count must be four")
    if normalized["ball_grid_columns"] != 4 or normalized["ball_grid_rows"] != 4:
        raise ValueError("official ball grid must be 4x4")
    if normalized["search_channel_count"] != 3:
        raise ValueError("official search area must have three channels")
    if (normalized["searchable_channel_width_m"] !=
            normalized["search_channel_count"] * normalized["search_channel_width_m"]):
        raise ValueError("search channel widths do not match the drawing")
    if not (normalized["stage_3_entry_center_y_m"] <
            normalized["stage_3_exit_center_y_m"] <
            normalized["stage_4_channel_end_y_m"] <
            normalized["stage_6_area_start_y_m"] <
            normalized["stage_6_top_center_y_m"] <
            normalized["course_length_m"]):
        raise ValueError("stage landmark order does not match the drawing")
    if (normalized["stage_5_bridge_jump_line_y_m"] !=
            normalized["stage_5_bridge_end_y_m"] -
            normalized["bridge_jump_before_end_m"]):
        raise ValueError("bridge jump line must be 0.50 m before its end")
    if normalized["bridge_jump_before_end_m"] >= normalized["search_channel_length_m"]:
        raise ValueError("bridge jump offset is implausibly large")
    return normalized


class RaceCore:
    def __init__(self, profiles=DEFAULT_STAGES, course_calibrated=False,
                 geometry=OFFICIAL_GEOMETRY_DEFAULTS):
        if len(profiles) != 6 or any(p.distance_m <= 0 or p.speed_mps <= 0 for p in profiles):
            raise ValueError("exactly six positive stage profiles are required")
        self.profiles = tuple(profiles)
        self.geometry = validate_course_geometry(dict(geometry))
        self.course_calibrated = bool(course_calibrated)
        self.stage = 1
        self.origin = None
        self.completed = set()

    def select_stage(self, stage, x, y):
        if stage not in range(1, 7):
            raise ValueError("stage must be 1..6")
        if stage != self.stage or self.origin is None:
            self.stage = stage
            self.origin = (x, y)

    def step(self, x, y, left_m, front_m, right_m, allowed, fresh):
        self.select_stage(self.stage, x, y)
        progress = math.hypot(x - self.origin[0], y - self.origin[1])
        profile = self.profiles[self.stage - 1]
        # Checked-in distances are placeholders, not physical stage evidence.
        # Never move until a measured course profile is explicitly enabled.
        if not self.course_calibrated:
            return 0.0, 0.0, None, progress, "COURSE_UNCALIBRATED"
        if not allowed or not fresh:
            return 0.0, 0.0, None, progress, "INHIBITED"
        if progress >= profile.distance_m:
            completion = None if self.stage in self.completed else self.stage
            self.completed.add(self.stage)
            return 0.0, 0.0, completion, progress, "STAGE_COMPLETE"
        if not all(math.isfinite(v) and v > 0 for v in (left_m, front_m, right_m)):
            return 0.0, 0.0, None, progress, "INVALID_SCAN"
        if front_m <= profile.min_clearance_m:
            turn = -0.18 if left_m < right_m else 0.18
            return 0.0, turn, None, progress, "BLOCKED"
        error = max(-0.6, min(0.6, right_m - left_m))
        yaw = max(-0.25, min(0.25, profile.steer_gain * error))
        slow = min(1.0, max(0.35, (front_m - profile.min_clearance_m) / 0.5))
        return profile.speed_mps * slow, yaw, None, progress, "RUNNING"


def main():
    from race_mission import MissionCore, parse_observation
    import rclpy
    from geometry_msgs.msg import Twist
    from nav_msgs.msg import Odometry
    from rclpy.node import Node
    from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy, qos_profile_sensor_data
    from sensor_msgs.msg import Image, LaserScan
    from std_msgs.msg import Bool, Int32, String

    class Controller(Node):
        def __init__(self):
            super().__init__("mi_dog_race_controller")
            names = ["stone", "balls", "curve", "tunnel", "bridge", "finish"]
            profiles = []
            for i, name in enumerate(names, 1):
                profiles.append(StageProfile(
                    name,
                    float(self.declare_parameter(f"stage_{i}.distance_m", DEFAULT_STAGES[i-1].distance_m).value),
                    float(self.declare_parameter(f"stage_{i}.speed_mps", DEFAULT_STAGES[i-1].speed_mps).value),
                    float(self.declare_parameter(f"stage_{i}.steer_gain", DEFAULT_STAGES[i-1].steer_gain).value),
                    float(self.declare_parameter(f"stage_{i}.min_clearance_m", DEFAULT_STAGES[i-1].min_clearance_m).value)))
            course_calibrated = bool(
                self.declare_parameter("course_calibrated", False).value)
            self.require_camera_ready = bool(
                self.declare_parameter("require_camera_ready", True).value)
            self.max_enabled_stage = int(
                self.declare_parameter("max_enabled_stage", 0).value)
            if self.max_enabled_stage not in range(0, 7):
                raise ValueError("max_enabled_stage must be 0 (all disabled) or 1..6")
            geometry = {}
            for key, default in OFFICIAL_GEOMETRY_DEFAULTS.items():
                geometry[key] = self.declare_parameter(
                    "geometry." + key, default).value
            self.core = RaceCore(
                profiles, course_calibrated=course_calibrated, geometry=geometry)
            self.mission = MissionCore(
                course_calibrated=course_calibrated,
                timeout=float(self.declare_parameter("perception_timeout_sec", 0.6).value),
                min_localization=float(self.declare_parameter(
                    "min_localization_confidence", 0.65).value),
                stage_speeds=tuple(profile.speed_mps for profile in profiles),
                stage_1_across_target=(
                    self.core.geometry["stage_1_exit_center_x_m"],
                    self.core.geometry["stage_1_start_center_y_m"]),
                stage_1_exit_target=(
                    self.core.geometry["stage_1_exit_center_x_m"],
                    self.core.geometry["stage_1_exit_clear_y_m"]),
                stage_2_exit_target=(
                    self.core.geometry["stage_2_exit_center_x_m"],
                    self.core.geometry["stage_2_exit_clear_y_m"]))
            self.geometry_source = str(self.declare_parameter(
                "geometry_source", "official_2026_problem_pdf_page_3").value)
            self.timeout = float(self.declare_parameter("sensor_timeout_sec", 0.6).value)
            self.stage_1_track_guard = StraightLineGuard(
                float(self.declare_parameter("stage_1.heading_gain", 1.2).value),
                float(self.declare_parameter("stage_1.cross_track_gain", 1.5).value),
                float(self.declare_parameter("stage_1.max_correction_yaw_rps", 0.25).value),
                float(self.declare_parameter("stage_1.slow_lateral_error_m", 0.08).value),
                float(self.declare_parameter("stage_1.stop_lateral_error_m", 0.18).value))
            self.orange_gate = OrangeAnnouncementGate(
                int(self.declare_parameter("stage_2.orange_confirm_frames", 3).value),
                int(self.declare_parameter("stage_2.orange_clear_frames", 8).value),
                float(self.declare_parameter("stage_2.orange_audio_cooldown_sec", 3.0).value))
            self.orange_audio_file = str(self.declare_parameter(
                "stage_2.orange_audio_file",
                "/home/mi/mi_dog_ws/install/mi_dog_real/share/mi_dog_real/audio/orange_ball.wav").value)
            self.audio_process = None
            self.boundary_guard = CourseBoundaryGuard(
                self.core.geometry["course_width_m"],
                self.core.geometry["course_length_m"],
                float(self.declare_parameter("boundary_guard.keepout_m", 0.08).value),
                float(self.declare_parameter("boundary_guard.reaction_sec", 0.20).value),
                float(self.declare_parameter("boundary_guard.decel_mps2", 0.40).value),
                float(self.declare_parameter("boundary_guard.correction_start_m", 0.30).value),
                float(self.declare_parameter("boundary_guard.correction_gain", 0.65).value),
                float(self.declare_parameter("boundary_guard.max_correction_yaw_rps", 0.20).value))
            image_topic = self.declare_parameter("camera_topic", "/image").value
            scan_topic = self.declare_parameter("lidar_topic", "/scan").value
            odom_topic = self.declare_parameter("odometry_topic", "/odom_out").value
            command_topic = self.declare_parameter(
                "command_topic", "/mi_dog_real/safe_cmd_vel").value
            stage_complete_topic = self.declare_parameter(
                "stage_complete_topic", "/mi_dog_real/stage_complete").value
            status_topic = self.declare_parameter(
                "status_topic", "/mi_dog_real/race_controller/status").value
            run_allowed_topic = self.declare_parameter(
                "run_allowed_topic", "/mi_dog_real/supervisor/run_allowed").value
            current_stage_topic = self.declare_parameter(
                "current_stage_topic", "/mi_dog_real/supervisor/current_stage").value
            perception_topic = self.declare_parameter(
                "perception_topic", "/mi_dog_real/course_observation").value
            latched = QoSProfile(depth=1, reliability=ReliabilityPolicy.RELIABLE,
                                 durability=DurabilityPolicy.TRANSIENT_LOCAL)
            self.pub = self.create_publisher(Twist, command_topic, 10)
            self.done_pub = self.create_publisher(Int32, stage_complete_topic, 10)
            self.status_pub = self.create_publisher(String, status_topic, latched)
            self.allowed = False
            self.stage = 1
            self.xy = None
            self.odom_pose = None
            self.scan = None
            self.observation = None
            self.seen = {"image": 0.0, "scan": 0.0, "odom": 0.0}
            self.create_subscription(Image, image_topic, self.on_image, qos_profile_sensor_data)
            self.create_subscription(LaserScan, scan_topic, self.on_scan, qos_profile_sensor_data)
            self.create_subscription(Odometry, odom_topic, self.on_odom, qos_profile_sensor_data)
            self.create_subscription(Bool, run_allowed_topic,
                                     lambda m: setattr(self, "allowed", m.data), latched)
            self.create_subscription(Int32, current_stage_topic, self.on_stage, latched)
            self.create_subscription(String, perception_topic, self.on_perception, 10)
            self.create_timer(0.1, self.tick)

        def now_s(self): return time.monotonic()
        def on_image(self, msg):
            if msg.width and msg.height and msg.data: self.seen["image"] = self.now_s()
        def on_odom(self, msg):
            q = msg.pose.pose.orientation
            norm = math.sqrt(q.x*q.x + q.y*q.y + q.z*q.z + q.w*q.w)
            if not math.isfinite(norm) or norm < 1e-6: return
            yaw = math.atan2(2.0*(q.w*q.z + q.x*q.y) / (norm*norm),
                             1.0-2.0*(q.y*q.y + q.z*q.z) / (norm*norm))
            self.xy = (msg.pose.pose.position.x, msg.pose.pose.position.y)
            if all(math.isfinite(v) for v in self.xy + (yaw,)):
                self.odom_pose = self.xy + (yaw,)
                self.seen["odom"] = self.now_s()
        def on_stage(self, msg):
            previous_stage = self.stage
            self.stage = msg.data
            if self.stage != previous_stage:
                self.stage_1_track_guard.reset()
                self.orange_gate.reset()
            if self.stage in range(1, 7): self.mission.select_stage(self.stage)
            if self.xy is not None: self.core.select_stage(self.stage, *self.xy)
        def on_perception(self, msg):
            try:
                value = parse_observation(msg.data)
                value["monotonic_stamp"] = self.now_s()
                self.observation = value
                detections = value.get("detections", {})
                orange_seen = (self.stage == 2 and self.allowed and
                               isinstance(detections, dict) and
                               detections.get("orange_seen") is True)
                if self.orange_gate.update(orange_seen, self.now_s()):
                    self.play_orange_announcement()
            except (TypeError, ValueError, json.JSONDecodeError):
                self.observation = None

        def play_orange_announcement(self):
            if not os.path.isfile(self.orange_audio_file):
                self.get_logger().error(
                    "Orange announcement missing: %s" % self.orange_audio_file)
                return
            if self.audio_process is not None and self.audio_process.poll() is None:
                return
            try:
                self.audio_process = subprocess.Popen(
                    ["/usr/bin/paplay", self.orange_audio_file],
                    stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL, start_new_session=True)
                self.get_logger().info("VOICE: 识别到橙色小球")
            except OSError as error:
                self.get_logger().error(
                    "Orange announcement failed: %s" % error)
        def on_scan(self, msg):
            sectors = [[], [], []]
            for i, value in enumerate(msg.ranges):
                angle = msg.angle_min + i * msg.angle_increment
                if math.isfinite(value) and msg.range_min <= value <= msg.range_max:
                    if -1.15 <= angle < -0.35: sectors[2].append(value)
                    elif -0.35 <= angle <= 0.35: sectors[1].append(value)
                    elif 0.35 < angle <= 1.15: sectors[0].append(value)
            if all(sectors):
                self.scan = tuple(sorted(s)[max(0, len(s)//10)] for s in sectors)
                self.seen["scan"] = self.now_s()
        def tick(self):
            now = self.now_s()
            fresh = (self.xy is not None and self.scan is not None and
                     now - self.seen["scan"] <= self.timeout and
                     now - self.seen["odom"] <= self.timeout and
                     (not self.require_camera_ready or
                      now - self.seen["image"] <= self.timeout))
            mission = self.mission.step(self.observation, self.allowed, now)
            # Physical acceptance is enabled incrementally.  A supervisor
            # transition into an unaccepted later stage must never produce a
            # command, even when the global course transform is valid.
            if not stage_motion_enabled(self.stage, self.max_enabled_stage):
                result = (0.0, 0.0, None, 0.0, "STAGE_NOT_ACCEPTED")
            elif self.xy is None:
                result = (0.0, 0.0, None, 0.0, "WAITING_ODOM")
            elif not fresh:
                # Never trust a syntactically valid observation to override
                # the controller's independent raw-sensor freshness gate.
                result = (0.0, 0.0, None, 0.0, "SENSOR_STALE")
            elif mission.state != "RUNNING" and mission.state != "STAGE_COMPLETE":
                result = (0.0, 0.0, None, 0.0, mission.state)
            elif mission.state == "STAGE_COMPLETE":
                result = (0.0, 0.0, self.stage if mission.complete else None, 0.0,
                          "STAGE_COMPLETE")
            else:
                # Mission facts, not placeholder Euclidean distance, own stage
                # completion.  The downstream adapter independently enforces
                # lidar, tilt, permission and command watchdog gates.
                result = (mission.linear, mission.yaw, None, 0.0, mission.state)
            linear, yaw, completion, progress, state = result
            track_state = "INACTIVE"
            cross_track = None
            odom_heading_error = None
            active_track_guard = None
            facts = (self.observation.get("facts", {})
                     if isinstance(self.observation, dict) else {})
            # The entry-line guard is valid only while crossing the four
            # slabs.  After that, stage 1 must make the official 90-degree
            # turn through the right opening; holding the old odom line would
            # incorrectly fight that turn.
            if stage_1_entry_guard_required(self.stage, facts):
                active_track_guard = self.stage_1_track_guard
            elif self.stage == 1:
                self.stage_1_track_guard.reset()
            if state == "RUNNING" and active_track_guard is not None and self.odom_pose is not None:
                linear, yaw, cross_track, odom_heading_error, track_state = (
                    active_track_guard.correct(
                        *self.odom_pose, linear, yaw))
                if track_state == "TRACK_DEVIATION": state = track_state
            boundary_state = "INACTIVE"
            boundary_margin = None
            predicted_boundary_margin = None
            if state == "RUNNING":
                course_pose = (self.observation.get("course_pose")
                               if isinstance(self.observation, dict) else None)
                linear, yaw, boundary_margin, predicted_boundary_margin, boundary_state = (
                    self.boundary_guard.correct(course_pose, linear, yaw))
                if boundary_state in ("BOUNDARY_POSE_INVALID", "BOUNDARY_STOP",
                                       "BOUNDARY_PREDICTED_STOP"):
                    state = boundary_state
            cmd = Twist(); cmd.linear.x = linear; cmd.angular.z = yaw; self.pub.publish(cmd)
            if completion is not None:
                msg = Int32(); msg.data = completion; self.done_pub.publish(msg)
            status = String(); status.data = json.dumps({"state": state, "stage": self.stage,
                "progress_m": round(progress, 3), "run_allowed": self.allowed,
                "sensors_fresh": fresh,
                "course_calibrated": self.core.course_calibrated,
                "geometry_valid": True,
                "geometry_source": self.geometry_source,
                "mission_intent": mission.intent,
                "mission_checkpoint": self.mission.checkpoint,
                "track_guard_state": track_state,
                "boundary_guard_state": boundary_state,
                "boundary_margin_m": (round(boundary_margin, 4)
                                       if boundary_margin is not None else None),
                "predicted_boundary_margin_m": (
                    round(predicted_boundary_margin, 4)
                    if predicted_boundary_margin is not None else None),
                "cross_track_error_m": (round(cross_track, 4)
                                          if cross_track is not None else None),
                "odom_heading_error_rad": (round(odom_heading_error, 4)
                                             if odom_heading_error is not None else None)},
                separators=(",", ":")); self.status_pub.publish(status)

    rclpy.init(); node = Controller()
    try: rclpy.spin(node)
    finally:
        zero = Twist(); node.pub.publish(zero)
        if node.audio_process is not None and node.audio_process.poll() is None:
            node.audio_process.terminate()
        node.destroy_node(); rclpy.shutdown()


if __name__ == "__main__":
    main()
