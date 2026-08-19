#!/usr/bin/env python3
"""Conservative real-sensor producer for the six-stage mission contract."""
import json
import math
import time


def _finite(value):
    return isinstance(value, (int, float)) and math.isfinite(value)


def yaw_from_quaternion(x, y, z, w):
    values = (x, y, z, w)
    if not all(_finite(value) for value in values):
        raise ValueError("non-finite quaternion")
    norm = math.sqrt(sum(value * value for value in values))
    if norm < 1e-6:
        raise ValueError("zero quaternion")
    x, y, z, w = (value / norm for value in values)
    return math.atan2(2.0 * (w * z + x * y), 1.0 - 2.0 * (y * y + z * z))


class SiteLocalization(object):
    def __init__(self, origin_x=0.0, origin_y=0.0, origin_yaw=0.0,
                 transform_valid=False, max_jump_m=0.40):
        values = (origin_x, origin_y, origin_yaw, max_jump_m)
        if not all(_finite(value) for value in values) or max_jump_m <= 0.0:
            raise ValueError("invalid site localization parameters")
        self.origin_x = float(origin_x)
        self.origin_y = float(origin_y)
        self.origin_yaw = float(origin_yaw)
        self.transform_valid = bool(transform_valid)
        self.max_jump_m = float(max_jump_m)
        self.previous = None

    def update(self, odom_x, odom_y, odom_yaw):
        if not all(_finite(value) for value in (odom_x, odom_y, odom_yaw)):
            self.previous = None
            return None, 0.0, "ODOM_INVALID"
        jump = 0.0 if self.previous is None else math.hypot(
            odom_x - self.previous[0], odom_y - self.previous[1])
        self.previous = (odom_x, odom_y)
        if jump > self.max_jump_m:
            return None, 0.0, "ODOM_JUMP"
        if not self.transform_valid:
            return None, 0.0, "SITE_TRANSFORM_UNCALIBRATED"
        dx, dy = odom_x - self.origin_x, odom_y - self.origin_y
        c, s = math.cos(self.origin_yaw), math.sin(self.origin_yaw)
        course_x = c * dx + s * dy
        course_y = -s * dx + c * dy
        heading = math.atan2(math.sin(odom_yaw - self.origin_yaw),
                             math.cos(odom_yaw - self.origin_yaw))
        return (course_x, course_y, heading), 0.85, "LOCALIZED_ODOM"


