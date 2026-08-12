#!/usr/bin/env bash
set -euo pipefail

target="mi@192.168.44.1"
identity_file=""
connect_timeout=5

usage() {
  cat <<'EOF'
Usage: robot_read_only_audit.sh [--target USER@HOST] [--identity FILE] [--connect-timeout SECONDS]

Runs a key-only, read-only safety audit on the CyberDog 2 main computer.
It does not publish ROS messages, restart services, write manifests, or enable motion.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --target)
      [[ $# -ge 2 ]] || { usage >&2; exit 2; }
      target="$2"
      shift 2
      ;;
    --identity)
      [[ $# -ge 2 ]] || { usage >&2; exit 2; }
      identity_file="$2"
      shift 2
      ;;
    --connect-timeout)
      [[ $# -ge 2 ]] || { usage >&2; exit 2; }
      connect_timeout="$2"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      usage >&2
      exit 2
      ;;
  esac
done

if [[ -z "$target" || "$target" =~ [[:space:]] ]]; then
  echo "Invalid --target: expected USER@HOST without whitespace." >&2
  exit 2
fi
if [[ ! "$connect_timeout" =~ ^[1-9][0-9]?$ ]] || (( connect_timeout > 60 )); then
  echo "Invalid --connect-timeout: expected an integer from 1 to 60." >&2
  exit 2
fi
if [[ -n "$identity_file" && ! -f "$identity_file" ]]; then
  echo "Identity file does not exist: $identity_file" >&2
  exit 2
fi

ssh_options=(
  -o BatchMode=yes
  -o PasswordAuthentication=no
  -o KbdInteractiveAuthentication=no
  -o ChallengeResponseAuthentication=no
  -o PubkeyAuthentication=yes
  -o StrictHostKeyChecking=accept-new
  -o "ConnectTimeout=$connect_timeout"
)
if [[ -n "$identity_file" ]]; then
  ssh_options+=( -o IdentitiesOnly=yes -i "$identity_file" )
fi

echo "Starting read-only CyberDog 2 audit on $target"
echo "No ROS messages, service restarts, file writes, or motion commands will be issued."

ssh "${ssh_options[@]}" "$target" 'bash -s' <<'REMOTE_AUDIT'
set -eo pipefail

workspace=/home/mi/mi_dog_ws
install_root="$workspace/install/mi_dog_real"
failures=0

pass() {
  printf '[PASS] %s\n' "$1"
}

fail() {
  printf '[FAIL] %s\n' "$1" >&2
  failures=$((failures + 1))
}

expect_equal() {
  local label="$1"
  local actual="$2"
  local expected="$3"
  if [[ "$actual" == "$expected" ]]; then
    pass "$label=$actual"
  else
    fail "$label expected '$expected', got '${actual:-<empty>}'"
  fi
}

count_processes() {
  local executable="$1"
  local -a pids=()
  mapfile -t pids < <(pgrep -f "^${executable}([[:space:]]|$)" || true)
  printf '%s' "${#pids[@]}"
}

read_param() {
  local node="$1"
  local parameter="$2"
  timeout 5s ros2 param get "$node" "$parameter" 2>/dev/null |
    awk -F': ' 'NF >= 2 {print $2; exit}'
}

service_active="$(systemctl is-active mi-dog-real-sensor.service 2>/dev/null || true)"
service_enabled="$(systemctl is-enabled mi-dog-real-sensor.service 2>/dev/null || true)"
expect_equal service_active "$service_active" active
expect_equal service_enabled "$service_enabled" enabled

for setup_file in /opt/ros2/galactic/setup.bash /opt/ros2/cyberdog/setup.bash \
                  "$workspace/install/setup.bash"; do
  if [[ ! -f "$setup_file" ]]; then
    fail "required ROS setup is missing: $setup_file"
  fi
done

if (( failures == 0 )); then
  source /opt/ros2/galactic/setup.bash
  source /opt/ros2/cyberdog/setup.bash
  source "$workspace/install/setup.bash"
else
  echo "Audit stopped before ROS discovery because the installed environment is incomplete." >&2
  exit 1
fi

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
expect_equal estop_guard_node_count \
  "$(count_processes "$install_root/lib/mi_dog_real/mi_dog_estop_guard_node")" 1

hid_count="$(pgrep -fc '/estop_hid_input.py([[:space:]]|$)' || true)"
expect_equal estop_hid_input_count "$hid_count" 0

enable_motion="$(read_param /mi_dog_real enable_motion || true)"
manage_dialogue="$(read_param /mi_dog_real manage_dialogue || true)"
require_supervisor="$(read_param /mi_dog_real require_supervisor_run_allowed || true)"
require_sensor="$(read_param /mi_dog_real require_sensor_ready || true)"
require_estop="$(read_param /mi_dog_real require_estop_ready || true)"

expect_equal enable_motion "$enable_motion" False
expect_equal manage_dialogue "$manage_dialogue" False
expect_equal require_supervisor_run_allowed "$require_supervisor" True
printf '[INFO] require_sensor_ready=%s\n' "${require_sensor:-<empty>}"
printf '[INFO] require_estop_ready=%s\n' "${require_estop:-<empty>}"

topic_values="$(python3 - <<'PY'
import time

import rclpy
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy
from std_msgs.msg import Bool, String

rclpy.init()
node = Node("mi_dog_read_only_audit_probe")
values = {}
subscriptions = []


def qos(durability):
    return QoSProfile(
        depth=1,
        durability=durability,
        reliability=ReliabilityPolicy.RELIABLE,
    )


def callback_for(key):
    def callback(message):
        value = message.data
        values[key] = str(value).lower() if isinstance(value, bool) else value
    return callback


specifications = (
    ("supervisor_state", "/mi_dog_real/supervisor/state", String,
     DurabilityPolicy.TRANSIENT_LOCAL),
    ("run_allowed", "/mi_dog_real/supervisor/run_allowed", Bool,
     DurabilityPolicy.TRANSIENT_LOCAL),
    ("emergency_stop", "/mi_dog_real/emergency_stop", Bool,
     DurabilityPolicy.VOLATILE),
    ("estop_guard_status", "/mi_dog_real/emergency_stop_guard/status", String,
     DurabilityPolicy.TRANSIENT_LOCAL),
)

for key, topic, message_type, durability in specifications:
    subscriptions.append(
        node.create_subscription(message_type, topic, callback_for(key), qos(durability))
    )

deadline = time.monotonic() + 8.0
while len(values) < len(specifications) and time.monotonic() < deadline:
    rclpy.spin_once(node, timeout_sec=0.2)

for key, _, _, _ in specifications:
    print(f"{key}={values.get(key, '')}")

node.destroy_node()
rclpy.shutdown()
if len(values) != len(specifications):
    raise SystemExit(1)
PY
)" || {
  fail "one or more required safety topics did not arrive within 8 seconds"
  topic_values=""
}

declare -A live=()
while IFS='=' read -r key value; do
  [[ -n "$key" ]] && live["$key"]="$value"
done <<< "$topic_values"

supervisor_state="${live[supervisor_state]:-}"
case "$supervisor_state" in
  DOWN_WAITING)
    pass "supervisor_state=$supervisor_state"
    ;;
  PAUSED|EMERGENCY_STOP)
    pass "supervisor_state=$supervisor_state (safe inhibited state)"
    ;;
  *)
    fail "supervisor_state expected a safe inhibited state, got '${supervisor_state:-<empty>}'"
    ;;
esac
expect_equal run_allowed "${live[run_allowed]:-}" false
expect_equal emergency_stop "${live[emergency_stop]:-}" true
expect_equal estop_guard_status "${live[estop_guard_status]:-}" input_missing

if (( failures > 0 )); then
  printf 'READ_ONLY_AUDIT=FAIL failures=%d\n' "$failures" >&2
  exit 1
fi

echo 'READ_ONLY_AUDIT=PASS'
REMOTE_AUDIT
