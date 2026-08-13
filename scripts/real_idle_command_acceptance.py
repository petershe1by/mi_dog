#!/usr/bin/env python3
"""Verify that a real zero Twist stays out of the walking gait."""

import math
import os
import signal
import subprocess
import sys
import threading
import time

import rclpy
from geometry_msgs.msg import Twist
from nav_msgs.msg import Odometry
from protocol.msg import BmsStatus, MotionServoCmd, MotionStatus
from rcl_interfaces.srv import GetParameters
from rclpy.executors import MultiThreadedExecutor
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy
from std_msgs.msg import Bool, Float32MultiArray, String


ACK = "I_ACKNOWLEDGE_REAL_IDLE_COMMAND"
NS = "/mi_desktop_48_b0_2d_7a_fe_40"
COMMAND_TOPIC = "/mi_dog_test/real_idle/safe_cmd_vel"
MOTION_TOPIC = f"{NS}/motion_servo_cmd"


def adapter_command():
    parameters = {
        "enable_motion": "true",
        "arm_token": "I_UNDERSTAND_REAL_ROBOT_RISK",
        "require_sensor_ready": "false",
        "require_estop_ready": "false",
        "require_voice_start": "false",
        "require_supervisor_run_allowed": "true",
        "motion_topic": MOTION_TOPIC,
        "command_topic": COMMAND_TOPIC,
        "supervisor_run_allowed_topic": "/mi_dog_real/supervisor/run_allowed",
        "camera_topic": "/mi_dog_test/real_idle/no_image",
        "lidar_topic": "/mi_dog_test/real_idle/no_scan",
        "pose_topic": "/mi_dog_test/real_idle/no_pose",
        "odometry_topic": f"{NS}/odom_out",
        "estop_topic": "/mi_dog_test/real_idle/no_estop",
        "voice_command_topic": "/mi_dog_test/real_idle/no_voice",
        "touch_topic": "/mi_dog_test/real_idle/no_touch",
        "wake_event_topic": "/mi_dog_test/real_idle/no_wake",
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
        "-r", "__node:=mi_dog_real_idle_acceptance",
    ]
    for name, value in parameters.items():
        command.extend(["-p", f"{name}:={value}"])
    return command


def stop_process(process):
    if process is None or process.poll() is not None:
        return
    os.killpg(process.pid, signal.SIGTERM)
    try:
        process.wait(timeout=3)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGKILL)
        process.wait(timeout=3)


class Probe(Node):
    def __init__(self):
        super().__init__("mi_dog_real_idle_acceptance_probe")
        latched = QoSProfile(
            depth=1,
            durability=DurabilityPolicy.TRANSIENT_LOCAL,
            reliability=ReliabilityPolicy.RELIABLE,
        )
        self.state = None
        self.run_allowed = None
        self.bms = None
        self.odom = None
        self.frames = []
        self.contacts = []
        self.statuses = []
        self.command_pub = self.create_publisher(Twist, COMMAND_TOPIC, 10)
        self.operator_pub = self.create_publisher(
            String, "/mi_dog_real/operator_event", 10)
        self.create_subscription(
            String, "/mi_dog_real/supervisor/state",
            lambda message: setattr(self, "state", message.data), latched)
        self.create_subscription(
            Bool, "/mi_dog_real/supervisor/run_allowed",
            lambda message: setattr(self, "run_allowed", message.data), latched)
        self.create_subscription(
            BmsStatus, f"{NS}/bms_status",
            lambda message: setattr(self, "bms", message),
            rclpy.qos.qos_profile_sensor_data)
        self.create_subscription(
            Odometry, f"{NS}/odom_out", self.on_odom,
            rclpy.qos.qos_profile_sensor_data)
        self.create_subscription(
            MotionStatus, f"{NS}/motion_status", self.on_status,
            rclpy.qos.qos_profile_sensor_data)
        self.create_subscription(
            Float32MultiArray, "/mi_dog_real/foot_contact_estimate",
            lambda message: self.contacts.append(
                (time.monotonic(), list(message.data))),
            rclpy.qos.qos_profile_sensor_data)
        self.create_subscription(
            MotionServoCmd, MOTION_TOPIC,
            lambda message: self.frames.append((time.monotonic(), message)), 10)

    def on_odom(self, message):
        self.odom = message

    def on_status(self, message):
        self.statuses.append(
            (time.monotonic(), int(message.switch_status), int(message.motion_id)))

    def wait_until(self, predicate, timeout):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if predicate():
                return True
            time.sleep(0.02)
        return False

    def event(self, value):
        message = String()
        message.data = value
        self.operator_pub.publish(message)

    def publish_idle_for(self, seconds):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            self.command_pub.publish(Twist())
            time.sleep(0.02)

    def formal_motion_disabled(self):
        client = self.create_client(GetParameters, "/mi_dog_real/get_parameters")
        if not client.wait_for_service(timeout_sec=3.0):
            return None
        request = GetParameters.Request()
        request.names = ["enable_motion"]
        future = client.call_async(request)
        deadline = time.monotonic() + 3.0
        while time.monotonic() < deadline and not future.done():
            time.sleep(0.02)
        if not future.done() or future.result() is None or not future.result().values:
            return None
        return future.result().values[0].bool_value is False


