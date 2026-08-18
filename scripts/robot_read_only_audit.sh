#!/usr/bin/env bash
set -euo pipefail

target="mi@192.168.44.1"
identity_file=""
connect_timeout=5

usage() {
  cat <<'EOF'
Usage: robot_read_only_audit.sh [--target USER@HOST] [--identity FILE] [--connect-timeout SECONDS]

Runs a key-only, read-only audit of the installed maintenance, competition, or
sensor-only stack. It never publishes, restarts services, writes files, or
enables motion.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --target) target="${2:-}"; shift 2 ;;
    --identity) identity_file="${2:-}"; shift 2 ;;
    --connect-timeout) connect_timeout="${2:-}"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) usage >&2; exit 2 ;;
  esac
done

[[ -n "$target" && ! "$target" =~ [[:space:]] ]] || {
  echo "Invalid --target" >&2; exit 2; }
[[ "$connect_timeout" =~ ^[1-9][0-9]?$ ]] && (( connect_timeout <= 60 )) || {
  echo "Invalid --connect-timeout" >&2; exit 2; }
[[ -z "$identity_file" || -f "$identity_file" ]] || {
  echo "Identity file does not exist: $identity_file" >&2; exit 2; }

ssh_options=(
  -o BatchMode=yes
  -o PasswordAuthentication=no
  -o KbdInteractiveAuthentication=no
  -o ChallengeResponseAuthentication=no
  -o PubkeyAuthentication=yes
  -o StrictHostKeyChecking=accept-new
  -o "ConnectTimeout=$connect_timeout"
)
[[ -z "$identity_file" ]] || ssh_options+=( -o IdentitiesOnly=yes -i "$identity_file" )

echo "Starting read-only CyberDog 2 audit on $target"
echo "No ROS messages, service restarts, file writes, or motion commands will be issued."

ssh "${ssh_options[@]}" "$target" 'bash -s' <<'REMOTE_AUDIT'
set -eo pipefail

workspace=/home/mi/mi_dog_ws
install_root="$workspace/install/mi_dog_real"
service=mi-dog-real-sensor.service
failures=0

pass() { printf '[PASS] %s\n' "$1"; }
fail() { printf '[FAIL] %s\n' "$1" >&2; failures=$((failures + 1)); }
expect_equal() {
  if [[ "$2" == "$3" ]]; then pass "$1=$2";
  else fail "$1 expected '$3', got '${2:-<empty>}'"; fi
}
count_processes() {
  local -a pids=()
  mapfile -t pids < <(pgrep -f "^$1([[:space:]]|$)" || true)
  printf '%s' "${#pids[@]}"
}
read_param() {
  timeout 5s ros2 param get "$1" "$2" 2>/dev/null |
    awk -F': ' 'NF >= 2 {print $2; exit}'
}

expect_equal service_active "$(systemctl is-active "$service" 2>/dev/null || true)" active
expect_equal service_enabled "$(systemctl is-enabled "$service" 2>/dev/null || true)" enabled
exec_start="$(systemctl show "$service" -p ExecStart --value --no-pager)"
case "$exec_start" in
  *"run_sensor_gate.sh maintenance"*) mode=maintenance ;;
  *"run_sensor_gate.sh competition"*) mode=competition ;;
  *"run_sensor_gate.sh sensor-only"*) mode=sensor-only ;;
  *) mode=unknown; fail "unrecognized service ExecStart: $exec_start" ;;
esac
printf '[INFO] service_mode=%s\n' "$mode"

source /opt/ros2/galactic/setup.bash
source /opt/ros2/cyberdog/setup.bash
source "$workspace/install/setup.bash"
set -u
export ROS_DOMAIN_ID=42
export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp
export CYCLONEDDS_URI=file:///etc/mi/cyclonedds.xml

expect_equal mi_dog_real_node_count \
  "$(count_processes "$install_root/lib/mi_dog_real/mi_dog_real_node")" 1
expect_equal supervisor_node_count \
  "$(count_processes "$install_root/lib/mi_dog_real/mi_dog_supervisor_node")" 1
expect_equal state_bridge_node_count \
  "$(count_processes "$install_root/lib/mi_dog_real/mi_dog_state_bridge_node")" 1
controller_count="$(pgrep -fc '/race_controller.py([[:space:]]|$)' || true)"
if [[ "$mode" == competition ]]; then
  expect_equal race_controller_node_count "$controller_count" 1
else
  expect_equal race_controller_node_count "$controller_count" 0
fi
guard_count="$(count_processes "$install_root/lib/mi_dog_real/mi_dog_estop_guard_node")"
if [[ "$mode" == sensor-only ]]; then
  expect_equal estop_guard_node_count "$guard_count" 1
else
  expect_equal estop_guard_node_count "$guard_count" 0
