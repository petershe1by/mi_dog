#!/usr/bin/env bash
set -euo pipefail

target="${MI_DOG_TARGET:-mi@192.168.44.1}"
identity="${MI_DOG_SSH_IDENTITY:-${HOME}/.ssh/mi_dog_competition_ed25519}"
distance="${1:-2.0}"
speed="${2:-0.40}"

python3 - "$distance" "$speed" <<'PY'
import sys
d, v = map(float, sys.argv[1:])
if not (0.05 <= d <= 2.0 and 0.05 <= v <= 0.40):
    raise SystemExit("distance must be 0.05..2.0 m and speed 0.05..0.40 m/s")
PY

ssh_options=(-o StrictHostKeyChecking=accept-new -o ConnectTimeout=5)
if [[ -f "$identity" ]]; then
  ssh_options+=(-o IdentitiesOnly=yes -i "$identity")
fi

ssh "${ssh_options[@]}" "$target" bash -s -- "$distance" "$speed" <<'REMOTE'
set -eo pipefail
source /home/mi/mi_dog_ws/scripts/load_live_ros_env.sh
source /home/mi/mi_dog_ws/install/setup.bash

python3 - "$1" "$2" <<'PY'
import math
import sys
import time

import rclpy
from geometry_msgs.msg import Twist
from nav_msgs.msg import Odometry
from protocol.msg import MotionServoCmd
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy, qos_profile_sensor_data
from std_msgs.msg import Bool, Int32, String

distance, speed = map(float, sys.argv[1:])
rclpy.init()
node = Node("mi_dog_bounded_distance_test")
latched = QoSProfile(depth=1, durability=DurabilityPolicy.TRANSIENT_LOCAL,
                     reliability=ReliabilityPolicy.RELIABLE)
state = {"allowed": None, "stage": None, "supervisor": None, "odom": None,
         "odom_time": 0.0, "odom_seq": 0,
         "max_servo_vx": 0.0, "max_servo_wz": 0.0,
         "max_step_height": 0.0}

def odom_cb(message):
    q = message.pose.pose.orientation
    yaw = math.atan2(2.0 * (q.w*q.z + q.x*q.y),
                     1.0 - 2.0 * (q.y*q.y + q.z*q.z))
    state["odom"] = (message.pose.pose.position.x, message.pose.pose.position.y, yaw)
    state["odom_time"] = time.monotonic()
    state["odom_seq"] += 1

def servo_cb(message):
    if message.cmd_type == MotionServoCmd.SERVO_DATA:
        if len(message.vel_des) == 3:
            state["max_servo_vx"] = max(state["max_servo_vx"], abs(message.vel_des[0]))
            state["max_servo_wz"] = max(state["max_servo_wz"], abs(message.vel_des[2]))
        if len(message.step_height) == 2:
            state["max_step_height"] = max(
                state["max_step_height"], *(abs(v) for v in message.step_height))

node.create_subscription(Bool, "/mi_dog_real/supervisor/run_allowed",
                         lambda m: state.update(allowed=m.data), latched)
node.create_subscription(Int32, "/mi_dog_real/supervisor/current_stage",
                         lambda m: state.update(stage=m.data), latched)
node.create_subscription(String, "/mi_dog_real/supervisor/state",
                         lambda m: state.update(supervisor=m.data), latched)
node.create_subscription(Odometry, "/mi_desktop_48_b0_2d_7a_fe_40/odom_out",
                         odom_cb, qos_profile_sensor_data)
node.create_subscription(MotionServoCmd,
                         "/mi_desktop_48_b0_2d_7a_fe_40/motion_servo_cmd",
                         servo_cb, qos_profile_sensor_data)
publisher = node.create_publisher(Twist, "/mi_dog_real/safe_cmd_vel", 10)

def stop():
    zero = Twist()
    for _ in range(5):
        publisher.publish(zero)
        rclpy.spin_once(node, timeout_sec=0.03)

try:
    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline:
        rclpy.spin_once(node, timeout_sec=0.05)
        if (state["allowed"] is True and state["stage"] == 1 and
                state["supervisor"] == "RUNNING" and state["odom"] is not None and
                time.monotonic() - state["odom_time"] <= 0.20 and
                publisher.get_subscription_count() == 1):
            break
    else:
        raise RuntimeError("preconditions_not_ready:" + repr(state))

    # START/CONTINUE can briefly interrupt odom delivery. Do not use a frame
    # cached before the transition: require three new, fresh frames while the
    # permission remains continuously asserted, then take the last one as the
    # distance/heading baseline.
    ready_seq = state["odom_seq"]
    fresh_deadline = time.monotonic() + 2.0
    while time.monotonic() < fresh_deadline:
        rclpy.spin_once(node, timeout_sec=0.05)
        if state["allowed"] is not True or state["supervisor"] != "RUNNING":
            raise RuntimeError("run_permission_revoked_during_odom_sync")
        if (state["odom_seq"] >= ready_seq + 3 and
                time.monotonic() - state["odom_time"] <= 0.20):
            break
    else:
        raise RuntimeError("post_start_odometry_not_fresh")

    x0, y0, yaw0 = state["odom"]
    command = Twist()
    command.linear.x = speed
    started = time.monotonic()
    # Stage-1 slabs and the downstream clearance limiter can make average
    # progress much lower than the requested peak speed. Keep all deviation
    # and freshness guards unchanged while allowing a bounded 60 s run.
    deadline = started + 60.0
    forward = lateral = heading_error = 0.0
    while time.monotonic() < deadline:
        now = time.monotonic()
        if state["allowed"] is not True or state["supervisor"] != "RUNNING":
            raise RuntimeError("run_permission_revoked")
        if now - state["odom_time"] > 0.35:
            raise RuntimeError("odometry_stale")
        x, y, yaw = state["odom"]
        dx, dy = x - x0, y - y0
        forward = math.cos(yaw0)*dx + math.sin(yaw0)*dy
        lateral = -math.sin(yaw0)*dx + math.cos(yaw0)*dy
        heading_error = math.atan2(math.sin(yaw-yaw0), math.cos(yaw-yaw0))
        if forward >= distance:
            break
        if abs(lateral) > 0.25 or abs(heading_error) > 0.50:
            raise RuntimeError("straightness_guard_triggered")
        # Odom/IMU-derived yaw holds the initial heading, while cross-track
        # feedback gently returns the body to the original straight line.
        command.angular.z = max(
            -0.25, min(0.25, -1.2 * heading_error - 1.5 * lateral))
        publisher.publish(command)
        rclpy.spin_once(node, timeout_sec=0.04)
        time.sleep(0.01)
    else:
        raise RuntimeError("distance_timeout")
    stop()
    outcome = "PASS"
except Exception as error:
    outcome = "FAIL"
    print(f"failure_reason={error}")
    raise
finally:
    stop()
    if "started" in locals():
        print(f"DISTANCE_TEST={outcome}")
        print(f"forward_m={forward:.4f}")
        print(f"lateral_m={lateral:.4f}")
        print(f"heading_error_rad={heading_error:.4f}")
        print(f"elapsed_sec={time.monotonic()-started:.3f}")
        print(f"max_servo_vx_mps={state['max_servo_vx']:.4f}")
        print(f"max_servo_wz_rps={state['max_servo_wz']:.4f}")
        print(f"max_step_height_m={state['max_step_height']:.4f}")
    node.destroy_node()
    rclpy.shutdown()
PY
REMOTE
