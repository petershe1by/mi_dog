#!/usr/bin/env bash
set -euo pipefail

target="${MI_DOG_TARGET:-mi@192.168.44.1}"
action=""
stage=""
connect_timeout=5

usage() {
  cat <<'EOF'
Usage: competition_control.sh [--target USER@HOST] [--stage 1..6] ACTION

Actions:
  status     Read service, supervisor state, stage, and run permission.
  start      Request START from stage 1 through the supervisor safety gate.
  continue   Request CONTINUE from the saved stage through the safety gate.
  select-stage
             Select and persist a stage while stopped; motion remains inhibited.
  continue-stage
             Select a stage, then request CONTINUE through the safety gate.
  pause      Revoke run permission and enter PAUSED.
  stop       Latch the supervisor in EMERGENCY_STOP.
  restart    Restart the sensor/competition service; it returns to DOWN_WAITING.

The script sends only a structured operator event. It never sends direction,
speed, gait, posture, or raw motion-controller commands. SSH/sudo passwords are
entered interactively and are not stored by this script.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --target)
      [[ $# -ge 2 ]] || { usage >&2; exit 2; }
      target="$2"
      shift 2
      ;;
    --stage)
      [[ $# -ge 2 ]] || { usage >&2; exit 2; }
      stage="$2"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    status|start|continue|select-stage|continue-stage|pause|stop|restart)
      [[ -z "$action" ]] || { usage >&2; exit 2; }
      action="$1"
      shift
      ;;
    *)
      usage >&2
      exit 2
      ;;
  esac
done

if [[ -z "$action" || -z "$target" || "$target" =~ [[:space:]] ]]; then
  usage >&2
  exit 2
fi

if [[ "$action" == select-stage || "$action" == continue-stage ]]; then
  if [[ ! "$stage" =~ ^[1-6]$ ]]; then
    echo "--stage must be an integer from 1 through 6." >&2
    exit 2
  fi
elif [[ -n "$stage" ]]; then
  echo "--stage is only valid with select-stage or continue-stage." >&2
  exit 2
fi

ssh_options=(
  -o StrictHostKeyChecking=accept-new
  -o "ConnectTimeout=$connect_timeout"
)

if [[ -n "${MI_DOG_SSH_CONTROL_PATH:-}" ]]; then
  ssh_options+=(
    -o "ControlPath=$MI_DOG_SSH_CONTROL_PATH"
  )
fi
if [[ "${MI_DOG_SSH_BATCH_MODE:-0}" == 1 ]]; then
  ssh_options+=(
    -o BatchMode=yes
  )
fi
if [[ -n "${MI_DOG_SSH_IDENTITY:-}" ]]; then
  ssh_options+=(
    -o IdentitiesOnly=yes
    -i "$MI_DOG_SSH_IDENTITY"
  )
fi

if [[ "$action" == restart ]]; then
  # A restart must revoke the supervisor permission before any process exits.
  # STOP is idempotent and leaves the checkpointed stage intact; the service
  # restart then returns the supervisor to DOWN_WAITING without auto-resuming.
  "$0" --target "$target" stop
  restart_command='supervisor_pattern="^/home/mi/mi_dog_ws/install/mi_dog_real/lib/mi_dog_real/mi_dog_supervisor_node "
     old_supervisor="$(pgrep -f "$supervisor_pattern" | head -n 1 || true)"
     SUDO_PLACEHOLDER systemctl restart mi-dog-real-sensor.service &&
     for attempt in $(seq 1 90); do
       new_supervisor="$(pgrep -f "$supervisor_pattern" | head -n 1 || true)"
       if [ "$(systemctl is-active mi-dog-real-sensor.service 2>/dev/null)" = active ] &&
          [ -n "$new_supervisor" ] && [ "$new_supervisor" != "$old_supervisor" ]; then
         echo service_active=active
         echo supervisor_ready=new_process
         echo supervisor_restart_policy=DOWN_WAITING
         exit 0
       fi
       sleep 1
     done
     systemctl status mi-dog-real-sensor.service --no-pager
     exit 1'
  if [[ "${MI_DOG_SSH_BATCH_MODE:-0}" == 1 ]]; then
    restart_command="${restart_command/SUDO_PLACEHOLDER/sudo -n}"
    ssh "${ssh_options[@]}" "$target" "$restart_command"
  else
    restart_command="${restart_command/SUDO_PLACEHOLDER/sudo}"
    ssh -tt "${ssh_options[@]}" "$target" "$restart_command"
  fi
  exit
fi

event=""
case "$action" in
  start) event=START ;;
  continue) event=CONTINUE ;;
  continue-stage) event=CONTINUE ;;
  pause) event=PAUSE ;;
  stop) event=STOP ;;
