#!/usr/bin/env bash
set -euo pipefail

set +u
source /opt/ros2/galactic/setup.bash
source /opt/ros2/cyberdog/setup.bash
source /home/mi/mi_dog_ws/install/setup.bash
set -u

export ROS_DOMAIN_ID=42
export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp
export CYCLONEDDS_URI=file:///etc/mi/cyclonedds.xml

mkdir -p /home/mi/mi_dog_ws/state

camera_service=/mi_desktop_48_b0_2d_7a_fe_40/camera_service
camera_started=false

stop_camera() {
  if [[ "$camera_started" == true ]]; then
    timeout 12s ros2 service call "$camera_service" protocol/srv/CameraService \
      "{command: 10, args: '', width: 0, height: 0, fps: 0}" >/dev/null 2>&1 || true
  fi
}
trap stop_camera EXIT INT TERM

camera_response="$(
  timeout 20s ros2 service call "$camera_service" protocol/srv/CameraService \
    "{command: 9, args: '', width: 640, height: 480, fps: 10}" 2>&1 || true
)"
if grep -q 'result=0' <<< "$camera_response"; then
  camera_started=true
  echo "Camera stream enabled at 640x480, 10 fps."
else
  echo "Camera stream was not enabled; sensor-only service continues fail-closed." >&2
  echo "$camera_response" >&2
fi

ros2 launch mi_dog_real sensor_only.launch.py
