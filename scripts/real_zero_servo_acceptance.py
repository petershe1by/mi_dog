#!/usr/bin/env python3
"""Bounded real-topic acceptance for zero-velocity servo and stop paths.

This script is intended to run on the CyberDog main computer from stdin.  It
starts a temporary, separately named motion adapter which publishes only to the
real MotionServoCmd topic.  The formal sensor-only node remains unchanged.
"""

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
from rclpy.node import Node
from rclpy.executors import MultiThreadedExecutor
from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy
from std_msgs.msg import Bool, Float32MultiArray, String


ACK = "I_ACKNOWLEDGE_REAL_ZERO_MOTION"
CANARY = os.environ.get("MI_DOG_ZERO_CANARY", "0") == "1"
NS = "/mi_desktop_48_b0_2d_7a_fe_40"
COMMAND_TOPIC = "/mi_dog_test/real_zero/safe_cmd_vel"
MOTION_TOPIC = f"{NS}/motion_servo_cmd"
RUN_ALLOWED_TOPIC = "/mi_dog_real/supervisor/run_allowed"
STATE_TOPIC = "/mi_dog_real/supervisor/state"
OPERATOR_TOPIC = "/mi_dog_real/operator_event"


def stop_process(process):
    if process is None or process.poll() is not None:
        return
    os.killpg(process.pid, signal.SIGTERM)
    try:
        process.wait(timeout=3)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGKILL)
        process.wait(timeout=3)


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
        "supervisor_run_allowed_topic": RUN_ALLOWED_TOPIC,
        "camera_topic": "/mi_dog_test/real_zero/no_image",
        "lidar_topic": "/mi_dog_test/real_zero/no_scan",
        "pose_topic": "/mi_dog_test/real_zero/no_pose",
        "odometry_topic": f"{NS}/odom_out",
        "estop_topic": "/mi_dog_test/real_zero/no_estop",
        "voice_command_topic": "/mi_dog_test/real_zero/no_voice",
        "touch_topic": "/mi_dog_test/real_zero/no_touch",
        "wake_event_topic": "/mi_dog_test/real_zero/no_wake",
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
        "-r", "__node:=mi_dog_real_zero_acceptance",
    ]
    for name, value in parameters.items():
        command.extend(["-p", f"{name}:={value}"])
    return command


class Probe(Node):
    def __init__(self):
        super().__init__("mi_dog_real_zero_acceptance_probe")
        latched = QoSProfile(
            depth=1,
            durability=DurabilityPolicy.TRANSIENT_LOCAL,
            reliability=ReliabilityPolicy.RELIABLE,
        )
        self.state = None
        self.run_allowed = None
        self.bms = None
        self.motion_status = None
        self.motion_status_samples = []
        self.odom = None
        self.frames = []
        self.foot_contacts = []
        self.command_pub = self.create_publisher(Twist, COMMAND_TOPIC, 10)
        self.operator_pub = self.create_publisher(String, OPERATOR_TOPIC, 10)
        self.create_subscription(
            String, STATE_TOPIC, lambda message: setattr(self, "state", message.data), latched)
        self.create_subscription(
            Bool, RUN_ALLOWED_TOPIC,
            lambda message: setattr(self, "run_allowed", message.data), latched)
        self.create_subscription(
            BmsStatus, f"{NS}/bms_status",
            lambda message: setattr(self, "bms", message), rclpy.qos.qos_profile_sensor_data)
        self.create_subscription(
            MotionStatus, f"{NS}/motion_status", self.on_motion_status,
            rclpy.qos.qos_profile_sensor_data)
        self.create_subscription(
            Odometry, f"{NS}/odom_out", lambda message: setattr(self, "odom", message),
            rclpy.qos.qos_profile_sensor_data)
        self.create_subscription(
            MotionServoCmd, MOTION_TOPIC,
            lambda message: self.frames.append((time.monotonic(), message)), 10)
        self.create_subscription(
            Float32MultiArray, "/mi_dog_real/foot_contact_estimate",
            lambda message: self.foot_contacts.append(
                (time.monotonic(), list(message.data))),
            rclpy.qos.qos_profile_sensor_data)

    def on_motion_status(self, message):
        self.motion_status = message
        self.motion_status_samples.append(
            (time.monotonic(), int(message.switch_status), int(message.motion_id)))

    def spin_for(self, seconds, *, publish_zero=False):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            if publish_zero:
                self.command_pub.publish(Twist())
            time.sleep(0.02)

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


def frame_types(frames):
    return [message.cmd_type for _, message in frames]


def all_zero(frames):
    return bool(frames) and all(
        len(message.vel_des) == 3 and
        all(abs(value) <= 1e-9 for value in message.vel_des)
        for _, message in frames
    )


def all_zero_step_height(frames):
    return bool(frames) and all(
        len(message.step_height) == 2 and
        all(abs(value) <= 1e-9 for value in message.step_height)
        for _, message in frames
    )