esac

transport_event="${event:-NONE}"
ssh "${ssh_options[@]}" "$target" bash -s -- "$transport_event" "$stage" <<'REMOTE_CONTROL'
set -eo pipefail

set +u
source /opt/ros2/galactic/setup.bash 2>/dev/null
source /opt/ros2/cyberdog/setup.bash 2>/dev/null
source /home/mi/mi_dog_ws/install/setup.bash 2>/dev/null
set -u
export ROS_DOMAIN_ID=42
export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp
export CYCLONEDDS_URI=file:///etc/mi/cyclonedds.xml

echo "service_active=$(systemctl is-active mi-dog-real-sensor.service 2>/dev/null || true)"

event="${1:-NONE}"
[[ "$event" == NONE ]] && event=""
stage="${2:-}"
python3 - "$event" "$stage" <<'PY'
import sys
import time

import rclpy
from rcl_interfaces.srv import GetParameters
from rclpy.node import Node
from protocol.msg import BmsStatus, MotionStatus
from rclpy.qos import (
    DurabilityPolicy,
    QoSProfile,
    ReliabilityPolicy,
    qos_profile_sensor_data,
)
from std_msgs.msg import Bool, Int32, String

event, stage_arg = sys.argv[1:]
allowed_events = {"", "START", "CONTINUE", "PAUSE", "STOP"}
if event not in allowed_events:
    raise SystemExit("Refusing unknown operator event")

rclpy.init()
node = Node("mi_dog_competition_control")
latched = QoSProfile(
    depth=1,
    durability=DurabilityPolicy.TRANSIENT_LOCAL,
    reliability=ReliabilityPolicy.RELIABLE,
)
values = {}
subscriptions = []
supervisor_keys = ("state", "stage", "run_allowed", "safety_reason")
battery_keys = (
    "battery_percent",
    "battery_voltage_v",
    "battery_temp_c",
    "battery_health",
    "wired_charging",
    "power_normal",
)
display_keys = supervisor_keys + ("safe_to_lie_down",) + battery_keys + (
    "motion_id", "motion_progress", "motion_switch_status")


def save(key):
    def callback(message):
        value = message.data
        values[key] = str(value).lower() if isinstance(value, bool) else str(value)
    return callback


def save_battery(message):
    values["battery_percent"] = str(message.batt_soc)
    values["battery_voltage_v"] = f"{message.batt_volt / 1000.0:.3f}"
    values["battery_temp_c"] = str(message.batt_temp)
    values["battery_health"] = str(message.batt_health)
    values["wired_charging"] = str(message.power_wired_charging).lower()
    values["power_normal"] = str(message.power_normal).lower()


subscriptions.append(node.create_subscription(
    String, "/mi_dog_real/supervisor/state", save("state"), latched))
subscriptions.append(node.create_subscription(
    Int32, "/mi_dog_real/supervisor/current_stage", save("stage"), latched))
subscriptions.append(node.create_subscription(
    Bool, "/mi_dog_real/supervisor/run_allowed", save("run_allowed"), latched))
subscriptions.append(node.create_subscription(
    String, "/mi_dog_real/supervisor/lie_down_safety_reason",
    save("safety_reason"), latched))
subscriptions.append(node.create_subscription(
    Bool, "/mi_dog_real/supervisor/safe_to_lie_down",
    save("safe_to_lie_down"), latched))
subscriptions.append(node.create_subscription(
    BmsStatus, "/mi_desktop_48_b0_2d_7a_fe_40/bms_status",
    save_battery, qos_profile_sensor_data))