def main():
    if len(sys.argv) != 2 or sys.argv[1] != ACK:
        print(f"usage: {sys.argv[0]} {ACK}", file=sys.stderr)
        return 2
    results = {}
    error_text = None
    process = None
    probe = None
    executor = None
    thread = None
    rclpy.init()
    try:
        probe = Probe()
        executor = MultiThreadedExecutor(num_threads=2)
        executor.add_node(probe)
        thread = threading.Thread(target=executor.spin, daemon=True)
        thread.start()
        ready = probe.wait_until(
            lambda: probe.state in ("DOWN_WAITING", "PAUSED") and
            probe.run_allowed is False and probe.bms is not None and
            probe.odom is not None and bool(probe.statuses), 10.0)
        results["initial_inputs_ready"] = ready
        if not ready:
            raise RuntimeError("initial safety inputs did not become ready")
        results["formal_enable_motion_false"] = probe.formal_motion_disabled() is True
        results["battery_at_least_50"] = int(probe.bms.batt_soc) >= 50
        results["wired_charging_false"] = not probe.bms.power_wired_charging
        results["bms_power_normal"] = bool(probe.bms.power_normal)
        results["initial_motion_normal"] = probe.statuses[-1][1] == 0
        if not all(results.values()):
            raise RuntimeError("preflight safety check failed")

        process = subprocess.Popen(
            adapter_command(), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            universal_newlines=True, start_new_session=True)
        results["adapter_subscriber_ready"] = probe.wait_until(
            lambda: probe.command_pub.get_subscription_count() == 1, 8.0)
        if not results["adapter_subscriber_ready"]:
            raise RuntimeError("temporary adapter did not subscribe")
        time.sleep(1.5)
        probe.event("START")
        results["supervisor_started"] = probe.wait_until(
            lambda: probe.state == "RUNNING" and probe.run_allowed is True, 5.0)
        if not results["supervisor_started"]:
            raise RuntimeError("supervisor refused START")

        frame_index = len(probe.frames)
        contact_index = len(probe.contacts)
        status_index = len(probe.statuses)
        start_position = probe.odom.pose.pose.position
        start_xy = (start_position.x, start_position.y)
        probe.publish_idle_for(1.0)
        probe.event("PAUSE")
        time.sleep(0.8)

        frames = probe.frames[frame_index:]
        contacts = [values for _, values in probe.contacts[contact_index:]
                    if len(values) == 4]
        statuses = probe.statuses[status_index:]
        end_position = probe.odom.pose.pose.position
        xy_delta = math.hypot(
            end_position.x - start_xy[0], end_position.y - start_xy[1])
        results["idle_has_end_heartbeat"] = any(
            message.cmd_type == MotionServoCmd.SERVO_END for _, message in frames)
        results["idle_has_no_start_or_data"] = not any(
            message.cmd_type in (MotionServoCmd.SERVO_START, MotionServoCmd.SERVO_DATA)
            for _, message in frames)
        results["all_frames_zero_velocity_and_step"] = bool(frames) and all(
            len(message.vel_des) == 3 and
            all(abs(value) <= 1e-9 for value in message.vel_des) and
            len(message.step_height) == 2 and
            all(abs(value) <= 1e-9 for value in message.step_height)
            for _, message in frames)
        results["motion_status_never_entered_303"] = bool(statuses) and all(
            motion_id != 303 for _, _, motion_id in statuses)
        results["motion_switch_stayed_normal"] = bool(statuses) and all(
            switch == 0 for _, switch, _ in statuses)
        results["foot_contact_samples_sufficient"] = len(contacts) >= 40
        results["all_foot_contacts_positive"] = bool(contacts) and all(
            value > 0.0 for values in contacts for value in values)
        results["odom_xy_delta_under_1cm"] = xy_delta < 0.01
        results["final_state_paused"] = (
            probe.state == "PAUSED" and probe.run_allowed is False)

        print(f"battery_percent={int(probe.bms.batt_soc)}")
        print(f"motion_frame_types={[message.cmd_type for _, message in frames]}")
        print(f"motion_status_unique={sorted(set((s, m) for _, s, m in statuses))}")
        print(f"foot_contact_samples={len(contacts)}")
        if contacts:
            print("foot_contact_minima=" + str([
                min(values[index] for values in contacts) for index in range(4)]))
        print(f"odom_xy_delta_m={xy_delta:.6f}")
    except Exception as error:
        error_text = str(error)
        print(f"acceptance_error={error}", file=sys.stderr)
    finally:
        if probe is not None:
            probe.event("PAUSE")
            time.sleep(0.3)
        stop_process(process)
        if process is not None and process.stdout is not None:
            output = process.stdout.read()[-3000:]
            if output:
                print("adapter_log_tail_begin")
                print(output, end="" if output.endswith("\n") else "\n")
                print("adapter_log_tail_end")
        if executor is not None:
            executor.shutdown()
        if thread is not None:
            thread.join(timeout=2)
        if probe is not None:
            probe.destroy_node()
        rclpy.shutdown()

    for name, passed in results.items():
        print(f"{name}={passed}")
    required = {
        "initial_inputs_ready", "formal_enable_motion_false",
        "battery_at_least_50", "wired_charging_false", "bms_power_normal",
        "initial_motion_normal", "adapter_subscriber_ready", "supervisor_started",
        "idle_has_end_heartbeat", "idle_has_no_start_or_data",
        "all_frames_zero_velocity_and_step", "motion_status_never_entered_303",
        "motion_switch_stayed_normal", "foot_contact_samples_sufficient",
        "all_foot_contacts_positive", "odom_xy_delta_under_1cm",
        "final_state_paused",
    }
    passed = error_text is None and set(results) == required and all(results.values())
    print(f"REAL_IDLE_COMMAND_ACCEPTANCE={'PASS' if passed else 'FAIL'}")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
