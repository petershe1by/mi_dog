#!/usr/bin/env bash
set -euo pipefail

service=mi-dog-real-sensor.service
if [[ "$(systemctl is-active "$service" 2>/dev/null || true)" != active ]]; then
  echo "PREFLIGHT=FAIL service_not_active" >&2
  exit 1
fi
exec_start="$(systemctl show "$service" -p ExecStart --value --no-pager)"
if [[ "$exec_start" != *"run_sensor_gate.sh competition"* ]]; then
  echo "PREFLIGHT=FAIL service_not_in_competition_mode" >&2
  exit 1
fi

set +u
source /opt/ros2/galactic/setup.bash
source /opt/ros2/cyberdog/setup.bash
source /home/mi/mi_dog_ws/install/setup.bash
set -u

export ROS_DOMAIN_ID=42
export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp
export CYCLONEDDS_URI=file:///etc/mi/cyclonedds.xml

python3 - <<'PY'
import json
import time

import rclpy
from nav_msgs.msg import Odometry
from protocol.msg import BmsStatus, MotionServoCmd, MotionStatus
from rcl_interfaces.srv import GetParameters
from rclpy.node import Node
from rclpy.qos import (
    DurabilityPolicy,
    QoSProfile,
    ReliabilityPolicy,
    qos_profile_sensor_data,
)
from sensor_msgs.msg import Image, LaserScan
from std_msgs.msg import Bool, String


def fail(reason):
    raise SystemExit("PREFLIGHT=FAIL " + reason)


rclpy.init()
node = Node("mi_dog_competition_preflight")
seen = {}
counts = {"camera": 0, "lidar": 0, "odom": 0, "servo": 0}
base = "/mi_desktop_48_b0_2d_7a_fe_40"
latched = QoSProfile(
    depth=1,
    reliability=ReliabilityPolicy.RELIABLE,
    durability=DurabilityPolicy.TRANSIENT_LOCAL,
)
subscriptions = []


def count(key):
    def callback(_message):
        counts[key] += 1
    return callback


def save(key):
    def callback(message):
        seen[key] = message.data
    return callback


subscriptions += [
    node.create_subscription(
        Image, base + "/image", count("camera"), qos_profile_sensor_data),
    node.create_subscription(
        LaserScan, base + "/scan", count("lidar"), qos_profile_sensor_data),
    node.create_subscription(
        Odometry, base + "/odom_out", count("odom"), qos_profile_sensor_data),
    node.create_subscription(
        MotionServoCmd, base + "/motion_servo_cmd", count("servo"), 10),
    node.create_subscription(
        String, "/mi_dog_real/supervisor/state", save("state"), latched),
    node.create_subscription(
        Bool, "/mi_dog_real/supervisor/run_allowed", save("allowed"), latched),
    node.create_subscription(
        String, "/mi_dog_real/race_controller/status", save("controller"), latched),
    node.create_subscription(
        String, "/mi_dog_real/course_perception/status", save("perception"), latched),
    node.create_subscription(
        String, "/mi_dog_real/course_observation", save("observation"), 10),
]


def save_bms(message):
    seen["bms"] = message


def save_motion(message):
    seen["motion"] = message


subscriptions += [
    node.create_subscription(
        BmsStatus, base + "/bms_status", save_bms, qos_profile_sensor_data),
    node.create_subscription(
        MotionStatus, base + "/motion_status", save_motion, qos_profile_sensor_data),
]

deadline = time.monotonic() + 8.0
while time.monotonic() < deadline:
    rclpy.spin_once(node, timeout_sec=0.1)

missing = [key for key in ("state", "allowed", "controller", "perception",
                           "observation", "bms", "motion")
           if key not in seen]
if missing:
    fail("missing=" + ",".join(missing))
if any(counts[key] == 0 for key in ("camera", "lidar", "odom")):
    fail("sensor_samples=" + json.dumps(counts, separators=(",", ":")))
if seen["state"] != "DOWN_WAITING" or seen["allowed"]:
    fail(f"unsafe_idle state={seen['state']} allowed={seen['allowed']}")