def save_motion_status(message):
    values["motion_id"] = str(message.motion_id)
    values["motion_progress"] = str(message.order_process_bar)
    values["motion_switch_status"] = str(message.switch_status)


subscriptions.append(node.create_subscription(
    MotionStatus, "/mi_desktop_48_b0_2d_7a_fe_40/motion_status",
    save_motion_status, qos_profile_sensor_data))

enable_motion = "unknown"
parameter_client = node.create_client(GetParameters, "/mi_dog_real/get_parameters")
if parameter_client.wait_for_service(timeout_sec=2.0):
    request = GetParameters.Request()
    request.names = ["enable_motion"]
    future = parameter_client.call_async(request)
    rclpy.spin_until_future_complete(node, future, timeout_sec=3.0)
    if future.done() and future.result() and future.result().values:
        enable_motion = str(future.result().values[0].bool_value)
print(f"enable_motion={enable_motion}")

min_battery_soc = "unknown"
supervisor_parameter_client = node.create_client(
    GetParameters, "/mi_dog_supervisor/get_parameters")
if supervisor_parameter_client.wait_for_service(timeout_sec=2.0):
    request = GetParameters.Request()
    request.names = ["min_battery_soc"]
    future = supervisor_parameter_client.call_async(request)
    rclpy.spin_until_future_complete(node, future, timeout_sec=3.0)
    if future.done() and future.result() and future.result().values:
        min_battery_soc = str(future.result().values[0].integer_value)
print(f"min_battery_soc={min_battery_soc}")

stage_publisher = None
selected_stage = int(stage_arg) if stage_arg else None
if selected_stage is not None:
    if selected_stage not in range(1, 7):
        raise SystemExit("Refusing stage outside 1..6")
    stage_publisher = node.create_publisher(
        Int32, "/mi_dog_real/supervisor/select_stage", QoSProfile(depth=10))
    deadline = time.monotonic() + 2.0
    while stage_publisher.get_subscription_count() < 1 and time.monotonic() < deadline:
        rclpy.spin_once(node, timeout_sec=0.1)
    if stage_publisher.get_subscription_count() < 1:
        raise SystemExit("Supervisor stage-select subscriber is unavailable")
    message = Int32()
    message.data = selected_stage
    stage_publisher.publish(message)
    deadline = time.monotonic() + 3.0
    while time.monotonic() < deadline:
        rclpy.spin_once(node, timeout_sec=0.1)
        if values.get("stage") == str(selected_stage):
            break
    if values.get("stage") != str(selected_stage):
        raise SystemExit(
            f"Stage selection rejected; current stage={values.get('stage', '<missing>')}")
    print(f"stage_selected={selected_stage}")

publisher = None
if event:
    publisher = node.create_publisher(
        String, "/mi_dog_real/operator_event", QoSProfile(depth=10))
    deadline = time.monotonic() + 2.0
    while publisher.get_subscription_count() < 1 and time.monotonic() < deadline:
        rclpy.spin_once(node, timeout_sec=0.1)
    if publisher.get_subscription_count() < 1:
        raise SystemExit("Supervisor operator-event subscriber is unavailable")
    message = String()
    message.data = event
    publisher.publish(message)
    print(f"event_sent={event}")

deadline = time.monotonic() + 5.0
while time.monotonic() < deadline:
    rclpy.spin_once(node, timeout_sec=0.1)
    display_ready = all(key in values for key in display_keys)
    if display_ready and (
            not event or time.monotonic() > deadline - 4.0):
        break

for key in display_keys:
    print(f"{key}={values.get(key, '<missing>')}")

node.destroy_node()
rclpy.shutdown()
if not all(key in values for key in supervisor_keys):
    raise SystemExit("Timed out reading supervisor state")
expected_state = {
    "START": "RUNNING",
    "CONTINUE": "RUNNING",
    "PAUSE": "PAUSED",
    "STOP": "EMERGENCY_STOP",
}.get(event)
if expected_state and values.get("state") != expected_state:
    raise SystemExit(
        f"event_rejected={event}; expected_state={expected_state}; "
        f"actual_state={values.get('state', '<missing>')}"
    )
PY
REMOTE_CONTROL