fi
expect_equal estop_hid_input_count \
  "$(pgrep -fc '/estop_hid_input.py([[:space:]]|$)' || true)" 0

enable_motion="$(read_param /mi_dog_real enable_motion || true)"
expected_motion=True
[[ "$mode" != sensor-only ]] || expected_motion=False
expect_equal enable_motion "$enable_motion" "$expected_motion"
expect_equal manage_dialogue "$(read_param /mi_dog_real manage_dialogue || true)" False
expect_equal require_supervisor_run_allowed \
  "$(read_param /mi_dog_real require_supervisor_run_allowed || true)" True
expect_equal min_battery_soc \
  "$(read_param /mi_dog_supervisor min_battery_soc || true)" 30

python3 - "$mode" <<'PY'
import json
import sys
import time

import rclpy
from nav_msgs.msg import Odometry
from protocol.msg import BmsStatus, MotionServoCmd, MotionStatus
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy, qos_profile_sensor_data
from sensor_msgs.msg import Image, LaserScan
from std_msgs.msg import Bool, String

mode = sys.argv[1]
rclpy.init()
node = Node("mi_dog_read_only_audit_probe")
latched = QoSProfile(depth=1, reliability=ReliabilityPolicy.RELIABLE,
                     durability=DurabilityPolicy.TRANSIENT_LOCAL)
values = {}
counts = {"camera": 0, "lidar": 0, "odom": 0, "servo": 0}
base = "/mi_desktop_48_b0_2d_7a_fe_40"

def count(key):
    return lambda _message: counts.__setitem__(key, counts[key] + 1)
def save(key):
    return lambda message: values.__setitem__(key, message.data)

subscriptions = [
    node.create_subscription(Image, base + "/image", count("camera"), qos_profile_sensor_data),
    node.create_subscription(LaserScan, base + "/scan", count("lidar"), qos_profile_sensor_data),
    node.create_subscription(Odometry, base + "/odom_out", count("odom"), qos_profile_sensor_data),
    node.create_subscription(MotionServoCmd, base + "/motion_servo_cmd", count("servo"), 10),
    node.create_subscription(String, "/mi_dog_real/supervisor/state", save("state"), latched),
    node.create_subscription(Bool, "/mi_dog_real/supervisor/run_allowed", save("allowed"), latched),
    node.create_subscription(BmsStatus, base + "/bms_status",
                             lambda message: values.__setitem__("bms", message), qos_profile_sensor_data),
    node.create_subscription(MotionStatus, base + "/motion_status",
                             lambda message: values.__setitem__("motion", message), qos_profile_sensor_data),
]
if mode == "competition":
    subscriptions.append(node.create_subscription(
        String, "/mi_dog_real/race_controller/status", save("controller"), latched))

deadline = time.monotonic() + 8.0
while time.monotonic() < deadline:
    rclpy.spin_once(node, timeout_sec=0.1)

required = ["state", "allowed", "bms", "motion"]
if mode == "competition": required.append("controller")
missing = [key for key in required if key not in values]
if missing: raise SystemExit("READ_ONLY_AUDIT=FAIL missing=" + ",".join(missing))
if values["state"] not in ("DOWN_WAITING", "PAUSED", "EMERGENCY_STOP"):
    raise SystemExit("READ_ONLY_AUDIT=FAIL unsafe_state=" + values["state"])
if values["allowed"]:
    raise SystemExit("READ_ONLY_AUDIT=FAIL run_allowed=true")
if counts["servo"]:
    raise SystemExit(f"READ_ONLY_AUDIT=FAIL idle_servo_frames={counts['servo']}")

bms = values["bms"]
motion = values["motion"]
print(f"[PASS] supervisor_state={values['state']}")
print("[PASS] run_allowed=false")
print("[PASS] idle_servo_frames=0")
print("[INFO] sensor_samples=" + json.dumps(counts, separators=(",", ":")))
print(f"[INFO] battery_percent={bms.batt_soc} wired_charging={str(bms.power_wired_charging).lower()}")
print(f"[INFO] motion_switch_status={motion.switch_status}")
if mode == "competition":
    try: controller = json.loads(values["controller"])
    except (TypeError, ValueError):
        raise SystemExit("READ_ONLY_AUDIT=FAIL invalid_controller_status")
    print("[INFO] controller=" + json.dumps(controller, separators=(",", ":")))
print("READ_ONLY_TOPIC_AUDIT=PASS")
node.destroy_node()
rclpy.shutdown()
PY

if (( failures > 0 )); then
  printf 'READ_ONLY_AUDIT=FAIL failures=%d\n' "$failures" >&2
  exit 1
fi
echo 'READ_ONLY_AUDIT=PASS'
REMOTE_AUDIT
