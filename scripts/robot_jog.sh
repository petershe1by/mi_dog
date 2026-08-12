#!/usr/bin/env bash
set -euo pipefail

target="${MI_DOG_TARGET:-mi@192.168.44.1}"
direction="${1:-}"
maintenance_controls="${MI_DOG_MAINTENANCE_CONTROLS:-0}"
connect_timeout=5

usage() {
  cat <<'EOF' >&2
Usage: robot_jog.sh {forward|backward|left|right|turn-left|turn-right|stop}

Publishes one low-speed 0.25-second pulse to /mi_dog_real/safe_cmd_vel.
Nonzero pulses are refused unless enable_motion=True and the supervisor's
latched run_allowed value is true. They also require the explicit local
MI_DOG_MAINTENANCE_CONTROLS=1 gate. A zero command is always permitted.
EOF
}

case "$direction" in
  forward)    vx=0.05;  vy=0.0;   wz=0.0 ;;
  backward)   vx=-0.04; vy=0.0;   wz=0.0 ;;
  left)       vx=0.0;   vy=0.03;  wz=0.0 ;;
  right)      vx=0.0;   vy=-0.03; wz=0.0 ;;
  turn-left)  vx=0.0;   vy=0.0;   wz=0.12 ;;
  turn-right) vx=0.0;   vy=0.0;   wz=-0.12 ;;
  stop)       vx=0.0;   vy=0.0;   wz=0.0 ;;
  *) usage; exit 2 ;;
esac

if [[ "$direction" != stop && "$maintenance_controls" != 1 ]]; then
  echo "jog_refused=maintenance_controls_disabled" >&2
  exit 3
fi

ssh_options=(
  -o StrictHostKeyChecking=accept-new
  -o "ConnectTimeout=$connect_timeout"
)
if [[ "${MI_DOG_SSH_BATCH_MODE:-0}" == 1 ]]; then
  ssh_options+=(-o BatchMode=yes)
fi
if [[ -n "${MI_DOG_SSH_IDENTITY:-}" ]]; then
  ssh_options+=(-o IdentitiesOnly=yes -i "$MI_DOG_SSH_IDENTITY")
fi

ssh "${ssh_options[@]}" "$target" bash -s -- "$direction" "$vx" "$vy" "$wz" <<'REMOTE_JOG'
set -eo pipefail
set +u
source /opt/ros2/galactic/setup.bash 2>/dev/null
source /opt/ros2/cyberdog/setup.bash 2>/dev/null
source /home/mi/mi_dog_ws/install/setup.bash 2>/dev/null
set -u
export ROS_DOMAIN_ID=42
export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp
export CYCLONEDDS_URI=file:///etc/mi/cyclonedds.xml

direction="$1"
vx="$2"
vy="$3"
wz="$4"
python3 - "$direction" "$vx" "$vy" "$wz" <<'PY'
import sys
import time

import rclpy
from geometry_msgs.msg import Twist
from rcl_interfaces.srv import GetParameters
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy
from std_msgs.msg import Bool

direction = sys.argv[1]
vx, vy, wz = map(float, sys.argv[2:])
rclpy.init()
node = Node("mi_dog_manual_jog")
latched = QoSProfile(
    depth=1,
    durability=DurabilityPolicy.TRANSIENT_LOCAL,
    reliability=ReliabilityPolicy.RELIABLE,
)
run_allowed = None


def allowed_callback(message):
    global run_allowed
    run_allowed = message.data


subscription = node.create_subscription(
    Bool, "/mi_dog_real/supervisor/run_allowed", allowed_callback, latched)
publisher = node.create_publisher(Twist, "/mi_dog_real/safe_cmd_vel", 10)
enable_motion = None
if direction != "stop":
    parameter_client = node.create_client(GetParameters, "/mi_dog_real/get_parameters")
    if parameter_client.wait_for_service(timeout_sec=2.0):
        request = GetParameters.Request()
        request.names = ["enable_motion"]
        future = parameter_client.call_async(request)
        rclpy.spin_until_future_complete(node, future, timeout_sec=3.0)
        if future.done() and future.result() and future.result().values:
            enable_motion = future.result().values[0].bool_value
    if enable_motion is not True:
        print(f"jog_refused=enable_motion_{enable_motion}")
        node.destroy_node()
        rclpy.shutdown()
        raise SystemExit(3)
deadline = time.monotonic() + 2.0
while time.monotonic() < deadline and (run_allowed is None or publisher.get_subscription_count() < 1):
    rclpy.spin_once(node, timeout_sec=0.05)

nonzero = any(abs(value) > 1e-9 for value in (vx, vy, wz))
if publisher.get_subscription_count() < 1:
    raise SystemExit("jog_refused=no_safe_cmd_vel_subscriber")
if nonzero and run_allowed is not True:
    raise SystemExit(f"jog_refused=run_allowed_{run_allowed}")

message = Twist()
message.linear.x = vx
message.linear.y = vy
message.angular.z = wz
duration = 0.25 if nonzero else 0.0
end = time.monotonic() + duration
while time.monotonic() < end:
    publisher.publish(message)
    rclpy.spin_once(node, timeout_sec=0.05)

message = Twist()
for _ in range(3):
    publisher.publish(message)
    rclpy.spin_once(node, timeout_sec=0.05)

print(f"jog_sent={direction}")
print(f"pulse_seconds={duration:.2f}")
print(f"run_allowed={str(run_allowed).lower() if run_allowed is not None else 'missing'}")
node.destroy_node()
rclpy.shutdown()
PY
REMOTE_JOG
