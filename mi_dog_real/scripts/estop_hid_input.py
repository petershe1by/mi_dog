#!/usr/bin/env python3
import errno
import fcntl
import os
import stat
import struct
import time

import rclpy
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy
from std_msgs.msg import Bool, String


EV_KEY = 0x01
INPUT_EVENT = struct.Struct("@llHHi")
KEY_BITMAP_BYTES = 96


def ioctl_request(direction, ioctl_type, number, size):
    return (direction << 30) | (size << 16) | (ioctl_type << 8) | number


EVIOCGKEY = ioctl_request(2, ord("E"), 0x18, KEY_BITMAP_BYTES)
EVIOCGRAB = ioctl_request(1, ord("E"), 0x90, struct.calcsize("i"))


class EstopHidInput(Node):
    def __init__(self):
        super().__init__("mi_dog_estop_hid_input")
        self.device_path = self.declare_parameter(
            "device_path", "/dev/input/by-id/mi-dog-estop-event-kbd"
        ).value
        self.key_code = int(self.declare_parameter("key_code", 88).value)
        self.assert_when_key_down = bool(
            self.declare_parameter("assert_when_key_down", False).value
        )
        self.grab_device = bool(self.declare_parameter("grab_device", True).value)
        self.reconnect_interval = float(
            self.declare_parameter("reconnect_interval_sec", 0.25).value
        )
        publish_rate = float(self.declare_parameter("publish_rate_hz", 50.0).value)
        self.output_topic = self.declare_parameter(
            "output_topic", "/mi_dog_real/emergency_stop_input"
        ).value
        self.status_topic = self.declare_parameter(
            "status_topic", "/mi_dog_real/emergency_stop_hid/status"
        ).value

        # This exists only so the repeatable FIFO test can exercise disconnects
        # without root/uinput. It must remain false in the deployed YAML.
        self.test_allow_non_character_device = bool(
            self.declare_parameter("test_allow_non_character_device", False).value
        )
        self.test_initial_key_down = bool(
            self.declare_parameter("test_initial_key_down", False).value
        )

        if not self.device_path or self.key_code < 0:
            raise ValueError("device_path must be set and key_code must be non-negative")
        if self.reconnect_interval <= 0.0 or publish_rate <= 0.0:
            raise ValueError("reconnect_interval_sec and publish_rate_hz must be positive")
        if self.test_allow_non_character_device:
            if not self.output_topic.startswith("/mi_dog_test/"):
                raise ValueError("test devices may publish only under /mi_dog_test/")
        elif not self.device_path.startswith("/dev/input/by-id/"):
            raise ValueError("production device_path must use stable /dev/input/by-id/")

        qos = QoSProfile(depth=10, reliability=ReliabilityPolicy.RELIABLE)
        status_qos = QoSProfile(
            depth=1,
            reliability=ReliabilityPolicy.RELIABLE,
            durability=DurabilityPolicy.TRANSIENT_LOCAL,
        )
        self.output_pub = self.create_publisher(Bool, self.output_topic, qos)
        self.status_pub = self.create_publisher(String, self.status_topic, status_qos)

        self.fd = None
        self.healthy = False
        self.key_down = False
        self.buffer = bytearray()
        self.reason = ""
        self.next_open_time = 0.0
        self.set_reason("device_missing")
        self.timer = self.create_timer(1.0 / publish_rate, self.tick)

    def set_reason(self, reason):
        if self.reason == reason:
            return
        self.reason = reason
        self.get_logger().warn(
            f"Emergency-stop HID input: {reason}; healthy={int(self.healthy)}"
        )

    def close_device(self, reason):
        if self.fd is not None:
            try:
                os.close(self.fd)
            except OSError:
                pass
        self.fd = None
        self.healthy = False
        self.buffer.clear()
        self.next_open_time = time.monotonic() + self.reconnect_interval
        self.set_reason(reason)

    def query_key_state(self, fd):
        bitmap = bytearray(KEY_BITMAP_BYTES)
        fcntl.ioctl(fd, EVIOCGKEY, bitmap, True)
        byte_index, bit_index = divmod(self.key_code, 8)
        if byte_index >= len(bitmap):
            raise ValueError("key_code exceeds supported Linux input range")
        return bool(bitmap[byte_index] & (1 << bit_index))

    def try_open(self):
        now = time.monotonic()
        if now < self.next_open_time:
            return
        self.next_open_time = now + self.reconnect_interval
        try:
            fd = os.open(
                self.device_path,
                os.O_RDONLY | os.O_NONBLOCK | getattr(os, "O_CLOEXEC", 0),
            )
            mode = os.fstat(fd).st_mode
            if not stat.S_ISCHR(mode) and not self.test_allow_non_character_device:
                raise OSError(errno.ENODEV, "configured path is not a character device")
            if self.test_allow_non_character_device:
                key_down = self.test_initial_key_down
            else:
                key_down = self.query_key_state(fd)
                if self.grab_device:
                    fcntl.ioctl(fd, EVIOCGRAB, 1)
        except (OSError, ValueError) as exc:
            if "fd" in locals():
                os.close(fd)
            self.healthy = False
            self.set_reason(f"open_failed:{getattr(exc, 'errno', 'invalid')}")
            return

        self.fd = fd
        self.key_down = key_down
        self.healthy = True
        self.buffer.clear()
        self.set_reason("healthy_key_down" if key_down else "healthy_key_up")

    def read_events(self):
        while self.fd is not None:
            try:
                chunk = os.read(self.fd, 4096)
            except BlockingIOError:
                break
            except OSError as exc:
                self.close_device(f"device_read_error:{exc.errno}")
                return
            if not chunk:
                self.close_device("device_disconnected")
                return
            self.buffer.extend(chunk)

        while len(self.buffer) >= INPUT_EVENT.size:
            _, _, event_type, code, value = INPUT_EVENT.unpack_from(self.buffer)
            del self.buffer[:INPUT_EVENT.size]
            if event_type == EV_KEY and code == self.key_code:
                self.key_down = value != 0
                self.set_reason(
                    "healthy_key_down" if self.key_down else "healthy_key_up"
                )

    def tick(self):
        if self.fd is None:
            self.try_open()
        if self.fd is not None:
            self.read_events()

        asserted = True
        if self.healthy:
            asserted = (
                self.key_down
                if self.assert_when_key_down
                else not self.key_down
            )
        output = Bool()
        output.data = asserted
        self.output_pub.publish(output)
        status = String()
        status.data = self.reason
        self.status_pub.publish(status)

    def destroy_node(self):
        self.close_device("shutdown")
        super().destroy_node()


def main():
    rclpy.init()
    node = EstopHidInput()
    try:
        rclpy.spin(node)
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
