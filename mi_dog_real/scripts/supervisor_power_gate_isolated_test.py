#!/usr/bin/env python3
"""Isolated acceptance test for battery and runtime safety latching."""

import os
import signal
import subprocess
import tempfile
import time

import rclpy
from nav_msgs.msg import Odometry
from protocol.msg import BmsStatus, MotionStatus
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy
from std_msgs.msg import Bool, Float32MultiArray, String


PREFIX = "/mi_dog_test/power_gate"


def supervisor_command(checkpoint):
    parameters = {
        "operator_event_topic": f"{PREFIX}/operator_event",
        "stage_complete_topic": f"{PREFIX}/stage_complete",
        "stage_select_topic": f"{PREFIX}/select_stage",
        "state_topic": f"{PREFIX}/state",
        "stage_topic": f"{PREFIX}/current_stage",
        "pause_request_topic": f"{PREFIX}/pause_request",
        "lie_down_request_topic": f"{PREFIX}/lie_down_request",
        "run_allowed_topic": f"{PREFIX}/run_allowed",
        "safe_to_lie_down_topic": f"{PREFIX}/safe_to_lie_down",
        "safety_reason_topic": f"{PREFIX}/safety_reason",
        "odometry_topic": f"{PREFIX}/odometry",
        "motion_status_topic": f"{PREFIX}/motion_status",
        "bms_status_topic": f"{PREFIX}/bms_status",
        "foot_contact_topic": f"{PREFIX}/foot_contact",
        "checkpoint_path": checkpoint,
        "min_battery_soc": "30",
        "sensor_freshness_sec": "0.5",
        "stable_hold_sec": "0.2",
    }
    command = [
        "ros2", "run", "mi_dog_real", "mi_dog_supervisor_node", "--ros-args",
        "-r", "__node:=mi_dog_supervisor_power_gate_isolated",
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
        super().__init__("mi_dog_supervisor_power_gate_probe")
        latched = QoSProfile(
            depth=1,
            durability=DurabilityPolicy.TRANSIENT_LOCAL,
            reliability=ReliabilityPolicy.RELIABLE,
        )
        self.values = {}
        self._subscriptions = [
            self.create_subscription(
                String, f"{PREFIX}/state",
                lambda message: self.values.__setitem__("state", message.data), latched),
            self.create_subscription(
                Bool, f"{PREFIX}/run_allowed",
                lambda message: self.values.__setitem__("run_allowed", message.data), latched),
            self.create_subscription(
                String, f"{PREFIX}/safety_reason",
                lambda message: self.values.__setitem__("safety_reason", message.data), latched),
        ]
        self.event_pub = self.create_publisher(String, f"{PREFIX}/operator_event", 10)
        self.odom_pub = self.create_publisher(Odometry, f"{PREFIX}/odometry", 10)
        self.motion_pub = self.create_publisher(MotionStatus, f"{PREFIX}/motion_status", 10)
        self.bms_pub = self.create_publisher(BmsStatus, f"{PREFIX}/bms_status", 10)
        self.contact_pub = self.create_publisher(
            Float32MultiArray, f"{PREFIX}/foot_contact", 10)

    def publish_inputs(self, soc, wired=False):
        odometry = Odometry()
        odometry.pose.pose.orientation.w = 1.0
        self.odom_pub.publish(odometry)

        motion = MotionStatus()
        motion.switch_status = MotionStatus.NORMAL
        motion.ori_error = 0
        motion.footpos_error = 0
        motion.motor_error = [0] * 12
        self.motion_pub.publish(motion)

        bms = BmsStatus()
        bms.batt_soc = soc
        bms.power_normal = True
        bms.power_wired_charging = wired
        self.bms_pub.publish(bms)

        contact = Float32MultiArray()
        contact.data = [0.5] * 4
        self.contact_pub.publish(contact)

    def sample_until(self, predicate, *, soc, wired=False, timeout=3.0):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            self.publish_inputs(soc, wired)
            rclpy.spin_once(self, timeout_sec=0.04)
            if predicate():
                return True
        return False

    def send_event(self, event):
        message = String()
        message.data = event
        self.event_pub.publish(message)


def main():
    descriptor, checkpoint = tempfile.mkstemp(prefix="mi_dog_power_", suffix=".txt")
    os.close(descriptor)
    process = None
    rclpy.init()
    probe = Probe()
    results = {}
    try:
        process = subprocess.Popen(
            supervisor_command(checkpoint),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        results["initial_down_waiting"] = probe.sample_until(
            lambda: probe.values.get("state") == "DOWN_WAITING", soc=18)
        results["low_soc_reason"] = probe.sample_until(
            lambda: probe.values.get("safety_reason") == "battery_soc_below_minimum", soc=18)
        probe.send_event("START")
        results["low_soc_start_rejected"] = probe.sample_until(
            lambda: probe.values.get("state") == "DOWN_WAITING" and
            probe.values.get("run_allowed") is False,
            soc=18)

        results["healthy_soc_inputs_ready"] = probe.sample_until(
            lambda: probe.values.get("safety_reason") in ("stability_hold", "ready"),
            soc=80)
        probe.send_event("START")
        results["healthy_soc_start_runs"] = probe.sample_until(
            lambda: probe.values.get("state") == "RUNNING" and
            probe.values.get("run_allowed") is True,
            soc=80)
        results["runtime_low_soc_pauses"] = probe.sample_until(
            lambda: probe.values.get("state") == "PAUSED" and
            probe.values.get("run_allowed") is False,
            soc=20)
        results["charge_recovery_does_not_auto_run"] = probe.sample_until(
            lambda: probe.values.get("state") == "PAUSED" and
            probe.values.get("run_allowed") is False,
            soc=80)

        results["recovered_inputs_ready_but_still_paused"] = probe.sample_until(
            lambda: probe.values.get("safety_reason") in ("stability_hold", "ready") and
            probe.values.get("state") == "PAUSED" and
            probe.values.get("run_allowed") is False,
            soc=80)
        probe.send_event("CONTINUE")
        results["explicit_continue_resumes"] = probe.sample_until(
            lambda: probe.values.get("state") == "RUNNING" and
            probe.values.get("run_allowed") is True,
            soc=80)
        results["wired_charging_pauses"] = probe.sample_until(
            lambda: probe.values.get("state") == "PAUSED" and
            probe.values.get("run_allowed") is False,
            soc=80, wired=True)
        results["wired_charging_reason"] = probe.sample_until(
            lambda: probe.values.get("safety_reason") == "wired_charging_motion_inhibited",
            soc=80, wired=True)

        for name, passed in results.items():
            print(f"{name}={passed}")
        if not all(results.values()):
            raise SystemExit(1)
    finally:
        if process is not None:
            stop_process(process)
        probe.destroy_node()
        rclpy.shutdown()
        try:
            os.unlink(checkpoint)
        except FileNotFoundError:
            pass


if __name__ == "__main__":
    main()
