#!/usr/bin/env python3
import os
import signal
import struct
import subprocess
import tempfile
import time

import rclpy
from rclpy.node import Node
from std_msgs.msg import Bool


INPUT_EVENT = struct.Struct("@llHHi")
EV_KEY = 0x01
KEY_F12 = 88


class Probe(Node):
    def __init__(self):
        super().__init__("mi_dog_estop_hid_isolated_probe")
        self.samples = []
        self.create_subscription(
            Bool,
            "/mi_dog_test/hid/output",
            lambda message: self.samples.append((time.monotonic(), message.data)),
            10,
        )

    def sample(self, seconds):
        start = time.monotonic()
        while time.monotonic() - start < seconds:
            rclpy.spin_once(self, timeout_sec=0.03)
        return start, time.monotonic()

    def wait_for_publisher(self, timeout=4.0):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            rclpy.spin_once(self, timeout_sec=0.05)
            if self.count_publishers("/mi_dog_test/hid/output") > 0:
                return
        raise RuntimeError("Timed out waiting for isolated HID publisher discovery")

    def values(self, interval, settle=0.25):
        start, end = interval
        return [value for stamp, value in self.samples if start + settle <= stamp < end]


def write_key(fd, down):
    os.write(fd, INPUT_EVENT.pack(0, 0, EV_KEY, KEY_F12, 1 if down else 0))


def main():
    with tempfile.TemporaryDirectory(prefix="mi_dog_estop_hid_") as tempdir:
        device_path = os.path.join(tempdir, "estop-event")
        os.mkfifo(device_path)
        writer = os.open(device_path, os.O_RDWR | os.O_NONBLOCK)
        process = subprocess.Popen(
            [
                "ros2", "run", "mi_dog_real", "estop_hid_input.py", "--ros-args",
                "-r", "__node:=mi_dog_estop_hid_isolated",
                "-p", f"device_path:={device_path}",
                "-p", "key_code:=88",
                "-p", "assert_when_key_down:=false",
                "-p", "grab_device:=false",
                "-p", "reconnect_interval_sec:=0.1",
                "-p", "publish_rate_hz:=50.0",
                "-p", "output_topic:=/mi_dog_test/hid/output",
                "-p", "status_topic:=/mi_dog_test/hid/status",
                "-p", "test_allow_non_character_device:=true",
                "-p", "test_initial_key_down:=false",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        rclpy.init()
        probe = Probe()
        try:
            probe.wait_for_publisher()
            opened_asserted = probe.sample(0.8)
            write_key(writer, True)
            normal_closed = probe.sample(0.7)
            write_key(writer, False)
            button_pressed = probe.sample(0.7)
            write_key(writer, True)
            button_released = probe.sample(0.7)

            os.close(writer)
            writer = None
            os.unlink(device_path)
            disconnected = probe.sample(0.8)

            os.mkfifo(device_path)
            writer = os.open(device_path, os.O_RDWR | os.O_NONBLOCK)
            reconnected_open = probe.sample(0.7)
            write_key(writer, True)
            reconnected_normal = probe.sample(0.7)

            phases = {
                "opened_key_up": probe.values(opened_asserted, 0.25),
                "normal_nc_closed": probe.values(normal_closed),
                "button_pressed_open": probe.values(button_pressed),
                "button_released_closed": probe.values(button_released),
                "usb_disconnected": probe.values(disconnected, 0.4),
                "reconnected_key_up": probe.values(reconnected_open, 0.35),
                "reconnected_normal": probe.values(reconnected_normal),
            }
            results = {
                "startup_open_asserts": all(phases["opened_key_up"]) and bool(phases["opened_key_up"]),
                "normal_nc_closed_clears": not any(phases["normal_nc_closed"]) and bool(phases["normal_nc_closed"]),
                "button_pressed_asserts": all(phases["button_pressed_open"]) and bool(phases["button_pressed_open"]),
                "button_released_clears": not any(phases["button_released_closed"]) and bool(phases["button_released_closed"]),
                "disconnect_asserts": all(phases["usb_disconnected"]) and bool(phases["usb_disconnected"]),
                "reconnect_open_asserts": all(phases["reconnected_key_up"]) and bool(phases["reconnected_key_up"]),
                "reconnect_normal_clears": not any(phases["reconnected_normal"]) and bool(phases["reconnected_normal"]),
            }
            for name, values in phases.items():
                print(f"phase={name} samples={len(values)} true={sum(values)} false={len(values)-sum(values)}")
            for name, passed in results.items():
                print(f"{name}={passed}")
            if not all(results.values()):
                raise SystemExit(1)
        finally:
            if writer is not None:
                os.close(writer)
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
