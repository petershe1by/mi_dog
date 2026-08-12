#!/usr/bin/env python3
"""Isolated, no-motion acceptance test for supervisor stage selection."""

import os
import signal
import subprocess
import tempfile
import time

import rclpy
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy
from std_msgs.msg import Int32, String


PREFIX = "/mi_dog_test/stage_select"


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
        "odometry_topic": f"{PREFIX}/no_odometry",
        "motion_status_topic": f"{PREFIX}/no_motion_status",
        "bms_status_topic": f"{PREFIX}/no_bms",
        "foot_contact_topic": f"{PREFIX}/no_foot_contact",
        "checkpoint_path": checkpoint,
    }
    command = [
        "ros2", "run", "mi_dog_real", "mi_dog_supervisor_node", "--ros-args",
        "-r", "__node:=mi_dog_supervisor_stage_test",
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
        super().__init__("mi_dog_supervisor_stage_probe")
        qos = QoSProfile(
            depth=1,
            durability=DurabilityPolicy.TRANSIENT_LOCAL,
            reliability=ReliabilityPolicy.RELIABLE,
        )
        self.state = None
        self.stage = None
        self._subscriptions = [
            self.create_subscription(String, f"{PREFIX}/state", self.on_state, qos),
            self.create_subscription(Int32, f"{PREFIX}/current_stage", self.on_stage, qos),
        ]
        self.event_pub = self.create_publisher(String, f"{PREFIX}/operator_event", 10)
        self.stage_pub = self.create_publisher(Int32, f"{PREFIX}/select_stage", 10)

    def on_state(self, message):
        self.state = message.data

    def on_stage(self, message):
        self.stage = message.data

    def wait_for(self, predicate, timeout=4.0):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            rclpy.spin_once(self, timeout_sec=0.1)
            if predicate():
                return True
        return False

    def publish_event(self, event):
        message = String()
        message.data = event
        self.event_pub.publish(message)

    def select_stage(self, stage):
        message = Int32()
        message.data = stage
        self.stage_pub.publish(message)


def main():
    descriptor, checkpoint = tempfile.mkstemp(prefix="mi_dog_stage_", suffix=".txt")
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
        results["initial_down_stage_1"] = probe.wait_for(
            lambda: probe.state == "DOWN_WAITING" and probe.stage == 1)
        results["stage_select_subscriber_ready"] = probe.wait_for(
            lambda: probe.stage_pub.get_subscription_count() == 1)

        probe.select_stage(6)
        results["waiting_selects_stage_6"] = probe.wait_for(lambda: probe.stage == 6)
        results["selection_does_not_run"] = probe.state == "DOWN_WAITING"

        probe.publish_event("PAUSE")
        results["pause_enters_paused"] = probe.wait_for(lambda: probe.state == "PAUSED")
        probe.select_stage(5)
        results["paused_selects_stage_5"] = probe.wait_for(lambda: probe.stage == 5)

        probe.select_stage(7)
        probe.wait_for(lambda: False, timeout=0.5)
        results["invalid_stage_rejected"] = probe.stage == 5

        probe.publish_event("STOP")
        results["stop_latches"] = probe.wait_for(lambda: probe.state == "EMERGENCY_STOP")
        probe.select_stage(4)
        probe.wait_for(lambda: False, timeout=0.5)
        results["selection_rejected_while_stopped"] = probe.stage == 5

        stop_process(process)
        process = subprocess.Popen(
            supervisor_command(checkpoint),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        probe.state = None
        probe.stage = None
        results["restart_restores_stage_but_not_running"] = probe.wait_for(
            lambda: probe.state == "DOWN_WAITING" and probe.stage == 5)

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
