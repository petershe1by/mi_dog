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
camera_topic=/mi_desktop_48_b0_2d_7a_fe_40/image
camera_active=false
if timeout 4s ros2 topic echo "$camera_topic" --once >/dev/null 2>&1; then
  camera_active=true
  echo "Camera stream was already active; preserving it across service restart."
else
  camera_response="$(
    timeout 20s ros2 service call "$camera_service" protocol/srv/CameraService \
      "{command: 9, args: '', width: 640, height: 480, fps: 10}" 2>&1 || true
  )"
  if grep -q 'result=0' <<< "$camera_response"; then
    camera_active=true
    echo "Camera stream enabled at 640x480, 10 fps."
  elif timeout 4s ros2 topic echo "$camera_topic" --once >/dev/null 2>&1; then
    camera_active=true
    echo "Camera stream became active even though the service response timed out."
  fi
fi

if [[ "$camera_active" != true ]]; then
  echo "Camera stream was not enabled; sensor-only service continues fail-closed." >&2
  echo "${camera_response:-camera topic inactive}" >&2
fi

ros2 launch mi_dog_real sensor_only.launch.py
