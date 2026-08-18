#!/usr/bin/env python3
"""Fail-closed six-stage real-robot race controller.

The ROS wrapper is deliberately thin; RaceCore is dependency-free and replay-testable.
Physical limits and the final obstacle stop remain enforced by mi_dog_real_node.
"""

from collections import namedtuple
import json
import math
import time


StageProfile = namedtuple(
    "StageProfile", "name distance_m speed_mps steer_gain min_clearance_m")


DEFAULT_STAGES = (
    StageProfile("stone", 2.0, 0.10, 0.55, 0.42),
    StageProfile("balls", 2.0, 0.08, 0.75, 0.48),
    StageProfile("curve", 2.5, 0.09, 0.95, 0.42),
    StageProfile("tunnel", 2.0, 0.08, 1.10, 0.38),
    StageProfile("bridge", 2.2, 0.06, 1.20, 0.45),
    StageProfile("finish", 2.0, 0.12, 0.45, 0.40),
)


class RaceCore:
    def __init__(self, profiles=DEFAULT_STAGES, course_calibrated=False):
        if len(profiles) != 6 or any(p.distance_m <= 0 or p.speed_mps <= 0 for p in profiles):
            raise ValueError("exactly six positive stage profiles are required")
        self.profiles = tuple(profiles)
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
            self.core = RaceCore(profiles, course_calibrated=course_calibrated)
            self.timeout = float(self.declare_parameter("sensor_timeout_sec", 0.6).value)
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
            latched = QoSProfile(depth=1, reliability=ReliabilityPolicy.RELIABLE,
                                 durability=DurabilityPolicy.TRANSIENT_LOCAL)
            self.pub = self.create_publisher(Twist, command_topic, 10)
            self.done_pub = self.create_publisher(Int32, stage_complete_topic, 10)
            self.status_pub = self.create_publisher(String, status_topic, latched)
            self.allowed = False
            self.stage = 1
            self.xy = None
            self.scan = None
            self.seen = {"image": 0.0, "scan": 0.0, "odom": 0.0}
            self.create_subscription(Image, image_topic, self.on_image, qos_profile_sensor_data)
            self.create_subscription(LaserScan, scan_topic, self.on_scan, qos_profile_sensor_data)
            self.create_subscription(Odometry, odom_topic, self.on_odom, qos_profile_sensor_data)
            self.create_subscription(Bool, run_allowed_topic,
                                     lambda m: setattr(self, "allowed", m.data), latched)
            self.create_subscription(Int32, current_stage_topic, self.on_stage, latched)
            self.create_timer(0.1, self.tick)

        def now_s(self): return time.monotonic()
        def on_image(self, msg):
            if msg.width and msg.height and msg.data: self.seen["image"] = self.now_s()
        def on_odom(self, msg):
            self.xy = (msg.pose.pose.position.x, msg.pose.pose.position.y)
            if all(math.isfinite(v) for v in self.xy): self.seen["odom"] = self.now_s()
        def on_stage(self, msg):
            self.stage = msg.data
            if self.xy is not None: self.core.select_stage(self.stage, *self.xy)
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
            fresh = self.xy is not None and self.scan is not None and all(now-v <= self.timeout for v in self.seen.values())
            if self.xy is None:
                result = (0.0, 0.0, None, 0.0, "WAITING_ODOM")
            else:
                self.core.select_stage(self.stage, *self.xy)
                scan = self.scan or (math.nan, math.nan, math.nan)
                result = self.core.step(*self.xy, *scan, self.allowed, fresh)
            linear, yaw, completion, progress, state = result
            cmd = Twist(); cmd.linear.x = linear; cmd.angular.z = yaw; self.pub.publish(cmd)
            if completion is not None:
                msg = Int32(); msg.data = completion; self.done_pub.publish(msg)
            status = String(); status.data = json.dumps({"state": state, "stage": self.stage,
                "progress_m": round(progress, 3), "run_allowed": self.allowed,
                "sensors_fresh": fresh,
                "course_calibrated": self.core.course_calibrated},
                separators=(",", ":")); self.status_pub.publish(status)

    rclpy.init(); node = Controller()
    try: rclpy.spin(node)
    finally:
        zero = Twist(); node.pub.publish(zero); node.destroy_node(); rclpy.shutdown()


if __name__ == "__main__":
    main()
