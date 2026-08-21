#!/usr/bin/env python3
"""Read-only multi-sample course-origin calculation from CyberDog odometry."""

import argparse
import json
import math
import time


def wrap(angle):
    return math.atan2(math.sin(angle), math.cos(angle))


def summarize(samples, course_x, course_y, max_position_jitter, max_yaw_jitter):
    if len(samples) < 3:
        raise ValueError("too few odometry samples")
    mean_x = sum(sample[0] for sample in samples) / len(samples)
    mean_y = sum(sample[1] for sample in samples) / len(samples)
    mean_yaw = math.atan2(
        sum(math.sin(sample[2]) for sample in samples) / len(samples),
        sum(math.cos(sample[2]) for sample in samples) / len(samples),
    )
    position_jitter = max(
        math.hypot(sample[0] - mean_x, sample[1] - mean_y) for sample in samples)
    yaw_jitter = max(abs(wrap(sample[2] - mean_yaw)) for sample in samples)
    if position_jitter > max_position_jitter:
        raise ValueError("robot moved during capture: %.4f m" % position_jitter)
    if yaw_jitter > max_yaw_jitter:
        raise ValueError("robot rotated during capture: %.4f rad" % yaw_jitter)
    c, s = math.cos(mean_yaw), math.sin(mean_yaw)
    origin_x = mean_x - (c * course_x - s * course_y)
    origin_y = mean_y - (s * course_x + c * course_y)
    return {
        "sample_count": len(samples),
        "assumed_course_pose": [course_x, course_y, 0.0],
        "mean_odom_pose": [mean_x, mean_y, mean_yaw],
        "position_jitter_m": position_jitter,
        "yaw_jitter_rad": yaw_jitter,
        "site_origin_x_m": origin_x,
        "site_origin_y_m": origin_y,
        "site_origin_yaw_rad": mean_yaw,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--topic", default="/mi_desktop_48_b0_2d_7a_fe_40/odom_out")
    parser.add_argument("--course-x", type=float, default=0.50)
    parser.add_argument("--course-y", type=float, default=0.50)
    parser.add_argument("--samples", type=int, default=30)
    parser.add_argument("--timeout", type=float, default=8.0)
    parser.add_argument("--max-position-jitter", type=float, default=0.015)
    parser.add_argument("--max-yaw-jitter", type=float, default=0.026)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        result = summarize([(1.0, 2.0, 0.0)] * 5, 0.5, 0.5, 0.015, 0.026)
        assert result["site_origin_x_m"] == 0.5
        assert result["site_origin_y_m"] == 1.5
        print("capture_course_origin_self_test=PASS")
        return
    if args.samples < 3 or args.timeout <= 0.0:
        raise SystemExit("invalid capture parameters")

    import rclpy
    from nav_msgs.msg import Odometry
    from rclpy.node import Node
    from rclpy.qos import qos_profile_sensor_data

    samples = []
    rclpy.init()
    node = Node("mi_dog_course_origin_capture")

    def receive(message):
        q = message.pose.pose.orientation
        norm = math.sqrt(q.x*q.x + q.y*q.y + q.z*q.z + q.w*q.w)
        if norm < 1e-9:
            return
        yaw = math.atan2(
            2.0 * (q.w*q.z + q.x*q.y) / (norm*norm),
            1.0 - 2.0 * (q.y*q.y + q.z*q.z) / (norm*norm),
        )
        p = message.pose.pose.position
        if all(math.isfinite(value) for value in (p.x, p.y, yaw)):
            samples.append((float(p.x), float(p.y), yaw))

    subscription = node.create_subscription(
        Odometry, args.topic, receive, qos_profile_sensor_data)
    deadline = time.monotonic() + args.timeout
    while len(samples) < args.samples and time.monotonic() < deadline:
        rclpy.spin_once(node, timeout_sec=0.1)
    node.destroy_subscription(subscription)
    node.destroy_node()
    rclpy.shutdown()
    if len(samples) < args.samples:
        raise SystemExit("CALIBRATION_CAPTURE=FAIL odom_samples=%d/%d" %
                         (len(samples), args.samples))
    try:
        result = summarize(samples, args.course_x, args.course_y,
                           args.max_position_jitter, args.max_yaw_jitter)
    except ValueError as error:
        raise SystemExit("CALIBRATION_CAPTURE=FAIL " + str(error))
    print("CALIBRATION_CAPTURE=PASS")
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))


if __name__ == "__main__":
    main()