def extract_colour_features(data, width, height, encoding, step,
                            sample_stride=6, min_colour_pixels=8):
    if encoding not in ("bgr8", "rgb8"):
        raise ValueError("unsupported image encoding")
    if width <= 0 or height <= 0 or step < width * 3 or sample_stride <= 0:
        raise ValueError("invalid image geometry")
    if len(data) < step * height:
        raise ValueError("truncated image")
    orange_x, yellow_left, yellow_right = [], [], []
    samples = 0
    for y in range(height // 3, height, sample_stride):
        row = y * step
        for x in range(0, width, sample_stride):
            offset = row + x * 3
            first, green, third = data[offset], data[offset + 1], data[offset + 2]
            blue, red = (first, third) if encoding == "bgr8" else (third, first)
            samples += 1
            if red >= 150 and 45 <= green <= 190 and blue <= 105 and red >= green + 35:
                orange_x.append(x)
            if red >= 145 and green >= 135 and blue <= 115 and abs(red - green) <= 90:
                (yellow_left if x < width / 2.0 else yellow_right).append(x)
    orange_seen = len(orange_x) >= min_colour_pixels
    both_boundaries = (len(yellow_left) >= min_colour_pixels and
                       len(yellow_right) >= min_colour_pixels)
    lane_center, heading_error = None, 0.0
    if both_boundaries:
        lane_center = (sum(yellow_left) / float(len(yellow_left)) +
                       sum(yellow_right) / float(len(yellow_right))) / 2.0
        normalized = (lane_center - width / 2.0) / max(1.0, width / 2.0)
        heading_error = max(-0.25, min(0.25, -normalized * 0.35))
    return {
        "orange_seen": orange_seen,
        "orange_pixels": len(orange_x),
        "orange_center_x_norm": (sum(orange_x) / float(len(orange_x)) / width
                                  if orange_seen else None),
        "yellow_left_pixels": len(yellow_left),
        "yellow_right_pixels": len(yellow_right),
        "lane_boundaries_seen": both_boundaries,
        "lane_center_x_norm": lane_center / width if lane_center is not None else None,
        "heading_error_rad": heading_error,
        "sample_count": samples,
    }


def front_clearance(ranges, angle_min, angle_increment, range_min, range_max):
    values = []
    for index, value in enumerate(ranges):
        angle = angle_min + index * angle_increment
        if (-0.30 <= angle <= 0.30 and _finite(value) and
                range_min <= value <= range_max):
            values.append(float(value))
    if not values:
        return 0.0
    values.sort()
    return values[max(0, len(values) // 10)]


def main():
    import rclpy
    from nav_msgs.msg import Odometry
    from rclpy.node import Node
    from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy, qos_profile_sensor_data
    from sensor_msgs.msg import Image, LaserScan
    from std_msgs.msg import Int32, String

    class Producer(Node):
        def __init__(self):
            super().__init__("mi_dog_course_perception")
            image_topic = self.declare_parameter("camera_topic", "/image").value
            scan_topic = self.declare_parameter("lidar_topic", "/scan").value
            odom_topic = self.declare_parameter("odometry_topic", "/odom_out").value
            stage_topic = self.declare_parameter("current_stage_topic", "/mi_dog_real/supervisor/current_stage").value
            output_topic = self.declare_parameter("observation_topic", "/mi_dog_real/course_observation").value
            status_topic = self.declare_parameter("status_topic", "/mi_dog_real/course_perception/status").value
            self.timeout = float(self.declare_parameter("sensor_timeout_sec", 0.6).value)
            self.sample_stride = int(self.declare_parameter("sample_stride", 6).value)
            self.min_colour_pixels = int(self.declare_parameter("min_colour_pixels", 8).value)
            self.localization = SiteLocalization(
                float(self.declare_parameter("site_origin_x_m", 0.0).value),
                float(self.declare_parameter("site_origin_y_m", 0.0).value),
                float(self.declare_parameter("site_origin_yaw_rad", 0.0).value),
                bool(self.declare_parameter("site_transform_valid", False).value),
                float(self.declare_parameter("max_odom_jump_m", 0.40).value))
            latched = QoSProfile(depth=1, reliability=ReliabilityPolicy.RELIABLE,
                                 durability=DurabilityPolicy.TRANSIENT_LOCAL)
            self.publisher = self.create_publisher(String, output_topic, 10)
            self.status_publisher = self.create_publisher(String, status_topic, latched)
            self.stage, self.image, self.clearance, self.pose = 1, None, None, None
            self.localization_confidence = 0.0
            self.localization_state = "ODOM_MISSING"
            self.seen = {"image": 0.0, "scan": 0.0, "odom": 0.0}
            self.create_subscription(Image, image_topic, self.on_image, qos_profile_sensor_data)
            self.create_subscription(LaserScan, scan_topic, self.on_scan, qos_profile_sensor_data)
            self.create_subscription(Odometry, odom_topic, self.on_odom, qos_profile_sensor_data)
            self.create_subscription(Int32, stage_topic, self.on_stage, latched)
            self.create_timer(0.1, self.publish_observation)

        @staticmethod
        def now_s(): return time.monotonic()

        def on_stage(self, message):
            if message.data in range(1, 7): self.stage = message.data

        def on_image(self, message):
            try:
                self.image = extract_colour_features(
                    message.data, message.width, message.height, message.encoding,
                    message.step, self.sample_stride, self.min_colour_pixels)
                self.seen["image"] = self.now_s()
            except (TypeError, ValueError, IndexError):
                self.image = None

        def on_scan(self, message):
            self.clearance = front_clearance(message.ranges, message.angle_min,
                                             message.angle_increment, message.range_min,
                                             message.range_max)
            if self.clearance > 0.0: self.seen["scan"] = self.now_s()

        def on_odom(self, message):
            orientation = message.pose.pose.orientation
            try:
                yaw = yaw_from_quaternion(orientation.x, orientation.y,
                                          orientation.z, orientation.w)
                self.pose, self.localization_confidence, self.localization_state = self.localization.update(
                    message.pose.pose.position.x, message.pose.pose.position.y, yaw)
                self.seen["odom"] = self.now_s()
            except ValueError:
                self.pose, self.localization_confidence = None, 0.0
                self.localization_state = "ODOM_INVALID"

        def publish_observation(self):
            now = self.now_s()
            fresh = {name: stamp > 0.0 and now - stamp <= self.timeout
                     for name, stamp in self.seen.items()}
            image = self.image if fresh["image"] and self.image is not None else {}
            confidence = self.localization_confidence if all(fresh.values()) else 0.0
            observation = {
                "schema": "mi_dog_course_observation_v1", "monotonic_stamp": now,
                "stage": self.stage, "localization_confidence": confidence,
                "localization_state": self.localization_state,
                "site_transform_valid": self.localization.transform_valid,
                "course_pose": self.pose,
                "front_clearance_m": self.clearance if fresh["scan"] else 0.0,
                "heading_error_rad": image.get("heading_error_rad", 0.0),
                "detections": image, "facts": {}, "sensors_fresh": fresh,
            }
            message = String()
            message.data = json.dumps(observation, sort_keys=True, separators=(",", ":"), allow_nan=False)
            self.publisher.publish(message)
            status = String()
            status.data = json.dumps({
                "schema": observation["schema"],
                "site_transform_valid": self.localization.transform_valid,
                "localization_state": self.localization_state,
                "localization_confidence": confidence, "sensors_fresh": fresh,
                "facts_are_physical_only": True,
            }, sort_keys=True, separators=(",", ":"))
            self.status_publisher.publish(status)

    rclpy.init(); node = Producer()
    try: rclpy.spin(node)
    finally: node.destroy_node(); rclpy.shutdown()


if __name__ == "__main__": main()
