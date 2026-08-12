#!/usr/bin/env bash
set -euo pipefail

set +u
source /opt/ros2/galactic/setup.bash
source /opt/ros2/cyberdog/setup.bash
source /home/mi/mi_dog_ws/install/setup.bash
set -u

export ROS_DOMAIN_ID=42
export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp
export CYCLONEDDS_URI=file:///etc/mi/cyclonedds.xml

mkdir -p /home/mi/mi_dog_ws/state

camera_service=/mi_desktop_48_b0_2d_7a_fe_40/camera_service
camera_topic=/mi_desktop_48_b0_2d_7a_fe_40/image

camera_frame_available() {
  timeout 12s python3 - "$camera_topic" <<'PY'
import sys
import time

import rclpy
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import Image

topic = sys.argv[1]
frames = []
rclpy.init()
node = Node("mi_dog_camera_startup_probe")
subscription = node.create_subscription(
    Image, topic, lambda message: frames.append(message), qos_profile_sensor_data)
deadline = time.monotonic() + 10.0
while not frames and time.monotonic() < deadline:
    rclpy.spin_once(node, timeout_sec=0.2)
node.destroy_subscription(subscription)
node.destroy_node()
rclpy.shutdown()
if not frames:
    raise SystemExit(1)
PY
}

camera_active=false
if camera_frame_available; then
  camera_active=true
  echo "Camera stream was already active; preserving it across service restart."
else
  camera_response="$(
    timeout 20s ros2 service call "$camera_service" protocol/srv/CameraService \
      "{command: 9, args: '', width: 640, height: 480, fps: 10}" 2>&1 || true
  )"
  if grep -q 'result=0' <<< "$camera_response"; then
    camera_active=true
    echo "Camera stream enabled at 640x480, 10 fps."
  elif camera_frame_available; then
    camera_active=true
    echo "Camera stream became active even though the service response timed out."
  fi
fi

if [[ "$camera_active" != true ]]; then
  echo "Camera stream was not enabled; sensor-only service continues fail-closed." >&2
  echo "${camera_response:-camera topic inactive}" >&2
fi

ros2 launch mi_dog_real sensor_only.launch.py
