#!/usr/bin/env python3
"""ROS isolation test for the real course observation producer; no robot topics."""
import json, math, os, signal, subprocess, time
import rclpy
from nav_msgs.msg import Odometry
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy, qos_profile_sensor_data
from sensor_msgs.msg import Image, LaserScan
from std_msgs.msg import Int32, String

PREFIX = "/mi_dog_test/course_perception"


def command():
    values = {
        "camera_topic": PREFIX + "/image", "lidar_topic": PREFIX + "/scan",
        "odometry_topic": PREFIX + "/odom", "current_stage_topic": PREFIX + "/stage",
        "observation_topic": PREFIX + "/observation", "status_topic": PREFIX + "/status",
        "sensor_timeout_sec": "0.4", "site_transform_valid": "false",
    }
    result = ["ros2", "run", "mi_dog_real", "course_perception.py", "--ros-args",
              "-r", "__node:=mi_dog_course_perception_isolated"]
    for key, value in values.items(): result.extend(["-p", "%s:=%s" % (key, value)])
    return result


class Probe(Node):
    def __init__(self):
        Node.__init__(self, "mi_dog_course_perception_isolated_probe")
        latched = QoSProfile(depth=1, reliability=ReliabilityPolicy.RELIABLE,
                             durability=DurabilityPolicy.TRANSIENT_LOCAL)
        self.image_pub = self.create_publisher(Image, PREFIX + "/image", qos_profile_sensor_data)
        self.scan_pub = self.create_publisher(LaserScan, PREFIX + "/scan", qos_profile_sensor_data)
        self.odom_pub = self.create_publisher(Odometry, PREFIX + "/odom", qos_profile_sensor_data)
        self.stage_pub = self.create_publisher(Int32, PREFIX + "/stage", latched)
        self.observations, self.statuses = [], []
        self.create_subscription(String, PREFIX + "/observation",
                                 lambda m: self.observations.append(json.loads(m.data)), 10)
        self.create_subscription(String, PREFIX + "/status",
                                 lambda m: self.statuses.append(json.loads(m.data)), latched)

    def publish(self, include_image=True):
        if include_image:
            image = Image(); image.width = 12; image.height = 12
            image.encoding = "bgr8"; image.step = 36
            image.data = [0] * (image.step * image.height); self.image_pub.publish(image)
        scan = LaserScan(); scan.angle_min = -1.2; scan.angle_increment = .1
        scan.range_min = .1; scan.range_max = 10.; scan.ranges = [2.] * 25
        odom = Odometry(); odom.pose.pose.orientation.w = 1.
        stage = Int32(); stage.data = 2
        self.scan_pub.publish(scan); self.odom_pub.publish(odom); self.stage_pub.publish(stage)


def stop(process):
    if process.poll() is not None: return
    os.killpg(process.pid, signal.SIGTERM)
    try: process.wait(timeout=3)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGKILL); process.wait(timeout=3)


def main():
    rclpy.init(); probe = Probe()
    process = subprocess.Popen(command(), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                               start_new_session=True)
    try:
        deadline = time.monotonic() + 3.
        while time.monotonic() < deadline:
            probe.publish(True); rclpy.spin_once(probe, timeout_sec=.05); time.sleep(.02)
        fresh = [o for o in probe.observations if all(o.get("sensors_fresh", {}).values())]
        assert fresh and all(o.get("facts") == {} for o in fresh)
        assert all(o.get("site_transform_valid") is False for o in fresh)
        assert all(o.get("localization_confidence") == 0. for o in fresh)
        assert any(o.get("stage") == 2 and o.get("front_clearance_m", 0.) > 1. for o in fresh)
        deadline = time.monotonic() + 1.
        while time.monotonic() < deadline:
            probe.publish(False); rclpy.spin_once(probe, timeout_sec=.05); time.sleep(.02)
        assert any(o.get("sensors_fresh", {}).get("image") is False
                   and o.get("localization_confidence") == 0. for o in probe.observations[-20:])
        assert any(s.get("facts_are_physical_only") is True for s in probe.statuses)
        print("course_perception_isolated_fresh=PASS")
        print("course_perception_isolated_stale=PASS")
        print("course_perception_isolated_no_facts=PASS")
    finally:
        stop(process); probe.destroy_node(); rclpy.shutdown()


if __name__ == "__main__": main()
