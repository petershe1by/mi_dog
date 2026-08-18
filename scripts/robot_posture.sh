#!/usr/bin/env bash
set -euo pipefail

target="${MI_DOG_TARGET:-mi@192.168.44.1}"
action="${1:-}"
maintenance_controls="${MI_DOG_MAINTENANCE_CONTROLS:-0}"
connect_timeout=5

usage() {
  cat <<'EOF' >&2
Usage: robot_posture.sh {stand|lie-down}

Calls only the robot's observed official posture motion IDs: recovery stand
(111) or high-damping lie-down (101). The action is refused unless BMS,
supervisor, run-permission, and posture-specific safety gates are satisfied.
It additionally requires the explicit local MI_DOG_MAINTENANCE_CONTROLS=1 gate.
EOF
}

case "$action" in
  stand) motion_id=111 ;;
  lie-down) motion_id=101 ;;
  *) usage; exit 2 ;;
esac

if [[ "$maintenance_controls" != 1 ]]; then
  echo "posture_refused=maintenance_controls_disabled" >&2
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
from rcl_interfaces.msg import ParameterType
from rcl_interfaces.srv import GetParameters
from rclpy.node import Node
from rclpy.qos import (
    DurabilityPolicy,
    QoSProfile,
    ReliabilityPolicy,
    qos_profile_sensor_data,
)
from std_msgs.msg import Bool, String
from std_srvs.srv import Trigger

action = sys.argv[1]
motion_id = int(sys.argv[2])
hard_minimum_soc = 30
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
        parameter = future.result().values[0]
        candidate = int(parameter.integer_value)
        if (parameter.type == ParameterType.PARAMETER_INTEGER and
                hard_minimum_soc <= candidate <= 100):
            minimum_soc = max(hard_minimum_soc, candidate)

required_base = {
    "state", "run_allowed", "safe_to_lie_down", "safety_reason",
    "battery_percent", "wired_charging", "power_normal", "bms_faults_clear",
}
required_motion = {"motion_switch_status", "motion_errors_clear"}
deadline = time.monotonic() + 8.0
while (not required_base.issubset(values) or not required_motion.issubset(values)) and time.monotonic() < deadline:
    rclpy.spin_once(node, timeout_sec=0.1)


def refuse(reason):
    print(f"posture_refused={reason}")
    node.destroy_node()
    rclpy.shutdown()
    raise SystemExit(3)


if not required_base.issubset(values) or minimum_soc is None:
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
if required_motion.issubset(values):
    if not values["motion_errors_clear"]:
        refuse("motion_error")
    if values["motion_switch_status"] not in (MotionStatus.NORMAL, MotionStatus.EDAMP):
        refuse(f"motion_switch_{values['motion_switch_status']}")
elif action == "stand":
    # This firmware publishes MotionStatus only around actions. Before the first
    # posture action, use the stock read-only machine-state query instead.
    machine_client = node.create_client(
        Trigger, "/mi_desktop_48_b0_2d_7a_fe_40/machine_state_valget")
    if not machine_client.wait_for_service(timeout_sec=3.0):
        refuse("machine_state_service_unavailable")
    machine_future = machine_client.call_async(Trigger.Request())
    rclpy.spin_until_future_complete(node, machine_future, timeout_sec=3.0)
    machine_response = machine_future.result() if machine_future.done() else None
    if (machine_response is None or not machine_response.success or
            machine_response.message.strip().lower() != "active"):
        refuse("machine_state_not_active")
    print("machine_state_fallback=active")
else:
    refuse("motion_status_missing")
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
