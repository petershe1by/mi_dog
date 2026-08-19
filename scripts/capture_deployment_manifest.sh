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
output_tmp="${output}.tmp.$$"
trap 'rm -f "$output_tmp"' EXIT

files=(
  "$install_root/lib/mi_dog_real/mi_dog_real_node"
  "$install_root/lib/mi_dog_real/mi_dog_supervisor_node"
  "$install_root/lib/mi_dog_real/mi_dog_state_bridge_node"
  "$install_root/lib/mi_dog_real/mi_dog_estop_guard_node"
  "$install_root/lib/mi_dog_real/estop_hid_input.py"
  "$source_root/config/this_robot_sensor_only.yaml"
  "$source_root/config/supervisor.yaml"
  "$source_root/config/estop_guard.yaml"
  "$source_root/config/estop_hid.yaml"
  "$source_root/config/this_robot_competition.yaml"
  "$source_root/config/race_controller.yaml"
  "$source_root/launch/maintenance.launch.py"
  "$source_root/launch/competition.launch.py"
  "$install_root/lib/mi_dog_real/race_controller.py"
  "$install_root/lib/mi_dog_real/race_mission.py"
  "$install_root/lib/mi_dog_real/race_replay.py"
  "$install_root/lib/mi_dog_real/course_perception.py"
  "$source_root/config/course_perception.yaml"
  "$workspace/scripts/run_sensor_gate.sh"
  "$workspace/scripts/start_camera_when_stable.sh"
  "$workspace/scripts/load_live_ros_env.sh"
  "$workspace/scripts/competition_preflight.sh"
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
service_exec_start="$(systemctl show mi-dog-real-sensor.service -p ExecStart --value --no-pager)"
case "$service_exec_start" in
  *"run_sensor_gate.sh maintenance"*) launch_mode="maintenance" ;;
  *"run_sensor_gate.sh competition"*) launch_mode="competition" ;;
  *"run_sensor_gate.sh sensor-only"*|*"run_sensor_gate.sh"*) launch_mode="sensor-only" ;;
  *)
    echo "Cannot determine launch mode from ExecStart: $service_exec_start" >&2
    exit 1
    ;;
esac

estop_guard_pid="not_running"
if [[ "$launch_mode" == "sensor-only" ]]; then
  estop_guard_pid="$(require_single_process "$install_root/lib/mi_dog_real/mi_dog_estop_guard_node" mi_dog_estop_guard_node)"
elif pgrep -f "^$install_root/lib/mi_dog_real/mi_dog_estop_guard_node([[:space:]]|$)" >/dev/null; then
  echo "E-stop guard must not run in $launch_mode mode without a physical input." >&2
  exit 1
fi

race_controller_pid="not_running"
if [[ "$launch_mode" == "competition" ]]; then
  race_controller_pid="$(require_single_process "/usr/bin/python3 $install_root/lib/mi_dog_real/race_controller.py" mi_dog_race_controller)"
elif pgrep -f "$install_root/lib/mi_dog_real/race_controller.py" >/dev/null; then
  echo "Race controller must not run in $launch_mode mode." >&2
  exit 1
fi

read_param() {
  local node="$1"
  local name="$2"
  if command -v ros2 >/dev/null 2>&1; then
    timeout 5s ros2 param get "$node" "$name" 2>/dev/null |
      awk -F': ' 'NF >= 2 {print $2; exit}'
  else
    printf 'unavailable'
  fi
}

