#!/usr/bin/env bash
set -euo pipefail

minimum_uptime_sec="${MI_DOG_CAMERA_MIN_UPTIME_SEC:-240}"
camera_topic="${MI_DOG_CAMERA_TOPIC:-/mi_desktop_48_b0_2d_7a_fe_40/image}"
camera_service="${MI_DOG_CAMERA_SERVICE:-/mi_desktop_48_b0_2d_7a_fe_40/camera_service}"

if [[ ! "$minimum_uptime_sec" =~ ^[0-9]+$ ]] || (( minimum_uptime_sec > 900 )); then
  echo "Deferred camera start refused: invalid minimum uptime '$minimum_uptime_sec'." >&2
  exit 2
fi

# Avoid duplicate helpers if this script is invoked manually. systemd's default
# KillMode=control-group also removes the helper on a project-service restart.
exec 9>/tmp/mi_dog_camera_start.lock
if ! flock -n 9; then
  echo "Deferred camera start already has an active verifier; exiting."
  exit 0
fi

camera_frame_available() {
  local probe_seconds="$1"
  timeout "$((probe_seconds + 3))s" python3 - "$camera_topic" "$probe_seconds" <<'PY'
import sys
import time

import rclpy
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import Image

topic = sys.argv[1]
probe_seconds = float(sys.argv[2])
valid_frames = []
rclpy.init()
node = Node("mi_dog_deferred_camera_probe")
subscription = node.create_subscription(
    Image,
    topic,
    lambda message: valid_frames.append(message)
    if message.width > 0 and message.height > 0 and message.data else None,
    qos_profile_sensor_data,
)
deadline = time.monotonic() + probe_seconds
while not valid_frames and time.monotonic() < deadline:
    rclpy.spin_once(node, timeout_sec=0.2)
node.destroy_subscription(subscription)
node.destroy_node()
rclpy.shutdown()
if not valid_frames:
    raise SystemExit(1)
PY
}

uptime_whole="$(cut -d. -f1 /proc/uptime)"
if (( uptime_whole < minimum_uptime_sec )); then
  delay_sec=$((minimum_uptime_sec - uptime_whole))
  echo "Deferring head RGB start for ${delay_sec}s (minimum uptime ${minimum_uptime_sec}s)."
  sleep "$delay_sec"
fi

if camera_frame_available 6; then
  echo "Head RGB already has valid frames; preserving the existing stream."
  exit 0
fi

echo "Stock bringup is stable; requesting head RGB 640x480 at 10 fps."
camera_response="$(
  timeout 20s ros2 service call "$camera_service" protocol/srv/CameraService \
    "{command: 9, args: '', width: 640, height: 480, fps: 10}" 2>&1 || true
)"

# A result=0 response has previously been observed while no frames existed.
# Physical topic evidence, not the service response, is the acceptance gate.
if camera_frame_available 20; then
  echo "Head RGB verified by a valid image frame after deferred start."
  exit 0
fi

echo "Head RGB start failed: no valid image frame; motion remains fail-closed." >&2
echo "camera_service_response=${camera_response//$'\n'/ }" >&2
exit 1