def has_start_then_data(frames):
    values = frame_types(frames)
    try:
        start = values.index(MotionServoCmd.SERVO_START)
        data = values.index(MotionServoCmd.SERVO_DATA, start + 1)
    except ValueError:
        return False
    return data > start


def main():
    if len(sys.argv) != 2 or sys.argv[1] != ACK:
        print(f"usage: {sys.argv[0]} {ACK}", file=sys.stderr)
        return 2
    process = None
    probe = None
    executor = None
    executor_thread = None
    results = {}
    acceptance_error = None
    rclpy.init()
    try:
        probe = Probe()
        executor = MultiThreadedExecutor(num_threads=2)
        executor.add_node(probe)
        executor_thread = threading.Thread(target=executor.spin, daemon=True)
        executor_thread.start()
        inputs_ready = probe.wait_until(
            lambda: probe.state in ("DOWN_WAITING", "PAUSED") and
            probe.run_allowed is False and probe.bms is not None and
            probe.motion_status is not None and probe.odom is not None,
            10.0,
        )
        results["initial_inputs_ready"] = inputs_ready
        if not inputs_ready:
            raise RuntimeError("initial safety inputs did not become ready")
        results["formal_enable_motion_false"] = probe.formal_motion_disabled() is True
        results["battery_at_least_50"] = int(probe.bms.batt_soc) >= 50
        results["wired_charging_false"] = not probe.bms.power_wired_charging
        results["bms_power_normal"] = bool(probe.bms.power_normal)
        results["motion_switch_normal"] = int(probe.motion_status.switch_status) == 0
        if not all(results.values()):
            raise RuntimeError("preflight safety check failed")

        initial_position = probe.odom.pose.pose.position
        initial_xyz = (initial_position.x, initial_position.y, initial_position.z)
        process = subprocess.Popen(
            adapter_command(), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            universal_newlines=True, start_new_session=True,
        )
        results["adapter_command_subscriber_ready"] = probe.wait_until(
            lambda: probe.command_pub.get_subscription_count() == 1, 8.0)
        if not results["adapter_command_subscriber_ready"]:
            raise RuntimeError("temporary adapter did not subscribe")

        # The armed adapter intentionally emits END while inhibited.  Let the
        # controller complete that transition before asking the supervisor to
        # enter RUNNING, otherwise its delayed status can revoke a fresh START.
        probe.spin_for(1.5)
        results["prestart_controller_restabilized"] = (
            probe.state in ("DOWN_WAITING", "PAUSED") and
            probe.run_allowed is False and
            probe.motion_status is not None and
            int(probe.motion_status.switch_status) == 0)
        if not results["prestart_controller_restabilized"]:
            raise RuntimeError("controller did not restabilize after initial END")

        probe.event("START")
        results["supervisor_started"] = probe.wait_until(
            lambda: probe.state == "RUNNING" and probe.run_allowed is True, 5.0)
        if not results["supervisor_started"]:
            raise RuntimeError("supervisor refused START")

        first_index = len(probe.frames)
        probe.spin_for(0.25 if CANARY else 0.8, publish_zero=True)
        first = probe.frames[first_index:]
        results["real_topic_start_then_data"] = has_start_then_data(first)
        results["real_topic_start_data_zero"] = all_zero([
            frame for frame in first
            if frame[1].cmd_type in (MotionServoCmd.SERVO_START, MotionServoCmd.SERVO_DATA)
        ])

        timeout_frames = []
        second = []
        if not CANARY:
            timeout_index = len(probe.frames)
            timeout_started = time.monotonic()
            probe.spin_for(0.9)
            timeout_frames = probe.frames[timeout_index:]
            timeout_end = next(
                (stamp for stamp, message in timeout_frames
                 if message.cmd_type == MotionServoCmd.SERVO_END), None)
            results["watchdog_sent_end"] = timeout_end is not None
            results["watchdog_end_within_0_50s"] = (
                timeout_end is not None and timeout_end - timeout_started <= 0.50)

            if probe.state == "PAUSED":
                probe.spin_for(1.0)
                probe.event("CONTINUE")
                results["supervisor_rearmed_after_watchdog"] = probe.wait_until(
                    lambda: probe.state == "RUNNING" and probe.run_allowed is True, 5.0)
            else:
                results["supervisor_rearmed_after_watchdog"] = (
                    probe.state == "RUNNING" and probe.run_allowed is True)
            if not results["supervisor_rearmed_after_watchdog"]:
                raise RuntimeError("supervisor could not rearm after watchdog END")

            second_index = len(probe.frames)
            probe.spin_for(0.6, publish_zero=True)
            second = probe.frames[second_index:]
            results["second_session_start_then_data"] = has_start_then_data(second)

        pause_index = len(probe.frames)
        pause_time = time.monotonic()
        probe.event("PAUSE")
        probe.spin_for(0.8, publish_zero=True)
        paused = probe.frames[pause_index:]
        pause_end = next(
            (stamp for stamp, message in paused
             if message.cmd_type == MotionServoCmd.SERVO_END), None)
        results["pause_state_and_permission_revoked"] = (
            probe.state == "PAUSED" and probe.run_allowed is False)
        results["pause_sent_end_within_0_50s"] = (
            pause_end is not None and pause_end - pause_time <= 0.50)
        if pause_end is None:
            results["no_data_after_pause_end"] = False
        else:
            results["no_data_after_pause_end"] = not any(
                stamp > pause_end and message.cmd_type == MotionServoCmd.SERVO_DATA
                for stamp, message in paused)
        results["all_captured_velocities_zero"] = all_zero(
            [frame for frame in first + timeout_frames + second + paused
             if frame[1].cmd_type in (
                 MotionServoCmd.SERVO_START,
                 MotionServoCmd.SERVO_DATA,
                 MotionServoCmd.SERVO_END,
             )]
        )
        results["all_captured_step_heights_zero"] = all_zero_step_height(
            [frame for frame in first + timeout_frames + second + paused
             if frame[1].cmd_type in (
                 MotionServoCmd.SERVO_START,
                 MotionServoCmd.SERVO_DATA,
                 MotionServoCmd.SERVO_END,
             )]
        )

        probe.spin_for(0.3)
        final_position = probe.odom.pose.pose.position
        odom_xy_delta = math.sqrt(
            (final_position.x - initial_xyz[0]) ** 2 +
            (final_position.y - initial_xyz[1]) ** 2)
        odom_z_delta = final_position.z - initial_xyz[2]
        results["odom_xy_delta_under_3cm"] = odom_xy_delta < 0.03
        session_contacts = [
            values for stamp, values in probe.foot_contacts
            if first and stamp >= first[0][0] and len(values) == 4
        ]
        results["foot_contact_samples_sufficient"] = len(session_contacts) >= 40
        results["all_foot_contacts_positive"] = (
            bool(session_contacts) and
            all(value > 0.0 for values in session_contacts for value in values)
        )
        print(f"initial_battery_percent={int(probe.bms.batt_soc)}")
        print(f"initial_wired_charging={str(probe.bms.power_wired_charging).lower()}")
        print(f"canary_mode={str(CANARY).lower()}")
        print(f"first_cmd_types={frame_types(first)}")
        print(f"timeout_cmd_types={frame_types(timeout_frames)}")
        print(f"second_cmd_types={frame_types(second)}")
        print(f"pause_cmd_types={frame_types(paused)}")
        print("motion_status_switch_id_samples=" + str(
            probe.motion_status_samples[-80:]))
        print(f"odom_xy_delta_m={odom_xy_delta:.6f}")
        print(f"odom_z_delta_m={odom_z_delta:.6f}")
        print(f"foot_contact_samples={len(session_contacts)}")
        if session_contacts:
            print("foot_contact_minima=" + str([
                min(values[index] for values in session_contacts)
                for index in range(4)]))
            print("foot_contact_maxima=" + str([
                max(values[index] for values in session_contacts)
                for index in range(4)]))
    except Exception as error:
        acceptance_error = str(error)
        print(f"acceptance_error={error}", file=sys.stderr)
    finally:
        if probe is not None:
            probe.event("PAUSE")
            probe.spin_for(0.3)
        stop_process(process)
        if process is not None and process.stdout is not None:
            output = process.stdout.read()[-4000:]
            if output:
                print("adapter_log_tail_begin")
                print(output, end="" if output.endswith("\n") else "\n")
                print("adapter_log_tail_end")
        if executor is not None:
            executor.shutdown()
        if executor_thread is not None:
            executor_thread.join(timeout=2)
        if probe is not None:
            probe.destroy_node()
        rclpy.shutdown()

    for name, passed in results.items():
        print(f"{name}={passed}")
    required_results = {
        "initial_inputs_ready",
        "formal_enable_motion_false",
        "battery_at_least_50",
        "wired_charging_false",
        "bms_power_normal",
        "motion_switch_normal",
        "adapter_command_subscriber_ready",
        "prestart_controller_restabilized",
        "supervisor_started",
        "real_topic_start_then_data",
        "real_topic_start_data_zero",
        "pause_state_and_permission_revoked",
        "pause_sent_end_within_0_50s",
        "no_data_after_pause_end",
        "all_captured_velocities_zero",
        "all_captured_step_heights_zero",
        "odom_xy_delta_under_3cm",
        "foot_contact_samples_sufficient",
        "all_foot_contacts_positive",
    }
    if not CANARY:
        required_results.update({
            "watchdog_sent_end",
            "watchdog_end_within_0_50s",
            "supervisor_rearmed_after_watchdog",
            "second_session_start_then_data",
        })
    passed = (
        acceptance_error is None and
        required_results == set(results) and
        all(results.values())
    )
    print(f"REAL_ZERO_SERVO_ACCEPTANCE={'PASS' if passed else 'FAIL'}")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