if counts["servo"] != 0:
    fail(f"idle_servo_frames={counts['servo']}")

try:
    controller = json.loads(seen["controller"])
except (TypeError, ValueError):
    fail("invalid_controller_status")
if controller.get("course_calibrated") is not True:
    fail("course_not_calibrated")
if controller.get("geometry_valid") is not True:
    fail("course_geometry_invalid")
if controller.get("geometry_source") != "official_2026_problem_pdf_page_3":
    fail("course_geometry_source=" + repr(controller.get("geometry_source")))
if controller.get("sensors_fresh") is not True:
    fail("controller_sensors_not_fresh")
try:
    perception = json.loads(seen["perception"])
    observation = json.loads(seen["observation"])
except (TypeError, ValueError):
    fail("invalid_perception_payload")
if perception.get("schema") != "mi_dog_course_observation_v1":
    fail("perception_schema=" + repr(perception.get("schema")))
if perception.get("site_transform_valid") is not True:
    fail("site_transform_not_calibrated")
if perception.get("facts_are_physical_only") is not True:
    fail("perception_fact_policy_invalid")
required_fresh = {"image", "scan", "odom"}
perception_fresh = perception.get("sensors_fresh", {})
if set(perception_fresh) != required_fresh or not all(perception_fresh.values()):
    fail("perception_sensors_not_fresh")
if observation.get("schema") != "mi_dog_course_observation_v1":
    fail("observation_schema=" + repr(observation.get("schema")))
if not isinstance(observation.get("facts"), dict):
    fail("observation_facts_invalid")
if observation.get("site_transform_valid") is not True:
    fail("observation_site_transform_invalid")
observation_fresh = observation.get("sensors_fresh", {})
if set(observation_fresh) != required_fresh or not all(observation_fresh.values()):
    fail("observation_sensors_not_fresh")
confidence = observation.get("localization_confidence")
if not isinstance(confidence, (int, float)) or confidence < 0.65:
    fail("observation_localization_uncertain")

bms = seen["bms"]
if bms.power_wired_charging:
    fail("wired_charging")
if not bms.power_normal or bms.batt_soc < 50:
    fail(f"power_not_ready soc={bms.batt_soc} normal={bms.power_normal}")
motion = seen["motion"]
if motion.switch_status != MotionStatus.NORMAL:
    fail(f"motion_switch_status={motion.switch_status}")

expected_nodes = {
    "/mi_dog_real",
    "/mi_dog_state_bridge",
    "/mi_dog_supervisor",
    "/mi_dog_course_perception",
    "/mi_dog_race_controller",
}
node_names = [namespace.rstrip("/") + "/" + name
              for name, namespace in node.get_node_names_and_namespaces()]
duplicates = [name for name in expected_nodes if node_names.count(name) != 1]
if duplicates:
    fail("node_count=" + ",".join(
        f"{name}:{node_names.count(name)}" for name in sorted(duplicates)))

client = node.create_client(GetParameters, "/mi_dog_real/get_parameters")
if not client.wait_for_service(timeout_sec=2.0):
    fail("adapter_parameter_service_missing")
request = GetParameters.Request()
request.names = [
    "enable_motion",
    "require_sensor_ready",
    "require_supervisor_run_allowed",
]
future = client.call_async(request)
rclpy.spin_until_future_complete(node, future, timeout_sec=3.0)
if not future.done() or future.result() is None:
    fail("adapter_parameters_unavailable")
values = [value.bool_value for value in future.result().values]
if values != [True, True, True]:
    fail("adapter_safety_parameters=" + repr(values))

print("PREFLIGHT=PASS")
print("mode=competition")
print("state=DOWN_WAITING run_allowed=false idle_servo_frames=0")
print("sensor_samples=" + json.dumps(counts, separators=(",", ":")))
print(f"battery_percent={bms.batt_soc} motion_switch_status={motion.switch_status}")
print("course_calibrated=true")
print("course_geometry=official_2026_problem_pdf_page_3 valid=true")
node.destroy_node()
rclpy.shutdown()
PY
