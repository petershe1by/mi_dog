#!/usr/bin/env bash
set -eo pipefail
container="${1:-mi-dog-race}"
fail(){ printf 'FAIL: %s\n' "$1" >&2; exit 1; }
[ "$(docker inspect -f '{{.State.Running}}' "$container" 2>/dev/null)" = true ] || fail 'container is not running'
run_ros(){ docker exec "$container" bash -lc "source /opt/ros/galactic/setup.bash; source /home/cyberdog_sim/install/setup.bash; $*"; }
run_ros 'ros2 node list' | grep -qx '/race_autonomy' || fail 'race_autonomy node missing'
run_ros 'ros2 topic info /scan' | grep -q 'Publisher count: 1' || fail 'lidar publisher missing'
run_ros 'ros2 topic info /scan' | grep -q 'Subscription count: 1' || fail 'lidar subscriber missing'
run_ros 'ros2 topic info /race/front/image_raw' | grep -q 'Publisher count: 1' || fail 'camera publisher missing'
run_ros 'ros2 topic info /race/front/image_raw' | grep -q 'Subscription count: 1' || fail 'camera subscriber missing'
run_ros 'ros2 topic info /model_states' | grep -q 'Publisher count: 1' || fail 'model state publisher missing'
run_ros 'ros2 topic info /model_states' | grep -q 'Subscription count: 1' || fail 'model state subscriber missing'
docker exec "$container" test -s /opt/mi_dog/audio/coke.wav || fail 'audio assets missing'
docker exec "$container" pgrep -x gzserver >/dev/null || fail 'gzserver missing'
docker exec "$container" pgrep -f './cyberdog_control m s' >/dev/null || fail 'controller missing'
printf 'PASS: container, Gazebo, controller, autonomy, lidar, camera and audio assets\n'