read_topic_once() {
  local topic="$1"
  local message_kind="$2"
  local durability="${3:-transient_local}"
  python3 - "$topic" "$message_kind" "$durability" <<'PY'
import sys
import time

import rclpy
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy
from std_msgs.msg import Bool, String

topic, message_kind, durability = sys.argv[1:]
message_type = {"bool": Bool, "string": String}[message_kind]
value = None
rclpy.init()
node = Node("mi_dog_deployment_manifest_probe")
qos = QoSProfile(
    depth=1,
    durability=(
        DurabilityPolicy.TRANSIENT_LOCAL
        if durability == "transient_local"
        else DurabilityPolicy.VOLATILE
    ),
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

effective_enable_motion="$(read_param /mi_dog_real enable_motion)"
effective_require_sensor_ready="$(read_param /mi_dog_real require_sensor_ready)"
effective_require_estop_ready="$(read_param /mi_dog_real require_estop_ready)"
effective_require_supervisor_run_allowed="$(read_param /mi_dog_real require_supervisor_run_allowed)"
effective_manage_dialogue="$(read_param /mi_dog_real manage_dialogue)"
effective_min_battery_soc="$(read_param /mi_dog_supervisor min_battery_soc)"
supervisor_state="$(read_topic_once /mi_dog_real/supervisor/state string)"
run_allowed="$(read_topic_once /mi_dog_real/supervisor/run_allowed bool)"
emergency_stop="not_applicable"
estop_guard_status="not_applicable"
if [[ "$launch_mode" == "sensor-only" ]]; then
  emergency_stop="$(read_topic_once /mi_dog_real/emergency_stop bool volatile)"
  estop_guard_status="$(read_topic_once /mi_dog_real/emergency_stop_guard/status string)"
fi
competition_ui_restart_sudo="unavailable"
if sudo -n -l /bin/systemctl restart mi-dog-real-sensor.service >/dev/null 2>&1; then
  competition_ui_restart_sudo="allowed_exact_unit_restart"
fi

for value in "$effective_enable_motion" "$effective_require_sensor_ready" \
             "$effective_require_estop_ready" "$effective_require_supervisor_run_allowed" \
             "$effective_manage_dialogue" \
             "$effective_min_battery_soc" \
             "$supervisor_state" "$run_allowed" "$emergency_stop" "$estop_guard_status"; do
  if [[ -z "$value" ]]; then
    echo "A required live deployment value was empty; manifest not written." >&2
    exit 1
  fi
done

{
  echo "manifest_schema=mi_dog_real/v3"
  echo "captured_at=$(date --iso-8601=seconds)"
  echo "hostname=$(hostname)"
  echo "kernel=$(uname -srmo)"
  echo "workspace=$workspace"
  echo "source_commit=$source_commit"
  echo "launch_mode=$launch_mode"
  echo "service_exec_start=$service_exec_start"
  echo "service_active=$(systemctl is-active mi-dog-real-sensor.service 2>/dev/null || true)"
  echo "mi_dog_real_node_pid=$real_node_pid"
  echo "mi_dog_supervisor_node_pid=$supervisor_pid"
  echo "mi_dog_state_bridge_node_pid=$bridge_pid"
  echo "mi_dog_estop_guard_node_pid=$estop_guard_pid"
  echo "mi_dog_race_controller_pid=$race_controller_pid"
  echo "ros_distro=${ROS_DISTRO:-unknown}"
  echo "ros_domain_id=${ROS_DOMAIN_ID:-unknown}"
  echo "rmw_implementation=${RMW_IMPLEMENTATION:-unknown}"
  echo "enable_motion=$effective_enable_motion"
  echo "require_sensor_ready=$effective_require_sensor_ready"
  echo "require_estop_ready=$effective_require_estop_ready"
  echo "require_supervisor_run_allowed=$effective_require_supervisor_run_allowed"
  echo "manage_dialogue=$effective_manage_dialogue"
  echo "min_battery_soc=$effective_min_battery_soc"
  echo "supervisor_state=$supervisor_state"
  echo "run_allowed=$run_allowed"
  echo "emergency_stop=$emergency_stop"
  echo "estop_guard_status=$estop_guard_status"
  echo "estop_hid_input_active=false"
  echo "competition_external_estop_required=false"
  echo "competition_voice_control_required=false"
  echo "competition_type_c_roles=UDisk,charge,download"
  echo "competition_network_dependency=none"
  echo "competition_computer_actions=START,CONTINUE,PAUSE,STOP,restart"
  echo "competition_ui_restart_sudo=$competition_ui_restart_sudo"
  echo "estop_hid_connection=not_required_unconfigured"
  echo "sha256_begin"
  sha256sum "${files[@]}"
  echo "sha256_end"
} > "$output_tmp"

chmod 0444 "$output_tmp"
mv -f "$output_tmp" "$output"
trap - EXIT
echo "$output"
