#!/usr/bin/env python3
import os
import signal
import subprocess
import time

import rclpy
from rclpy.node import Node
from std_msgs.msg import Bool, String


class EstopProbe(Node):
    def __init__(self):
        super().__init__("mi_dog_estop_guard_isolated_probe")
        self.output_samples = []
        self.status = ""
        self.input_pub = self.create_publisher(Bool, "/mi_dog_test/estop/input", 10)
        self.create_subscription(
            Bool,
            "/mi_dog_test/estop/output",
            lambda message: self.output_samples.append((time.monotonic(), message.data)),
            10,
        )
        self.create_subscription(
            String,
            "/mi_dog_test/estop/status",
            lambda message: setattr(self, "status", message.data),
            10,
        )

    def sample(self, seconds, input_value=None):
        start = time.monotonic()
        while time.monotonic() - start < seconds:
            if input_value is not None:
                message = Bool()
                message.data = input_value
                self.input_pub.publish(message)
            rclpy.spin_once(self, timeout_sec=0.02)
            time.sleep(0.02)
        return start, time.monotonic()

    def values(self, interval, settle=0.15):
        start, end = interval
        return [value for stamp, value in self.output_samples if start + settle <= stamp < end]


def main():
    process = subprocess.Popen(
        [
            "ros2", "run", "mi_dog_real", "mi_dog_estop_guard_node", "--ros-args",
            "-r", "__node:=mi_dog_estop_guard_isolated",
            "-p", "input_topic:=/mi_dog_test/estop/input",
            "-p", "output_topic:=/mi_dog_test/estop/output",
            "-p", "status_topic:=/mi_dog_test/estop/status",
            "-p", "input_timeout_sec:=0.25",
            "-p", "publish_rate_hz:=50.0",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    rclpy.init()
    probe = EstopProbe()
    try:
        missing = probe.sample(1.2)
        false_without_cycle = probe.sample(0.8, False)
        pressed = probe.sample(0.5, True)
        released = probe.sample(0.8, False)
        stale = probe.sample(0.9)
        reconnect_false = probe.sample(0.8, False)
        rearm_pressed = probe.sample(0.5, True)
        rearm_released = probe.sample(0.8, False)

        phases = {
            "missing": probe.values(missing, settle=0.5),
            "false_without_cycle": probe.values(false_without_cycle, settle=0.3),
            "pressed": probe.values(pressed, settle=0.2),
            "released": probe.values(released, settle=0.3),
            "stale": probe.values(stale, settle=0.55),
            "reconnect_false": probe.values(reconnect_false, settle=0.3),
            "rearm_pressed": probe.values(rearm_pressed, settle=0.2),
            "rearm_released": probe.values(rearm_released, settle=0.3),
        }

        results = {
            "startup_missing_asserted": all(phases["missing"]) and bool(phases["missing"]),
            "false_without_cycle_stays_asserted": (
                all(phases["false_without_cycle"]) and bool(phases["false_without_cycle"])
            ),
            "pressed_asserts": all(phases["pressed"]) and bool(phases["pressed"]),
            "release_after_cycle_clears": (
                not any(phases["released"]) and bool(phases["released"])
            ),
            "stale_reasserts": all(phases["stale"]) and bool(phases["stale"]),
            "reconnect_false_stays_asserted": (
                all(phases["reconnect_false"]) and bool(phases["reconnect_false"])
            ),
            "second_press_asserts": (
                all(phases["rearm_pressed"]) and bool(phases["rearm_pressed"])
            ),
            "second_release_clears": (
                not any(phases["rearm_released"]) and bool(phases["rearm_released"])
            ),
        }
        for name, values in phases.items():
            print(f"phase={name} samples={len(values)} true={sum(values)} false={len(values)-sum(values)}")
        for name, passed in results.items():
            print(f"{name}={passed}")
        if not all(results.values()):
            raise SystemExit(1)
    finally:
        probe.destroy_node()
        rclpy.shutdown()
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait(timeout=3)


if __name__ == "__main__":
    main()
