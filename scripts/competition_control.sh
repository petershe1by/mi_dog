#!/usr/bin/env bash
set -euo pipefail

target="${MI_DOG_TARGET:-mi@192.168.44.1}"
action=""
connect_timeout=5

usage() {
  cat <<'EOF'
Usage: competition_control.sh [--target USER@HOST] ACTION

Actions:
  status     Read service, supervisor state, stage, and run permission.
  start      Request START from stage 1 through the supervisor safety gate.
  continue   Request CONTINUE from the saved stage through the safety gate.
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
    -h|--help)
      usage
      exit 0
      ;;
    status|start|continue|pause|stop|restart)
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

ssh_options=(
  -o StrictHostKeyChecking=accept-new
  -o "ConnectTimeout=$connect_timeout"
)

if [[ -n "${MI_DOG_SSH_CONTROL_PATH:-}" ]]; then
  ssh_options+=(
    -o "ControlPath=$MI_DOG_SSH_CONTROL_PATH"
  )
fi

if [[ "$action" == restart ]]; then
  ssh -tt "${ssh_options[@]}" "$target" \
    'sudo systemctl restart mi-dog-real-sensor.service &&
     for attempt in $(seq 1 30); do
       if [ "$(systemctl is-active mi-dog-real-sensor.service 2>/dev/null)" = active ]; then
         echo service_active=active
         echo supervisor_restart_policy=DOWN_WAITING
         exit 0
       fi
       sleep 1
     done
     systemctl status mi-dog-real-sensor.service --no-pager
     exit 1'
  exit
fi

event=""
case "$action" in
  start) event=START ;;
  continue) event=CONTINUE ;;
  pause) event=PAUSE ;;
  stop) event=STOP ;;
esac

ssh "${ssh_options[@]}" "$target" bash -s -- "$event" <<'REMOTE_CONTROL'
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

event="${1:-}"
python3 - "$event" <<'PY'
import sys
import time

import rclpy
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy
from std_msgs.msg import Bool, Int32, String

event = sys.argv[1]
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


def save(key):
    def callback(message):
        value = message.data
        values[key] = str(value).lower() if isinstance(value, bool) else str(value)
    return callback


subscriptions.append(node.create_subscription(
    String, "/mi_dog_real/supervisor/state", save("state"), latched))
subscriptions.append(node.create_subscription(
    Int32, "/mi_dog_real/supervisor/current_stage", save("stage"), latched))
subscriptions.append(node.create_subscription(
    Bool, "/mi_dog_real/supervisor/run_allowed", save("run_allowed"), latched))
subscriptions.append(node.create_subscription(
    String, "/mi_dog_real/supervisor/lie_down_safety_reason",
    save("safety_reason"), latched))

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
    if len(values) == 4 and (not event or time.monotonic() > deadline - 4.0):
        break

for key in ("state", "stage", "run_allowed", "safety_reason"):
    print(f"{key}={values.get(key, '<missing>')}")

node.destroy_node()
rclpy.shutdown()
if len(values) != 4:
    raise SystemExit("Timed out reading supervisor state")
PY
REMOTE_CONTROL
