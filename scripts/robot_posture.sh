#!/usr/bin/env bash
set -euo pipefail

target="${MI_DOG_TARGET:-mi@192.168.44.1}"
action="${1:-}"
connect_timeout=5

usage() {
  cat <<'EOF' >&2
Usage: robot_posture.sh {stand|lie-down}

Calls only the robot's observed official posture motion IDs: recovery stand
(111) or high-damping lie-down (101). The action is refused unless BMS,
supervisor, run-permission, and posture-specific safety gates are satisfied.
EOF
}

case "$action" in
  stand) motion_id=111 ;;
  lie-down) motion_id=101 ;;
  *) usage; exit 2 ;;
esac

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

ssh "${ssh_options[@]}" "$target" bash -s -- "$action" "$motion_id" <<'REMOTE_POSTURE'
set -eo pipefail
set +u
source /opt/ros2/galactic/setup.bash 2>/dev/null
source /opt/ros2/cyberdog/setup.bash 2>/dev/null
source /home/mi/mi_dog_ws/install/setup.bash 2>/dev/null
set -u
export ROS_DOMAIN_ID=42
export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp
export CYCLONEDDS_URI=file:///etc/mi/cyclonedds.xml

action="$1"
motion_id="$2"
python3 - "$action" "$motion_id" <<'PY'
import sys
import time

import rclpy
from protocol.msg import BmsStatus, MotionStatus
from protocol.srv import MotionResultCmd
from rcl_interfaces.srv import GetParameters
from rclpy.node import Node
from rclpy.qos import (
    DurabilityPolicy,
    QoSProfile,
    ReliabilityPolicy,
    qos_profile_sensor_data,
)
from std_msgs.msg import Bool, String

action = sys.argv[1]
motion_id = int(sys.argv[2])
expected_ids = {"stand": 111, "lie-down": 101}
if expected_ids.get(action) != motion_id:
    raise SystemExit("posture_refused=invalid_action_mapping")

rclpy.init()
node = Node("mi_dog_manual_posture")
latched = QoSProfile(
    depth=1,
    durability=DurabilityPolicy.TRANSIENT_LOCAL,
    reliability=ReliabilityPolicy.RELIABLE,
)
values = {}


def save_data(key):
    def callback(message):
        values[key] = message.data
    return callback


def save_bms(message):
    fault_fields = (
        "charge_over_current", "discharge_over_current",
        "cell_over_voltage", "cell_under_voltage", "cell_volt_abnormal",
        "mos_over_temp", "discharge_short", "fuse",
        "discharge_over_tmp", "discharge_under_tmp",
        "charge_over_temp", "charge_under_temp",
        "chg_mos_fault", "dsg_mos_fault",
    )
    values["battery_percent"] = int(message.batt_soc)
    values["wired_charging"] = bool(message.power_wired_charging)
    values["power_normal"] = bool(message.power_normal)
    values["bms_faults_clear"] = not any(
        bool(getattr(message, field)) for field in fault_fields)


def save_motion(message):
    values["motion_id"] = int(message.motion_id)
    values["motion_progress"] = int(message.order_process_bar)
    values["motion_switch_status"] = int(message.switch_status)
    values["motion_errors_clear"] = (
        int(message.ori_error) == 0 and int(message.footpos_error) == 0 and
        all(int(value) in (0, -(2 ** 31)) for value in message.motor_error)
    )


subscriptions = [
    node.create_subscription(
        String, "/mi_dog_real/supervisor/state", save_data("state"), latched),
    node.create_subscription(
        Bool, "/mi_dog_real/supervisor/run_allowed",
        save_data("run_allowed"), latched),
    node.create_subscription(
        Bool, "/mi_dog_real/supervisor/safe_to_lie_down",
        save_data("safe_to_lie_down"), latched),
    node.create_subscription(
        String, "/mi_dog_real/supervisor/lie_down_safety_reason",
        save_data("safety_reason"), latched),
    node.create_subscription(
        BmsStatus, "/mi_desktop_48_b0_2d_7a_fe_40/bms_status",
        save_bms, qos_profile_sensor_data),
    node.create_subscription(
        MotionStatus, "/mi_desktop_48_b0_2d_7a_fe_40/motion_status",
        save_motion, qos_profile_sensor_data),
]

