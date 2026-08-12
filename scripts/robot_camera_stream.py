#!/usr/bin/env python3
"""Remote ROS Image to length-prefixed JPEG stream for the localhost UI."""

import argparse
import os
import struct
import sys
import time

import cv2
import numpy as np
import rclpy
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import Image


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--topic", required=True)
    parser.add_argument("--max-fps", type=float, default=10.0)
    parser.add_argument("--jpeg-quality", type=int, default=72)
    parser.add_argument("--max-width", type=int, default=640)
    args = parser.parse_args()
    if not 1.0 <= args.max_fps <= 15.0:
        parser.error("--max-fps must be in [1, 15]")
    if not 30 <= args.jpeg_quality <= 90:
        parser.error("--jpeg-quality must be in [30, 90]")
    if not 160 <= args.max_width <= 1280:
        parser.error("--max-width must be in [160, 1280]")
    return args


def image_to_bgr(message):
    encodings = {
        "bgr8": (3, None),
        "rgb8": (3, cv2.COLOR_RGB2BGR),
        "bgra8": (4, cv2.COLOR_BGRA2BGR),
        "rgba8": (4, cv2.COLOR_RGBA2BGR),
        "mono8": (1, cv2.COLOR_GRAY2BGR),
    }
    if message.encoding not in encodings or message.height < 1 or message.width < 1:
        return None
    channels, conversion = encodings[message.encoding]
    row_bytes = message.width * channels
    if message.step < row_bytes:
        return None
    data = np.frombuffer(message.data, dtype=np.uint8)
    expected = message.height * message.step
    if data.size < expected:
        return None
    rows = data[:expected].reshape(message.height, message.step)
    frame = rows[:, :row_bytes]
    if channels == 1:
        frame = frame.reshape(message.height, message.width)
    else:
        frame = frame.reshape(message.height, message.width, channels)
    if conversion is not None:
        frame = cv2.cvtColor(frame, conversion)
    return frame


def write_all(descriptor, data):
    """Write a complete framed payload even when the pipe accepts a short write."""
    view = memoryview(data)
    while view:
        written = os.write(descriptor, view)
        if written <= 0:
            raise BrokenPipeError
        view = view[written:]


def main():
    args = parse_args()
    output_fd = sys.stdout.fileno()
    minimum_interval = 1.0 / args.max_fps
    state = {"last_frame": 0.0, "running": True}
    rclpy.init()
    node = Node("mi_dog_remote_camera_stream")

    def callback(message):
        now = time.monotonic()
        if now - state["last_frame"] < minimum_interval:
            return
        frame = image_to_bgr(message)
        if frame is None:
            return
        if frame.shape[1] > args.max_width:
            scale = args.max_width / frame.shape[1]
            frame = cv2.resize(
                frame,
                (args.max_width, max(1, int(frame.shape[0] * scale))),
                interpolation=cv2.INTER_AREA,
            )
        success, encoded = cv2.imencode(
            ".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), args.jpeg_quality])
        if not success:
            return
        payload = encoded.tobytes()
        try:
            write_all(output_fd, struct.pack(">I", len(payload)))
            write_all(output_fd, payload)
        except BrokenPipeError:
            state["running"] = False
            return
        state["last_frame"] = now

    subscription = node.create_subscription(
        Image, args.topic, callback, qos_profile_sensor_data)
    try:
        while rclpy.ok() and state["running"]:
            rclpy.spin_once(node, timeout_sec=0.2)
    finally:
        node.destroy_subscription(subscription)
        node.destroy_node()
        rclpy.shutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
