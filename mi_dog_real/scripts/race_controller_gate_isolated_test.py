#!/usr/bin/env python3
"""Verify the default course gate entirely on isolated ROS topics."""

import json
import os
import signal
import subprocess
import time

import rclpy
from geometry_msgs.msg import Twist
from nav_msgs.msg import Odometry
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy, qos_profile_sensor_data
from sensor_msgs.msg import Image, LaserScan
from std_msgs.msg import Bool, Int32, String


PREFIX = "/mi_dog_test/race_course_gate"


def controller_command():
    parameters = {
        "course_calibrated": "false",
        "sensor_timeout_sec": "0.6",
        "camera_topic": f"{PREFIX}/image",
        "lidar_topic": f"{PREFIX}/scan",
        "odometry_topic": f"{PREFIX}/odom",
        "command_topic": f"{PREFIX}/safe_cmd_vel",
        "stage_complete_topic": f"{PREFIX}/stage_complete",
        "status_topic": f"{PREFIX}/status",
        "run_allowed_topic": f"{PREFIX}/run_allowed",
        "current_stage_topic": f"{PREFIX}/current_stage",
        "perception_topic": f"{PREFIX}/course_observation",
    }
    command = [
        "ros2", "run", "mi_dog_real", "race_controller.py", "--ros-args",
        "-r", "__node:=mi_dog_race_course_gate_isolated",
    ]
    for name, value in parameters.items():
        command.extend(["-p", f"{name}:={value}"])
    return command


def stop_process(process):
    if process.poll() is not None:
        return
    os.killpg(process.pid, signal.SIGTERM)
    try:
        process.wait(timeout=3)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGKILL)
        process.wait(timeout=3)


class Probe(Node):
    def __init__(self):
        super().__init__("mi_dog_race_course_gate_probe")
        latched = QoSProfile(
            depth=1,
            reliability=ReliabilityPolicy.RELIABLE,
            durability=DurabilityPolicy.TRANSIENT_LOCAL,
        )
        self.commands = []
        self.completions = []
        self.statuses = []
        self.image_pub = self.create_publisher(
            Image, f"{PREFIX}/image", qos_profile_sensor_data)
        self.scan_pub = self.create_publisher(
            LaserScan, f"{PREFIX}/scan", qos_profile_sensor_data)
        self.odom_pub = self.create_publisher(
            Odometry, f"{PREFIX}/odom", qos_profile_sensor_data)
        self.allowed_pub = self.create_publisher(Bool, f"{PREFIX}/run_allowed", latched)
        self.stage_pub = self.create_publisher(Int32, f"{PREFIX}/current_stage", latched)
        self.create_subscription(
            Twist, f"{PREFIX}/safe_cmd_vel", self.commands.append, 10)
        self.create_subscription(
            Int32, f"{PREFIX}/stage_complete", self.completions.append, 10)
        self.create_subscription(
            String, f"{PREFIX}/status", lambda message: self.statuses.append(message.data), latched)

    def publish_inputs(self):
        image = Image()
        image.width = 1
        image.height = 1
        image.encoding = "mono8"
        image.step = 1
        image.data = [1]
        scan = LaserScan()
        scan.angle_min = -1.2
        scan.angle_max = 1.2
        scan.angle_increment = 0.1
        scan.range_min = 0.1
        scan.range_max = 10.0
        scan.ranges = [2.0] * 25
        odom = Odometry()
        odom.pose.pose.orientation.w = 1.0
        allowed = Bool()
        allowed.data = True
        stage = Int32()
        stage.data = 1
        self.image_pub.publish(image)
        self.scan_pub.publish(scan)
        self.odom_pub.publish(odom)
        self.allowed_pub.publish(allowed)
        self.stage_pub.publish(stage)


def main():
    rclpy.init()
    probe = Probe()
    process = subprocess.Popen(
        controller_command(),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    try:
        deadline = time.monotonic() + 4.0
        while time.monotonic() < deadline:
            probe.publish_inputs()
            rclpy.spin_once(probe, timeout_sec=0.05)
            time.sleep(0.02)
        decoded = []
        for value in probe.statuses:
            try:
                decoded.append(json.loads(value))
            except ValueError:
                pass
        results = {
            "isolated_commands_received": bool(probe.commands),
            "all_commands_zero": bool(probe.commands) and all(
                abs(command.linear.x) <= 1e-9 and
                abs(command.linear.y) <= 1e-9 and
                abs(command.angular.z) <= 1e-9
                for command in probe.commands),
            "no_stage_completion": not probe.completions,
            "course_gate_reported": any(
                status.get("state") == "COURSE_UNCALIBRATED" and
                status.get("course_calibrated") is False and
                status.get("sensors_fresh") is True
                for status in decoded),
        }
        for name, passed in results.items():
            print(f"{name}={passed}")
        print(f"command_samples={len(probe.commands)}")
        if not all(results.values()):
            raise SystemExit(1)
    finally:
        stop_process(process)
        probe.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
