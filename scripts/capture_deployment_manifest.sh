#!/usr/bin/env bash
set -euo pipefail

workspace="${MI_DOG_WORKSPACE:-/home/mi/mi_dog_ws}"
source_commit="unknown"
output=""

usage() {
  echo "Usage: $0 [--source-commit COMMIT] [--output FILE] [--workspace DIR]" >&2
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --source-commit)
      [[ $# -ge 2 ]] || { usage; exit 2; }
      source_commit="$2"
      shift 2
      ;;
    --output)
      [[ $# -ge 2 ]] || { usage; exit 2; }
      output="$2"
      shift 2
      ;;
    --workspace)
      [[ $# -ge 2 ]] || { usage; exit 2; }
      workspace="$2"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      usage
      exit 2
      ;;
  esac
done

if [[ "$source_commit" != "unknown" && ! "$source_commit" =~ ^[0-9a-fA-F]{7,40}$ ]]; then
  echo "Invalid --source-commit: expected a 7-40 character hexadecimal Git commit or unknown." >&2
  exit 2
fi

install_root="$workspace/install/mi_dog_real"
source_root="$workspace/src/mi_dog_real"
state_root="$workspace/state"
if [[ -z "$output" ]]; then
  mkdir -p "$state_root"
  output="$state_root/deployment_manifest_$(date +%Y%m%dT%H%M%S%z).txt"
else
  mkdir -p "$(dirname "$output")"
fi

files=(
  "$install_root/lib/mi_dog_real/mi_dog_real_node"
  "$install_root/lib/mi_dog_real/mi_dog_supervisor_node"
  "$install_root/lib/mi_dog_real/mi_dog_state_bridge_node"
  "$source_root/config/this_robot_sensor_only.yaml"
  "$source_root/config/supervisor.yaml"
  "$workspace/scripts/run_sensor_gate.sh"
  "$workspace/scripts/capture_deployment_manifest.sh"
  "/etc/systemd/system/mi-dog-real-sensor.service"
)

for file in "${files[@]}"; do
  if [[ ! -f "$file" ]]; then
    echo "Required deployment file is missing: $file" >&2
    exit 1
  fi
done

require_single_process() {
  local executable="$1"
  local label="$2"
  local -a pids=()
  mapfile -t pids < <(pgrep -f "^${executable}([[:space:]]|$)" || true)
  if [[ ${#pids[@]} -ne 1 ]]; then
    echo "Expected exactly one $label process, found ${#pids[@]} (${pids[*]:-none})." >&2
    echo "Remove stale isolated-test processes before capturing a deployment manifest." >&2
    exit 1
  fi
  printf '%s' "${pids[0]}"
}

real_node_pid="$(require_single_process "$install_root/lib/mi_dog_real/mi_dog_real_node" mi_dog_real_node)"
supervisor_pid="$(require_single_process "$install_root/lib/mi_dog_real/mi_dog_supervisor_node" mi_dog_supervisor_node)"
bridge_pid="$(require_single_process "$install_root/lib/mi_dog_real/mi_dog_state_bridge_node" mi_dog_state_bridge_node)"

read_param() {
  local name="$1"
  if command -v ros2 >/dev/null 2>&1; then
    timeout 5s ros2 param get /mi_dog_real "$name" 2>/dev/null |
      awk -F': ' 'NF >= 2 {print $2; exit}'
  else
    printf 'unavailable'
  fi
}

read_topic_once() {
  local topic="$1"
  local message_kind="$2"
  python3 - "$topic" "$message_kind" <<'PY'
import sys
import time

import rclpy
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy
from std_msgs.msg import Bool, String

topic, message_kind = sys.argv[1:]
message_type = {"bool": Bool, "string": String}[message_kind]
value = None
rclpy.init()
node = Node("mi_dog_deployment_manifest_probe")
qos = QoSProfile(
    depth=1,
    durability=DurabilityPolicy.TRANSIENT_LOCAL,
    reliability=ReliabilityPolicy.RELIABLE,
)

def callback(message):
    global value
    value = message.data

subscription = node.create_subscription(message_type, topic, callback, qos)
deadline = time.monotonic() + 8.0
while value is None and time.monotonic() < deadline:
    rclpy.spin_once(node, timeout_sec=0.2)
if isinstance(value, bool):
    print(str(value).lower())
elif value is not None:
    print(value)
node.destroy_subscription(subscription)
node.destroy_node()
rclpy.shutdown()
if value is None:
    raise SystemExit("Timed out waiting for " + topic)
PY
}

effective_enable_motion="$(read_param enable_motion)"
effective_require_sensor_ready="$(read_param require_sensor_ready)"
effective_require_estop_ready="$(read_param require_estop_ready)"
effective_require_supervisor_run_allowed="$(read_param require_supervisor_run_allowed)"
supervisor_state="$(read_topic_once /mi_dog_real/supervisor/state string)"
run_allowed="$(read_topic_once /mi_dog_real/supervisor/run_allowed bool)"

for value in "$effective_enable_motion" "$effective_require_sensor_ready" \
             "$effective_require_estop_ready" "$effective_require_supervisor_run_allowed" \
             "$supervisor_state" "$run_allowed"; do
  if [[ -z "$value" ]]; then
    echo "A required live deployment value was empty; manifest not written." >&2
    exit 1
  fi
done

{
  echo "manifest_schema=mi_dog_real/v1"
  echo "captured_at=$(date --iso-8601=seconds)"
  echo "hostname=$(hostname)"
  echo "kernel=$(uname -srmo)"
  echo "workspace=$workspace"
  echo "source_commit=$source_commit"
  echo "service_active=$(systemctl is-active mi-dog-real-sensor.service 2>/dev/null || true)"
  echo "mi_dog_real_node_pid=$real_node_pid"
  echo "mi_dog_supervisor_node_pid=$supervisor_pid"
  echo "mi_dog_state_bridge_node_pid=$bridge_pid"
  echo "ros_distro=${ROS_DISTRO:-unknown}"
  echo "ros_domain_id=${ROS_DOMAIN_ID:-unknown}"
  echo "rmw_implementation=${RMW_IMPLEMENTATION:-unknown}"
  echo "enable_motion=$effective_enable_motion"
  echo "require_sensor_ready=$effective_require_sensor_ready"
  echo "require_estop_ready=$effective_require_estop_ready"
  echo "require_supervisor_run_allowed=$effective_require_supervisor_run_allowed"
  echo "supervisor_state=$supervisor_state"
  echo "run_allowed=$run_allowed"
  echo "sha256_begin"
  sha256sum "${files[@]}"
  echo "sha256_end"
} > "$output"

chmod 0444 "$output"
echo "$output"
