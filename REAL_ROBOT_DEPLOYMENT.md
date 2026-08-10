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

1. Calibrate foot-contact and proximity values while standing, unobstructed, and during a
   separately approved controlled leg lift.
2. Add ground-edge/clearance interpretation before connecting the lie-down request to posture motion.
3. Port perception and replace all Gazebo-only state (`/model_states`, world coordinates).
4. Validate an independent emergency stop and zero-speed command semantics before any nonzero command.
5. Implement and separately accept each physical stage controller before an end-to-end run.

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
and `bms_status`, plus the official LCM `state_estimator.contactEstimate[4]` bridged at about
50 Hz in RF/LF/RR/LR order. It requires all four contact values to be positive and a 1.5 s
stable interval, and publishes
`/mi_dog_real/supervisor/safe_to_lie_down` plus a machine-readable reason. Wired charging
always inhibits posture motion; on 2026-08-09 the live reason was
`wired_charging_motion_inhibited`. This is an observable permission only and does not issue
a lie-down command.

The same read-only bridge publishes `/mi_dog_real/proximity_summary` in metres as
`[ultrasonic, head-left median, head-right median, rear-left median, rear-right median]`.
The live lying/charging baseline was approximately `[0.21, 0.22, 0.21, 0.05, 0.05]`.
Proximity is deliberately not a safety gate yet: thresholds need a standing, unobstructed
calibration and edge/ground interpretation before they can authorize a posture change.

The first no-walk standing calibration completed on 2026-08-09. Recovery stand returned
`mode=12, progress=100`; foot contact stayed `[0.5, 0.5, 0.5, 0.5]`. Head ToF was about
`0.37/0.37 m`, rear ToF about `0.20/0.195 m`, while the front ultrasonic reading jumped
between roughly `0.34` and `0.57 m`. The ultrasonic channel therefore needs temporal
filtering rather than a single-frame authorization threshold. The dog returned to lying
with `mode=7, progress=100`.

This test also exposed a firmware-semantics bug: Xiaomi `motion_action` defines
`INT32_MIN (-2147483648)` as `kMotorNormal`. The supervisor now accepts both that sentinel
and zero as healthy motor entries; every other motor error value remains fail-closed. The
ARM64 rebuild passed, the sensor-only service restarted active, and the live safety reason
returned to `ready`.

A standing cardboard-box calibration then measured the front ultrasonic channel at roughly
`0.50..0.75 m` for a nominal 0.8 m box, a stable `0.468 m` at 0.5 m, and mostly `0.288 m`
(occasionally `0.296 m`) at 0.3 m. The whole-frame head ToF medians remained near
`0.37/0.37 m` at all three distances, so they do not represent this frontal target. A
candidate ultrasonic policy is stop at `<=0.35 m`, slow within `0.35..0.55 m`, require at
least three consecutive ordinary detections, and reserve a single-frame path for an
independently validated very-close emergency threshold. These values are not connected to
motion until different materials, widths, lateral offsets, and low-speed dynamics are tested.
Head ToF is analysed separately below because its field of view points toward the ground.

The bridge now exposes a separate read-only `/mi_dog_real/head_ground_roi_summary` as
`[left-centre p25, left-centre median, right-centre p25, right-centre median,
left-valid-fraction, right-valid-fraction]`. The first four fields are metres; the appended
fractions preserve compatibility with consumers of the original four-field prefix.
Each statistic uses the central 4x4 pixels of the raw 8x8 sensor. This symmetric ROI is
unchanged by the 180-degree raw-index reversal in Xiaomi's point-cloud utility. It remains
diagnostic-only until unobstructed and box-distance measurements establish useful thresholds.
With the box removed while lying and wired charging, the ROI baseline was approximately
`0.212/0.220 m` on the left and `0.208/0.216 m` on the right (p25/median). The supervisor
correctly cancelled a proposed standing sample because both BMS wired charging and the
official `MotionStatus.CHARGING=14` were active. Status 14 now reports the explicit reason
`motion_controller_charging_inhibited` instead of a generic controller fault.
After unplugging, one session retained controller status `CHARGING=14` while fresh BMS data
already reported no wired charging. A normal reboot restored `switch_status=0`. The supervisor
now identifies that exact fail-closed combination as `motion_controller_charging_state_stale`;
it never treats the fresh BMS reading as permission to bypass the motion controller.
An isolated `/mi_dog_test/...` replay verified both the stale-state and genuine-charging
reasons while keeping the safety result false; it published no real motion command.

`/mi_dog_real/supervisor/run_allowed` is independently fail-closed. In addition to the
supervisor being `RUNNING`, it requires fresh valid odometry within the 25-degree tilt limit,
fresh error-free motion status, and fresh healthy non-charging BMS data. Official motion
switches `NORMAL=0` and `TRANSITIONING=1` are accepted so a normal command transition does
not cut its own permission; ESTOP, damping, lifted, thermal, battery, controller-error, and
charging states revoke it. The run gate deliberately does not require all four feet to be in
contact because a valid gait lifts feet by design.
An isolated replay verified true for NORMAL and TRANSITIONING, false for ESTOP, 30-degree
tilt, stale odometry, wired charging, and a motion orientation error, plus recovery back to
true after each transient fault. After deployment the real service remained `DOWN_WAITING`
with `run_allowed=false` and safety reason `ready`; no real motion command was published.

Recomputing Xiaomi's raw-index mapping and installation rotations shows that all head-ToF
rays point downward by about 42 to 87 degrees in robot coordinates; the central 4x4 rays
span roughly 56 to 78 degrees downward. These sensors are therefore ground/drop-off inputs,
not frontal obstacle ranging. Future standing calibration should detect missing ground,
sudden range increases, and left/right disagreement. Such evidence may stop motion but must
never authorize forward motion by itself; ultrasonic and lidar remain the frontal sensors.

On 2026-08-10, a stationary standing run collected 20 flat-floor frames. Left p25/median
means were `0.3631/0.3756 m`, and right means were `0.3630/0.3768 m`; all observed values
were within about `0.356..0.382 m`. A matte-black floor covering produced
`0.3477/0.3600 m` left and `0.3402/0.3604 m` right: no return loss, only an approximately
1.6 cm shorter range. Surface colour therefore cannot stand in for a geometric drop-off.
The appended valid-pixel fractions make partial/no-return evidence observable, but remain
diagnostic-only and are not connected to motion.

The package installs a read-only capture utility:

```bash
ros2 run mi_dog_real ground_tof_capture.py --samples 20 --timeout 15
```

It reports mean/min/max for all six fields and never imports a motion-control interface.
Official geometry combined with the standing baseline places the central-ROI footprints at
approximately robot-frame `x=0.30..0.41 m`, left `y=0.09..0.19 m`, and right
`y=-0.19..-0.09 m`, close to the front feet. No object may be inserted there while standing.
Keeping every foot on an ordinary floor also cannot create a genuinely lower target, so home
testing is limited to stationary coverage/material checks. A geometric drop threshold requires
a purpose-built, fall-arrested rig with remotely changeable target panels.