minimum_soc = None
parameter_client = node.create_client(
    GetParameters, "/mi_dog_supervisor/get_parameters")
if parameter_client.wait_for_service(timeout_sec=2.0):
    request = GetParameters.Request()
    request.names = ["min_battery_soc"]
    future = parameter_client.call_async(request)
    rclpy.spin_until_future_complete(node, future, timeout_sec=3.0)
    if future.done() and future.result() and future.result().values:
        minimum_soc = int(future.result().values[0].integer_value)

required = {
    "state", "run_allowed", "safe_to_lie_down", "safety_reason",
    "battery_percent", "wired_charging", "power_normal", "bms_faults_clear",
    "motion_switch_status", "motion_errors_clear",
}
deadline = time.monotonic() + 8.0
while not required.issubset(values) and time.monotonic() < deadline:
    rclpy.spin_once(node, timeout_sec=0.1)


def refuse(reason):
    print(f"posture_refused={reason}")
    node.destroy_node()
    rclpy.shutdown()
    raise SystemExit(3)


if not required.issubset(values) or minimum_soc is None:
    refuse("safety_inputs_missing")
if values["state"] not in ("DOWN_WAITING", "PAUSED"):
    refuse(f"supervisor_state_{values['state']}")
if values["run_allowed"] is not False:
    refuse("run_allowed_not_false")
if values["battery_percent"] < minimum_soc:
    refuse(f"battery_{values['battery_percent']}_below_{minimum_soc}")
if values["wired_charging"]:
    refuse("wired_charging")
if not values["power_normal"]:
    refuse("power_not_normal")
if not values["bms_faults_clear"]:
    refuse("bms_fault")
if not values["motion_errors_clear"]:
    refuse("motion_error")
if values["motion_switch_status"] not in (MotionStatus.NORMAL, MotionStatus.EDAMP):
    refuse(f"motion_switch_{values['motion_switch_status']}")
if action == "lie-down" and (
        values["safe_to_lie_down"] is not True or values["safety_reason"] != "ready"):
    refuse(f"lie_down_not_safe_{values['safety_reason']}")

service_name = "/mi_desktop_48_b0_2d_7a_fe_40/motion_result_cmd"
client = node.create_client(MotionResultCmd, service_name)
if not client.wait_for_service(timeout_sec=3.0):
    refuse("motion_result_service_unavailable")
request = MotionResultCmd.Request()
if not hasattr(request, "motion_id"):
    refuse("motion_result_request_abi_mismatch")
request.motion_id = motion_id
future = client.call_async(request)
rclpy.spin_until_future_complete(node, future, timeout_sec=30.0)
if not future.done() or future.result() is None:
    refuse("motion_result_timeout")
response = future.result()
result = bool(getattr(response, "result", False))
code = int(getattr(response, "code", -1))
print(f"posture_action={action}")
print(f"motion_id={motion_id}")
print(f"service_result={str(result).lower()}")
print(f"service_code={code}")
if not result or code != 0:
    refuse(f"service_rejected_code_{code}")

deadline = time.monotonic() + 20.0
completed = False
while time.monotonic() < deadline:
    rclpy.spin_once(node, timeout_sec=0.1)
    if values.get("motion_id") == motion_id and values.get("motion_progress", 0) >= 95:
        completed = True
        break
print(f"motion_progress={values.get('motion_progress', 'missing')}")
print(f"posture_feedback_complete={str(completed).lower()}")
node.destroy_node()
rclpy.shutdown()
if not completed:
    raise SystemExit(4)
PY
REMOTE_POSTURE
