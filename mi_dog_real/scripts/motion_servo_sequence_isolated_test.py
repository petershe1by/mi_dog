#!/usr/bin/env python3
"""Verify START/DATA/END sequencing on isolated ROS topics with zero velocity."""

import os
import signal
import subprocess
import time

import rclpy
from geometry_msgs.msg import Twist
from protocol.msg import MotionServoCmd
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy
from std_msgs.msg import Bool


PREFIX = "/mi_dog_test/servo_sequence"
ARM_TOKEN = "I_UNDERSTAND_REAL_ROBOT_RISK"


def real_node_command():
    parameters = {
        "enable_motion": "true",
        "arm_token": ARM_TOKEN,
        "require_sensor_ready": "false",
        "require_estop_ready": "false",
        "require_voice_start": "false",
        "require_supervisor_run_allowed": "true",
        "motion_topic": f"{PREFIX}/motion_servo_cmd",
        "command_topic": f"{PREFIX}/safe_cmd_vel",
        "supervisor_run_allowed_topic": f"{PREFIX}/run_allowed",
        "camera_topic": f"{PREFIX}/no_image",
        "lidar_topic": f"{PREFIX}/no_scan",
        "pose_topic": f"{PREFIX}/no_pose",
        "odometry_topic": f"{PREFIX}/no_odom",
        "estop_topic": f"{PREFIX}/no_estop",
        "voice_command_topic": f"{PREFIX}/no_voice",
        "touch_topic": f"{PREFIX}/no_touch",
        "wake_event_topic": f"{PREFIX}/no_wake",
        "audio_feedback_enabled": "false",
        "touch_pause_enabled": "false",
        "publish_wake_word": "false",
        "publish_rate_hz": "20.0",
        "command_timeout_sec": "0.30",
        "supervisor_timeout_sec": "0.50",
        "stop_heartbeat_sec": "0.20",
    }
    command = [
        "ros2", "run", "mi_dog_real", "mi_dog_real_node", "--ros-args",
        "-r", "__node:=mi_dog_servo_sequence_isolated",
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
        super().__init__("mi_dog_servo_sequence_probe")
        latched = QoSProfile(
            depth=1,
            durability=DurabilityPolicy.TRANSIENT_LOCAL,
            reliability=ReliabilityPolicy.RELIABLE,
        )
        self.samples = []
        self.command_pub = self.create_publisher(
            Twist, f"{PREFIX}/safe_cmd_vel", 10)
        self.allowed_pub = self.create_publisher(
            Bool, f"{PREFIX}/run_allowed", latched)
        self.motion_sub = self.create_subscription(
            MotionServoCmd,
            f"{PREFIX}/motion_servo_cmd",
            lambda message: self.samples.append((time.monotonic(), message)),
            10,
        )

    def wait_for_connections(self, timeout=5.0):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            rclpy.spin_once(self, timeout_sec=0.1)
            if (self.command_pub.get_subscription_count() == 1 and
                    self.allowed_pub.get_subscription_count() == 1):
                return True
        return False

    def sample(self, seconds, *, allowed=None, command=False):
        start_index = len(self.samples)
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            if allowed is not None:
                allowed_message = Bool()
                allowed_message.data = allowed
                self.allowed_pub.publish(allowed_message)
            if command:
                self.command_pub.publish(Twist())
            rclpy.spin_once(self, timeout_sec=0.02)
            time.sleep(0.02)
        return [message for _, message in self.samples[start_index:]]


def types(messages):
    return [message.cmd_type for message in messages]


def ordered_start_data(messages):
    frame_types = types(messages)
    try:
        start_index = frame_types.index(MotionServoCmd.SERVO_START)
        data_index = frame_types.index(MotionServoCmd.SERVO_DATA, start_index + 1)
    except ValueError:
        return False
    return data_index > start_index


def zero_velocity(messages, command_type):
    selected = [message for message in messages if message.cmd_type == command_type]
    return bool(selected) and all(
        len(message.vel_des) == 3 and all(abs(value) <= 1e-9 for value in message.vel_des)
        for message in selected
    )


def main():
    process = None
    rclpy.init()
    probe = Probe()
    results = {}
    try:
        process = subprocess.Popen(
            real_node_command(),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        results["isolated_subscribers_ready"] = probe.wait_for_connections()

        initial = probe.sample(0.5, allowed=False)
        first_session = probe.sample(0.9, allowed=True, command=True)
        timeout_phase = probe.sample(0.8, allowed=True, command=False)
        second_session = probe.sample(0.8, allowed=True, command=True)
        revoke_phase = probe.sample(0.6, allowed=False, command=False)
        stale_after_reallow = probe.sample(0.4, allowed=True, command=False)
        third_session = probe.sample(0.8, allowed=True, command=True)

        results["inhibited_has_no_start_or_data"] = not any(
            value in (MotionServoCmd.SERVO_START, MotionServoCmd.SERVO_DATA)
            for value in types(initial)
        )
        results["first_session_start_then_data"] = ordered_start_data(first_session)
        results["start_frame_zero_velocity"] = zero_velocity(
            first_session, MotionServoCmd.SERVO_START)
        results["zero_data_frame_zero_velocity"] = zero_velocity(
            first_session, MotionServoCmd.SERVO_DATA)
        results["command_timeout_sends_end"] = (
            MotionServoCmd.SERVO_END in types(timeout_phase))
        results["second_session_restarts_start_then_data"] = ordered_start_data(
            second_session)
        results["permission_revoke_sends_end"] = (
            MotionServoCmd.SERVO_END in types(revoke_phase))
        results["reallow_without_fresh_command_stays_ended"] = not any(
            value in (MotionServoCmd.SERVO_START, MotionServoCmd.SERVO_DATA)
            for value in types(stale_after_reallow)
        )
        results["fresh_command_starts_third_session"] = ordered_start_data(third_session)
        all_end_frames = [
            message for message in timeout_phase + revoke_phase
            if message.cmd_type == MotionServoCmd.SERVO_END
        ]
        results["end_frames_zero_velocity"] = bool(all_end_frames) and all(
            len(message.vel_des) == 3 and all(abs(value) <= 1e-9 for value in message.vel_des)
            for message in all_end_frames
        )

        for name, messages in (
                ("initial", initial),
                ("first_session", first_session),
                ("timeout", timeout_phase),
                ("second_session", second_session),
                ("revoke", revoke_phase),
                ("reallow_without_command", stale_after_reallow),
                ("third_session", third_session)):
            print(f"phase={name} cmd_types={types(messages)}")
        for name, passed in results.items():
            print(f"{name}={passed}")
        if not all(results.values()):
            raise SystemExit(1)
    finally:
        if process is not None:
            stop_process(process)
        probe.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
