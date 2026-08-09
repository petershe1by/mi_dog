# CyberDog 2 real-robot deployment checkpoint

Observed on 2026-08-05 over the physical Ethernet port.

- Laptop: `192.168.44.100/24`
- Main compute: `mi@192.168.44.1`, hostname `mi-desktop`, ARM64 Tegra, Ubuntu 18.04
- Locomotion board: `root@192.168.44.233`, hostname `TinaLinux`, ARM64, firmware `1.2.0.3`
- ROS 2: Galactic under `/opt/ros2`; robot overlay under `/opt/ros2/cyberdog`
- Robot namespace: `/mi_desktop_48_b0_2d_7a_fe_40`

The stock locomotion board and the pre-existing main-compute workspaces are backed up under
`../cyberdog2_backup_20260805`. Never run the bundled `scp_to_cyberdog.sh`; it deletes the stock
`/robot/robot-software` tree.

`mi_dog_real` is the isolated safety adapter. The dog-native build passed against
`protocol 1.0.0` and is persistently installed under `/home/mi/mi_dog_ws` (7 MB).
Its per-dog profile keeps `enable_motion: false`. The persistent acceptance run observed
`camera=1, lidar=1, pose=0`; its exit trap shut image publishing down cleanly. Localization
and pose remained inactive.

The main compute root filesystem initially had only 2.7 MB free. The explicitly approved
deletion of `/home/mi/.cache/pip` (download cache only) recovered 336 MB; 332 MB remained
after installation. No existing workspace, Python environment, model, VS Code server, or
stock robot software was removed.

Motion remains locked. The next acceptance gates are:

1. Persist and rerun the sensor-only install.
2. Add reversible camera start/stop handling.
3. Verify the meaning of `MotionStatus.contact` or locate another documented foot-contact source.
4. Port perception and replace all Gazebo-only state (`/model_states`, world coordinates).
5. Validate emergency stop and zero-speed command semantics before any nonzero command.

## Voice competition gate

The adapter now has a fail-closed voice gate.  With `require_voice_start: true`, motion
remains inhibited until an exact `std_msgs/msg/String` command arrives on
`/mi_dog_real/voice_command`:

- `开始比赛`: enable race motion only when required sensors and the emergency-stop
  heartbeat are healthy.
- `继续比赛`: re-enable under the same checks after a voice stop.
- `停止比赛`: immediately invalidate the current motion command and inhibit output.

The latched `/mi_dog_real/race_enabled` topic exposes the gate state to the future real
autonomy supervisor.  This layer intentionally does not translate directional speech into
velocity.  The stock CyberDog 2 wake word is `铁蛋铁蛋`; the bundled Xiaomi audio demo can
set another word by publishing `std_msgs/msg/String` on the namespaced `wake_word` topic.
`publish_wake_word` remains false by default so normal deployment does not alter the stock
voice configuration.  The robot's recognized-text and wake topics are now mapped in
`this_robot_sensor_only.yaml`; live tests accepted the exact short commands `启动` and `暂停`.

The 2026-08-09 handoff now includes `mi_dog_supervisor_node` and an enabled
`mi-dog-real-sensor.service`.  The service remains sensor-only.  Synthetic acceptance proved
ordered stage advancement, rejection of completion while paused, checkpoint persistence, and
fail-closed restart at `DOWN_WAITING`.  Real locomotion, safe lie-down, perception adapters,
and six physical stage controllers remain separate unproven gates.

The next read-only gate now runs on the robot. `/odom_out` is continuous at about 48 Hz and
provides a valid body quaternion plus twist. The supervisor combines it with `motion_status`
and `bms_status`, requires a 1.5 s stable interval, and publishes
`/mi_dog_real/supervisor/safe_to_lie_down` plus a machine-readable reason. Wired charging
always inhibits posture motion; on 2026-08-09 the live reason was
`wired_charging_motion_inhibited`. This is an observable permission only and does not issue
a lie-down command.
