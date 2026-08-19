#!/usr/bin/env python3
"""Prove raw image staleness overrides a fresh-looking observation."""
import json, os, signal, subprocess, time
import rclpy
from geometry_msgs.msg import Twist
from nav_msgs.msg import Odometry
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy, qos_profile_sensor_data
from sensor_msgs.msg import Image, LaserScan
from std_msgs.msg import Bool, Int32, String

PREFIX = "/mi_dog_test/race_sensor_stale"


def command():
    parameters = {
        "course_calibrated": "true", "sensor_timeout_sec": "0.4",
        "camera_topic": PREFIX + "/image", "lidar_topic": PREFIX + "/scan",
        "odometry_topic": PREFIX + "/odom", "command_topic": PREFIX + "/cmd",
        "stage_complete_topic": PREFIX + "/complete", "status_topic": PREFIX + "/status",
        "run_allowed_topic": PREFIX + "/allowed", "current_stage_topic": PREFIX + "/stage",
        "perception_topic": PREFIX + "/observation",
    }
    result = ["ros2", "run", "mi_dog_real", "race_controller.py", "--ros-args",
              "-r", "__node:=mi_dog_race_sensor_stale_isolated"]
    for key, value in parameters.items(): result.extend(["-p", "%s:=%s" % (key, value)])
    return result


class Probe(Node):
    def __init__(self):
        Node.__init__(self, "mi_dog_race_sensor_stale_probe")
        latched = QoSProfile(depth=1, reliability=ReliabilityPolicy.RELIABLE,
                             durability=DurabilityPolicy.TRANSIENT_LOCAL)
        self.image_pub = self.create_publisher(Image, PREFIX + "/image", qos_profile_sensor_data)
        self.scan_pub = self.create_publisher(LaserScan, PREFIX + "/scan", qos_profile_sensor_data)
        self.odom_pub = self.create_publisher(Odometry, PREFIX + "/odom", qos_profile_sensor_data)
        self.allowed_pub = self.create_publisher(Bool, PREFIX + "/allowed", latched)
        self.stage_pub = self.create_publisher(Int32, PREFIX + "/stage", latched)
        self.observation_pub = self.create_publisher(String, PREFIX + "/observation", 10)
        self.commands, self.statuses = [], []
        self.create_subscription(Twist, PREFIX + "/cmd", self.commands.append, 10)
        self.create_subscription(String, PREFIX + "/status",
                                 lambda m: self.statuses.append(json.loads(m.data)), latched)

    def publish(self, include_image):
        if include_image:
            image = Image(); image.width = 1; image.height = 1
            image.encoding = "mono8"; image.step = 1; image.data = [1]
            self.image_pub.publish(image)
        scan = LaserScan(); scan.angle_min = -1.2; scan.angle_increment = .1
        scan.range_min = .1; scan.range_max = 10.; scan.ranges = [2.] * 25
        odom = Odometry(); odom.pose.pose.orientation.w = 1.
        allowed = Bool(); allowed.data = True
        stage = Int32(); stage.data = 1
        observation = String(); observation.data = json.dumps({
            "schema": "mi_dog_course_observation_v1", "localization_confidence": .9,
            "front_clearance_m": 2., "heading_error_rad": 0., "facts": {}})
        self.scan_pub.publish(scan); self.odom_pub.publish(odom)
        self.allowed_pub.publish(allowed); self.stage_pub.publish(stage)
        self.observation_pub.publish(observation)


def run_phase(probe, seconds, include_image):
    probe.commands[:] = []; probe.statuses[:] = []
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        probe.publish(include_image); rclpy.spin_once(probe, timeout_sec=.05); time.sleep(.02)


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
        run_phase(probe, 2.5, True)
        assert probe.commands and any(command.linear.x > 0. for command in probe.commands)
        run_phase(probe, 1.2, False)
        stale_commands = probe.commands[-5:]
        assert stale_commands and all(abs(command.linear.x) < 1e-9 and
                                      abs(command.angular.z) < 1e-9
                                      for command in stale_commands)
        assert any(status.get("state") == "SENSOR_STALE" for status in probe.statuses)
        print("controller_fresh_sensor_motion_candidate=PASS")
        print("controller_raw_sensor_stale_zero=PASS")
    finally:
        stop(process); probe.destroy_node(); rclpy.shutdown()


if __name__ == "__main__": main()
