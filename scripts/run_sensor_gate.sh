#!/usr/bin/env bash
set -euo pipefail

launch_mode="${1:-sensor-only}"
mode_file=/home/mi/mi_dog_ws/state/launch_mode
if [[ -r "$mode_file" ]]; then
  IFS= read -r launch_mode < "$mode_file"
fi
if [[ "$launch_mode" != "sensor-only" && "$launch_mode" != "competition" && "$launch_mode" != "maintenance" ]]; then
  echo "usage: run_sensor_gate.sh [sensor-only|competition|maintenance]" >&2
  exit 2
fi

set +u
source /opt/ros2/galactic/setup.bash
source /opt/ros2/cyberdog/setup.bash
source /home/mi/mi_dog_ws/install/setup.bash
set -u

export ROS_DOMAIN_ID=42
export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp
export CYCLONEDDS_URI=file:///etc/mi/cyclonedds.xml

mkdir -p /home/mi/mi_dog_ws/state

# Starting CSI RGB while stock bringup is activating can exhaust NvCapture
# requests. Launch safety nodes now and let one long-running guard delay startup,
# verify real frames, and bound every capture session with reliable STOP/START
# cycles. Camera-stale gates keep motion at zero during each rest window.
camera_starter=/home/mi/mi_dog_ws/scripts/start_camera_when_stable.sh
if [[ -x "$camera_starter" ]]; then
  "$camera_starter" &
  echo "Guarded camera lifecycle started in the service cgroup (pid=$!)."
else
  echo "Camera lifecycle guard is missing; service remains fail-closed on camera." >&2
fi

if [[ "$launch_mode" == "competition" ]]; then
  echo "Starting armed competition stack in fail-closed DOWN_WAITING."
  exec ros2 launch mi_dog_real competition.launch.py
fi
if [[ "$launch_mode" == "maintenance" ]]; then
  echo "Starting manual maintenance stack in fail-closed DOWN_WAITING."
  exec ros2 launch mi_dog_real maintenance.launch.py
fi
exec ros2 launch mi_dog_real sensor_only.launch.py
