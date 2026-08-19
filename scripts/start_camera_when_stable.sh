#!/usr/bin/env bash
set -euo pipefail

minimum_uptime_sec="${MI_DOG_CAMERA_MIN_UPTIME_SEC:-240}"
active_window_sec="${MI_DOG_CAMERA_ACTIVE_WINDOW_SEC:-45}"
rest_window_sec="${MI_DOG_CAMERA_REST_WINDOW_SEC:-5}"
probe_interval_sec="${MI_DOG_CAMERA_PROBE_INTERVAL_SEC:-5}"
max_cycles="${MI_DOG_CAMERA_MAX_CYCLES:-0}"
camera_topic="${MI_DOG_CAMERA_TOPIC:-/mi_desktop_48_b0_2d_7a_fe_40/image}"
camera_service="${MI_DOG_CAMERA_SERVICE:-/mi_desktop_48_b0_2d_7a_fe_40/camera_service}"
probe_command="${MI_DOG_CAMERA_PROBE_COMMAND:-}"
call_command="${MI_DOG_CAMERA_CALL_COMMAND:-}"

require_uint() {
  local name="$1" value="$2" maximum="$3"
  if [[ ! "$value" =~ ^[0-9]+$ ]] || (( value > maximum )); then
    echo "Camera stream guard refused: invalid $name '$value'." >&2
    exit 2
  fi
}

require_uint minimum_uptime_sec "$minimum_uptime_sec" 900
require_uint active_window_sec "$active_window_sec" 300
require_uint rest_window_sec "$rest_window_sec" 60
require_uint probe_interval_sec "$probe_interval_sec" 60
require_uint max_cycles "$max_cycles" 1000
(( active_window_sec >= 1 && probe_interval_sec >= 1 )) || {
  echo "Camera stream guard refused: active and probe intervals must be positive." >&2
  exit 2
}
[[ -z "$probe_command" || -x "$probe_command" ]] || {
  echo "Camera stream guard refused: probe command is not executable." >&2; exit 2; }
[[ -z "$call_command" || -x "$call_command" ]] || {
  echo "Camera stream guard refused: call command is not executable." >&2; exit 2; }

# Keep one owner for the stock START/STOP service. systemd removes this process
# with the rest of the project service cgroup on a service restart.
exec 9>/tmp/mi_dog_camera_start.lock
if ! flock -n 9; then
  echo "Camera stream guard already has an active owner; exiting."
  exit 0
fi

camera_frame_available() {
  local probe_seconds="$1"
  if [[ -n "$probe_command" ]]; then
    "$probe_command" "$probe_seconds"
    return
  fi
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
node = Node("mi_dog_camera_stream_guard_probe")
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

call_camera() {
  local command="$1" response
  if [[ -n "$call_command" ]]; then
    "$call_command" "$command"
    return
  fi
  response="$(
    timeout 20s ros2 service call "$camera_service" protocol/srv/CameraService \
      "{command: $command, args: '', width: 640, height: 480, fps: 10}" 2>&1
  )" || {
    echo "Camera command $command failed: ${response//$'\n'/ }" >&2
    return 1
  }
  if [[ "$response" != *"result=0"* ]]; then
    echo "Camera command $command was refused: ${response//$'\n'/ }" >&2
    return 1
  fi
}

camera_active=0
stop_camera() {
  if (( camera_active )); then
    call_camera 10 || true
    camera_active=0
  fi
}
trap stop_camera EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

uptime_whole="$(cut -d. -f1 /proc/uptime)"
if (( uptime_whole < minimum_uptime_sec )); then
  delay_sec=$((minimum_uptime_sec - uptime_whole))
  echo "Deferring head RGB guard for ${delay_sec}s (minimum uptime ${minimum_uptime_sec}s)."
  sleep "$delay_sec"
fi

# An inherited stream has unknown age. Stop it once so every accepted window
# begins with a fresh, owned capture session.
if camera_frame_available 2; then
  camera_active=1
  echo "Stopping inherited head RGB stream before guarded cycles."
  stop_camera
  sleep "$rest_window_sec"
fi

cycle=0
while (( max_cycles == 0 || cycle < max_cycles )); do
  cycle=$((cycle + 1))
  echo "Head RGB guarded cycle $cycle: START_IMAGE_PUBLISH."
  cycle_started=$SECONDS
  call_camera 9
  camera_active=1
  if ! camera_frame_available 10; then
    echo "Head RGB guarded cycle $cycle failed: no valid image frame." >&2
    exit 1
  fi

  # Bound wall-clock capture lifetime from before the START call. Service
  # latency and initial frame verification count against the active window.
  deadline=$((cycle_started + active_window_sec))
  while (( SECONDS < deadline )); do
    remaining=$((deadline - SECONDS))
    sleep_for="$probe_interval_sec"
    (( sleep_for <= remaining )) || sleep_for="$remaining"
    sleep "$sleep_for"
    (( SECONDS >= deadline )) && break
    if ! camera_frame_available 2; then
      echo "Head RGB guarded cycle $cycle failed: image stream became stale." >&2
      exit 1
    fi
  done

  echo "Head RGB guarded cycle $cycle: STOP_IMAGE_PUBLISH."
  stop_camera
  (( max_cycles != 0 && cycle >= max_cycles )) && break
  sleep "$rest_window_sec"
done

echo "Head RGB guarded cycles completed cleanly."
