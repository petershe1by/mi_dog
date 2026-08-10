#!/usr/bin/env python3
import argparse
import math
import sys
import time

import rclpy
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from std_msgs.msg import Float32MultiArray


FIELD_NAMES = (
    "left_p25_m",
    "left_median_m",
    "right_p25_m",
    "right_median_m",
    "left_valid_fraction",
    "right_valid_fraction",
)


class GroundTofCapture(Node):
    def __init__(self, topic):
        super().__init__("ground_tof_capture")
        self.samples = []
        self.invalid_messages = 0
        self.create_subscription(
            Float32MultiArray, topic, self._receive, qos_profile_sensor_data)

    def _receive(self, message):
        if len(message.data) < len(FIELD_NAMES):
            self.invalid_messages += 1
            return
        values = tuple(float(value) for value in message.data[:len(FIELD_NAMES)])
        if not all(math.isfinite(value) for value in values):
            self.invalid_messages += 1
            return
        self.samples.append(values)


def parse_args():
    parser = argparse.ArgumentParser(
        description="Read-only statistics for the CyberDog head ground-ToF ROI topic.")
    parser.add_argument(
        "--topic", default="/mi_dog_real/head_ground_roi_summary")
    parser.add_argument("--samples", type=int, default=20)
    parser.add_argument("--timeout", type=float, default=15.0)
    args = parser.parse_args()
    if args.samples <= 0:
        parser.error("--samples must be positive")
    if args.timeout <= 0.0:
        parser.error("--timeout must be positive")
    return args


def main():
    args = parse_args()
    rclpy.init()
    node = GroundTofCapture(args.topic)
    deadline = time.monotonic() + args.timeout
    try:
        while len(node.samples) < args.samples and time.monotonic() < deadline:
            rclpy.spin_once(node, timeout_sec=0.1)
    finally:
        samples = node.samples[:args.samples]
        invalid_messages = node.invalid_messages
        node.destroy_node()
        rclpy.shutdown()

    print("samples={} invalid_messages={}".format(len(samples), invalid_messages))
    if not samples:
        print("no valid six-field ground-ToF samples received", file=sys.stderr)
        return 2
    for index, name in enumerate(FIELD_NAMES):
        values = [sample[index] for sample in samples]
        print(
            "{} mean={:.6f} min={:.6f} max={:.6f}".format(
                name, sum(values) / len(values), min(values), max(values)))
    if len(samples) != args.samples:
        print(
            "timed out before requested sample count", file=sys.stderr)
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
