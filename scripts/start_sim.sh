#!/usr/bin/env bash
set -eo pipefail
cd /home/cyberdog_sim
source /opt/ros/galactic/setup.bash
source install/setup.bash
cleanup(){ kill 0 2>/dev/null || true; }
trap cleanup EXIT INT TERM
ros2 launch cyberdog_gazebo race_gazebo.launch.py use_lidar:=true paused:=false &
sleep 10
ros2 launch cyberdog_gazebo cyberdog_control_launch.py &
sleep 6
if [[ -n "${RACE_START_STAGE:-}" ]]; then
  timeout 8 gz model -m robot -x "${RACE_START_X:-3.05}" -y "${RACE_START_Y:-6.65}" -z 0.30 -Y "${RACE_START_YAW:-0}" || true
fi
ros2 launch cyberdog_visual cyberdog_visual.launch.py &
sleep 3
if [[ -n "${RACE_START_STAGE:-}" ]]; then
  race_args=(--ros-args -p start_stage:="${RACE_START_STAGE}")
  if [[ -n "${RACE_START_STEP:-}" ]]; then race_args+=(-p start_finish_step:="${RACE_START_STEP}"); fi
  ros2 run cyberdog_autonomy race_autonomy "${race_args[@]}" &
else
  ros2 run cyberdog_autonomy race_autonomy &
fi
wait
