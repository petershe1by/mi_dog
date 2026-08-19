#!/usr/bin/env bash
# Source the exact ROS environment of the single live project supervisor.
# This avoids re-sourcing three large ROS setup trees for every UI click while
# remaining fail-closed when the service is absent or duplicated.

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  echo "load_live_ros_env.sh must be sourced." >&2
  exit 2
fi

supervisor_pattern="^/home/mi/mi_dog_ws/install/mi_dog_real/lib/mi_dog_real/mi_dog_supervisor_node "
mapfile -t _mi_dog_supervisor_pids < <(pgrep -f "$supervisor_pattern" || true)
if [[ ${#_mi_dog_supervisor_pids[@]} -ne 1 ]]; then
  echo "live_ros_env_refused=supervisor_count_${#_mi_dog_supervisor_pids[@]}" >&2
  unset _mi_dog_supervisor_pids supervisor_pattern
  return 1
fi

_mi_dog_environ="/proc/${_mi_dog_supervisor_pids[0]}/environ"
if [[ ! -r "$_mi_dog_environ" ]]; then
  echo "live_ros_env_refused=supervisor_environment_unreadable" >&2
  unset _mi_dog_supervisor_pids _mi_dog_environ supervisor_pattern
  return 1
fi

_mi_dog_loaded=0
while IFS= read -r -d '' _mi_dog_entry; do
  case "$_mi_dog_entry" in
    AMENT_PREFIX_PATH=*|COLCON_PREFIX_PATH=*|CMAKE_PREFIX_PATH=*|LD_LIBRARY_PATH=*|\
    PATH=*|PYTHONPATH=*|ROS_DISTRO=*|ROS_DOMAIN_ID=*|RMW_IMPLEMENTATION=*|CYCLONEDDS_URI=*)
      export "$_mi_dog_entry"
      _mi_dog_loaded=$((_mi_dog_loaded + 1))
      ;;
  esac
done <"$_mi_dog_environ"

if [[ $_mi_dog_loaded -lt 5 || "${ROS_DOMAIN_ID:-}" != 42 || \
      "${RMW_IMPLEMENTATION:-}" != rmw_cyclonedds_cpp ]]; then
  echo "live_ros_env_refused=incomplete_environment" >&2
  unset _mi_dog_supervisor_pids _mi_dog_environ _mi_dog_entry _mi_dog_loaded supervisor_pattern
  return 1
fi

unset _mi_dog_supervisor_pids _mi_dog_environ _mi_dog_entry _mi_dog_loaded supervisor_pattern
