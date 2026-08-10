# `mi_dog_real`: CyberDog 2 真机适配包

这个包与 `cyberdog_autonomy`（Gazebo/LCM 仿真）完全隔离：不改 Dockerfile、不替换仿真控制器，也不把 x86 仿真镜像复制到狗上。

## 已实现的安全边界

- 默认 `enable_motion=false`：只订阅相机、雷达和姿态，绝不发布运动指令。
- 运动输出同时要求 `enable_motion=true` 和明确的 `arm_token`。
- 按配置要求的相机、雷达和机身姿态数据都在 1 秒内到达，才允许转发 `/mi_dog_real/safe_cmd_vel`。
- 300 ms 指令超时、任一传感器失联时，发送官方 `motion_servo_cmd` 停止命令。
- 默认要求 `/mi_dog_real/emergency_stop` 持续发布 `false` 心跳；心跳超过 0.5 秒或收到 `true` 都会进入停止状态。
- `mi_dog_estop_guard_node` 将未来独立硬件的
  `/mi_dog_real/emergency_stop_input` 转为上述心跳：启动、输入缺失或超过 0.25 秒均持续发布
  `true`。首次 `false` 不会解锁，必须先观察一次按下 `true` 再释放 `false`；断线恢复后也
  必须重复按下—释放周期。
- `estop_hid_input.py` 是 USB HID 常闭输入原型，FIFO 逻辑测试已通过，但机器狗三个外部
  Type-C 的 Host/Device 角色没有文档依据。内部 `lsusb` 不能证明外部端口可接 HID，因此
  正式开机服务不启动该原型，也不得据此插接任一 Type-C。
- 默认还要求 supervisor 的 `/mi_dog_real/supervisor/run_allowed` 持续为真；许可缺失、为假或
  超过 0.5 秒未刷新都会发送停止心跳，不能仅凭语音门或速度输入绕过 supervisor。
- 拒绝 NaN/Inf 指令；IMU 四元数归一化后执行横滚/俯仰门控，雷达使用前向扇区有效样本做减速和停车。
- 运动命令带加速度斜坡，停止状态以 0.2 秒周期持续发送零速度心跳，而不是只发送一次。
- 使用官方慢速步态 `motion_id=303`、真机 ABI 定义的视觉来源 `cmd_source=2`；限幅为前后 0.25 m/s、横移 0.10 m/s、转向 0.40 rad/s。步高采用 0.05 m。
- 不设置步长、机身高度或自定义跳跃高度：这些并非当前公开的稳定真机接口。跳跃只能待现场确认后调用官方预置动作。

## 比赛语音门控

- 设置 `require_voice_start=true` 后，节点启动并不等于允许运动；必须先收到精确的
  配置口令，并同时满足传感器与急停心跳检查。本机真人实测口令为
  `启动`、`恢复`、`暂停`、`终止`，每条口令都要先说一次 `铁蛋铁蛋`。
- `恢复` 只在同样的安全检查通过后恢复门控；`终止` 立即清空当前命令并
  禁止运动输出。
- `暂停` 和头部触摸区双击也会清空当前命令并关闭门控；本机固件直接以
  `protocol/msg/TouchStatus.touch_state=3` 表示双击，同一次手势的重复上报由
  `touch_lockout_sec` 去重。
- 节点在收到 `dog_wakeup=true` 后向 `continue_dialog` 发送 `true`，否则这台狗通常
  只响应唤醒词而不发布 `asr_text`。原厂云端仍可能回答“暂时回答不上”；这不表示
  控制失败，以 `operator_event` 和节点日志为准。
- 头部双击还会触发原厂电量播报；真机已验证它与 `PAUSE_TOUCH` 同时发生，可将
  电量播报视为双击被硬件识别的确认。
- 识别文本入口为 `std_msgs/msg/String`，门控结果
  通过持久化话题 `/mi_dog_real/race_enabled` 发布，供后续真机状态机使用。
- 合法输入还会发布 `/mi_dog_real/operator_event`：`START`、`CONTINUE`、`PAUSE`、
  `PAUSE_TOUCH` 或 `STOP`。机器狗通过官方 `speech_text_play` 服务播放离线
  `play_id=9000` 作为收到命令的确认音；现场已验证离线播放返回 `status=0`。
- 当前机器狗的在线自定义 TTS 返回 `status=1`，因此比赛功能不得依赖联网播报。
- ASR 文本匹配会忽略 ASCII 空白及末尾的中英文逗号、句号、问号和感叹号，仍然
  使用命令白名单，不做危险的模糊子串匹配。
- 语音不会直接生成前进、转弯等速度命令，避免误识别导致动作。
- CyberDog 2 默认唤醒词为 `铁蛋铁蛋`。配置支持通过机器狗的 `wake_word` 话题请求
  更换，但 `publish_wake_word=false` 默认保持原厂唤醒词不变。

本机已验证识别文本话题为
`/mi_desktop_48_b0_2d_7a_fe_40/asr_text`，触摸话题为
`/mi_desktop_48_b0_2d_7a_fe_40/touch_status`；映射保存在
`config/this_robot_sensor_only.yaml`。这些输入目前只控制安全门，不代表赛段断点恢复
和自动趴下已经实现。

## Supervisor 与开机服务

`mi_dog_supervisor_node` 订阅 `/mi_dog_real/operator_event` 和
`/mi_dog_real/stage_complete`，发布以下持久化状态：

- `/mi_dog_real/supervisor/state`：`DOWN_WAITING/RUNNING/PAUSED/EMERGENCY_STOP/FINISHED`；
- `/mi_dog_real/supervisor/current_stage`：当前赛段 `1..6`；
- `/mi_dog_real/supervisor/run_allowed`：只有 `RUNNING` 且所有运行安全门实时满足时为真；
- `/mi_dog_real/supervisor/pause_request` 与 `lie_down_request`。
- `/mi_dog_real/supervisor/safe_to_lie_down` 与 `lie_down_safety_reason`：融合约 48 Hz
  的 `/odom_out`、`motion_status`、约 1 Hz 的 `bms_status` 和约 50 Hz 的四足接触估计，
  要求姿态有效、横滚/俯仰小于 25°、线速度小于 0.03 m/s、角速度小于 0.08 rad/s、
  四足均接触、控制器/BMS 无故障并稳定持续 1.5 秒。任一数据过期即关闭许可。

`mi_dog_state_bridge_node` 只读订阅官方运动模块使用的 LCM `state_estimator`，把
`contactEstimate[4]` 发布为 `/mi_dog_real/foot_contact_estimate`，顺序固定为
`RF, LF, RR, LR`。官方皮肤管理代码以数值大于零判断腿未抬起，本包沿用相同语义，
不再把 `MotionStatus.contact` 位掩码误当作压力传感器。2026-08-09 趴卧充电时实测四路
均为 `0.5`，频率约 50 Hz。

`MotionStatus.motor_error` 不能按“非零即故障”解释：小米官方 `motion_action` 把
`INT32_MIN (-2147483648)` 定义为 `kMotorNormal`，而这台固件在不同状态下也可能上报
`0`。supervisor 同时接受这两个正常值，其他值仍按电机故障闭锁。
官方 `MotionStatus.CHARGING=14` 会继续闭锁姿态动作，但诊断原因单独显示为
`motion_controller_charging_inhibited`，不再误导为笼统控制器故障。

同一桥接节点还将超声、头部左右 8x8 ToF、后部左右 ToF 汇总到
`/mi_dog_real/proximity_summary`，数组顺序为
`[ultrasonic, head_left, head_right, rear_left, rear_right]`，单位米；ToF 使用有效正值
的中位数，无效或不可用通道输出 NaN。趴卧充电现场基线约为
`[0.21, 0.22, 0.21, 0.05, 0.05]`。这些距离目前仅供观测和后续标定，尚未进入趴下
许可；必须在正常站立、前后无遮挡时重新标定，不能按趴卧值设置障碍阈值。

检查点保存在 `/home/mi/mi_dog_ws/state/supervisor_checkpoint.txt`。进程或整机重启后
只恢复赛段编号，状态强制回到 `DOWN_WAITING`，绝不自动恢复运动。暂停期间的赛段完成
消息会被拒绝，只有 `CONTINUE` 后才可推进。

真机已安装并启用 `mi-dog-real-sensor.service`，它通过
`scripts/run_sensor_gate.sh` 启动传感器安全门和 supervisor。该服务固定使用
`enable_motion=false` 的配置；它开机可用，但还不能让机器狗执行六赛段动作。
同一服务启动急停守卫，但不启动 HID 原型；当前没有实体输入生产者，所以它按设计保持
`input_missing/output_asserted=true`。ARM64 隔离测试已通过启动、首次 false、按下/释放、
超时、重连和再次按下/释放八阶段，但这不能替代实体按钮和线缆验收。
`lie_down_request` 目前只是请求话题。安全门已经完成姿态、速度、四足接触、控制器和 BMS 的
只读检查；有线充电时固定输出 `safe_to_lie_down=false` 和 `run_allowed=false`，原因为
`wired_charging_motion_inhibited`。落脚面/边缘与周围空间检查完成前，仍不能连接真实
趴下动作；四足接触只能证明腿没有抬起，不能证明当前位置适合趴下。

2026-08-09 首次站立标定中，起立响应为 `mode=12, progress=100`，全程没有速度指令。
四足接触仍为 `[0.5, 0.5, 0.5, 0.5]`；站立测距约为头部左右
`0.37/0.37 m`、后部左右 `0.20/0.195 m`，前超声在约 `0.34..0.57 m` 间跳变。
因此前超声必须增加时间滤波和异常跳变处理，不能用单帧阈值授权运动。标定结束后
已执行 `mode=7` 趴下并收到 `progress=100`。

同日使用正前方大纸箱完成三档站立定距标定：

| 纸箱标称距离 | 前超声实测 | 头部 ToF 左/右中值 |
| --- | --- | --- |
| 0.8 m | 约 0.50..0.75 m，波动明显 | 约 0.37/0.37 m |
| 0.5 m | 稳定约 0.468 m | 约 0.37/0.37 m |
| 0.3 m | 主要 0.288 m，偶尔 0.296 m | 约 0.37/0.37 m |

因此候选前向策略是：超声 `<=0.35 m` 请求停车、`0.35..0.55 m` 请求减速；普通阈值
至少连续三帧确认，极近距离可单帧触发急停。该策略尚未进入运动链：还需用不同材质、
宽度和左右偏置的障碍物验证漏检/误检，并确认慢速行走时的动态响应。当前头部 ToF 的
64 点整体中值没有随纸箱距离变化，不能作为正前方纸箱距离；结合下方官方安装位姿复算，
这两枚传感器应分析 8x8 地面 ROI，而不是当作正前方测距。

为此桥接节点新增只读话题 `/mi_dog_real/head_ground_roi_summary`，顺序为
`[left_center_p25, left_center_median, right_center_p25, right_center_median,
left_valid_fraction, right_valid_fraction]`。前四项单位米，后两项为中心 4×4 中有效像素
占比；保留前四项顺序以兼容已有诊断工具。
ROI 是每个原始 8×8 阵列的中心 4×4；官方点云脚本使用的 180° 索引反转不会改变这个
对称区域。25 分位用于观察只覆盖部分像素的障碍，中值用于判断覆盖较大的目标。该话题
仍是诊断量，不参与运动许可，必须经过无遮挡和三档纸箱复测后才能选阈值。
趴卧充电、纸箱已移除时，中心 ROI 实测约为左侧 `0.212/0.220 m`、右侧
`0.208/0.216 m`（25 分位/中值）。由于充电状态为 `switch_status=14` 且 BMS 明确
`power_wired_charging=true`，安全门正确取消了后续站立采样。
拔线后曾出现 BMS 已为未充电、但运动控制器仍残留 `CHARGING=14` 的状态，最终通过
正常重启恢复为 `switch_status=0`。supervisor 将这种组合单独报告为
`motion_controller_charging_state_stale`；它与真实充电一样保持闭锁，不会绕过控制器状态。
隔离回放分别注入“新鲜 BMS 未充电 + 运控 14”和“新鲜 BMS 正在充电 + 运控 14”，
两个分支均得到预期原因且安全值保持 false；回放使用独立 `/mi_dog_test/...` 话题，
没有发布任何真实运动命令。

`/mi_dog_real/supervisor/run_allowed` 采用独立的运行许可门：除 supervisor 必须处于
`RUNNING` 外，BMS 必须健康且未充电，里程计必须新鲜、姿态有效并处于 25° 倾角限制
内，运控反馈必须新鲜且无姿态/足端/电机错误。运控 `NORMAL=0` 与正常指令切换期间的
官方 `TRANSITIONING=1` 可保持许可；`ESTOP`、`EDAMP`、抬起、过热、低电、控制错误和
充电等其他状态全部撤销许可。运行门不要求四脚同时接触，因为正常步态会主动抬脚。
隔离回放已验证：`NORMAL`、`TRANSITIONING` 为 true；`ESTOP`、30° 倾斜、里程计过期、
有线充电和运控姿态错误均为 false，各故障恢复后可重新为 true。正式服务重启后保持
`DOWN_WAITING`、`run_allowed=false`、安全诊断 `ready`，全程没有真实运动命令。
START/CONTINUE 还执行事件到达时的边沿检查：若任一运行输入未就绪，事件被拒绝且状态不
进入 `RUNNING`；传感器随后恢复也不会自动启动，操作者必须重新发出“开始/继续”。PAUSE
与 STOP 不受该门限制，始终可以立即撤销运行状态。
隔离状态机测试覆盖了不安全 START、恢复、安全 START、PAUSE、不安全 CONTINUE、再次恢复、
安全 CONTINUE 和 STOP 的完整序列；拒绝、无自动恢复和状态转换结果均符合预期。
运动适配节点现已直接订阅该许可，并以 0.5 秒新鲜度闭锁最终输出。ARM64 编译通过；隔离
`/mi_dog_test/...` 输出测试验证许可缺失、false 和过期均只有停止帧，新鲜 true 才允许隔离
速度帧，重新变为新鲜 true 后可恢复。测试没有连接真实 `motion_servo_cmd`。

依据小米官方点云脚本的原始索引、安装位姿和旋转矩阵复算，头部两枚 ToF 的射线在
机器人坐标系中全部向下约 42°..87°，中心 4×4 约向下 56°..78°。因此它们应作为
前脚附近地面/落差诊断，而不是正前方障碍距离。后续应在站立平地标定左右地面基线，
用距离突然增大、无有效回波或左右显著不一致检测边缘；任何地面异常只能触发停步，
不能单独授权继续前进。正前方障碍继续由超声和激光雷达负责。

2026-08-10 重启并拔除充电线后完成静止站立标定（20 帧）：平地左侧 25 分位/中值
均值为 `0.3631/0.3756 m`，右侧为 `0.3630/0.3768 m`；各通道范围仅约
`0.356..0.382 m`。在前方平铺哑光黑布后，左侧变为 `0.3477/0.3600 m`，右侧
变为 `0.3402/0.3604 m`，没有出现失回波，反而比平地缩短约 1.6 cm。因此颜色或
低反射材料不能等价为落差，不能据此设置距离阈值。话题追加有效像素比例，供后续安全
模拟测试区分“少量有效点”和“完整地面回波”；当前仍只诊断、不触发运动。

只读采集工具可替代 `ros2 topic echo | awk`，避免订阅端提前退出时出现 BrokenPipe：

```bash
ros2 run mi_dog_real ground_tof_capture.py --samples 20 --timeout 15
```

工具只订阅六项 ROI 话题并输出每项均值、最小值、最大值及无效消息数，不导入任何运动
消息或 LCM 控制接口。按官方位姿与站立平地距离复算，中心 ROI 落点约位于机身坐标
`x=0.30..0.41 m`，左侧 `y=0.09..0.19 m`、右侧 `y=-0.19..-0.09 m`。这些区域
靠近前脚，家庭环境不得在狗站立时伸手放置物体。狗脚保持在普通地板上又无法产生比地板
更低的真实目标，因此家中只做静止覆盖/材质诊断；几何落差阈值必须在有防坠保护、人员
可远程更换目标板的正式工装上标定。

真人验收已覆盖 `启动 -> RUNNING`、头部双击 `-> PAUSED`、`恢复 -> RUNNING`；
验收后系统被留在赛段1 `PAUSED`。

## 首次接入（只读探测）

先由赛事方确认 CyberDog 2 的 Type-C 数据模式、官方 USB-C 网卡/转接方案、IP 和登录权限。不要按 CyberDog 1 的 `192.168.55.*` 教程操作，也不要在未确认网络前运行竞赛镜像中的 `scp_to_cyberdog.sh`。

在机器人官方 `cyberdog_ws`/ROS 2 环境中建立独立工作区后构建：

```bash
mkdir -p ~/mi_dog_ws/src
cp -a /path/to/mi_dog_real ~/mi_dog_ws/src/
cd ~/mi_dog_ws
source /opt/ros/<robot_ros_distro>/setup.bash
colcon build --packages-select mi_dog_real
source install/setup.bash
ros2 run mi_dog_real mi_dog_real_node --ros-args --params-file \
  $(ros2 pkg prefix mi_dog_real)/share/mi_dog_real/config/real_robot.yaml
```

先执行 `ros2 topic list`，确认并按实际版本覆盖 `camera_topic`、`lidar_topic`、`pose_topic`。本机固件使用动态命名空间；`config/this_robot_sensor_only.yaml` 记录了 2026-08-05 实测映射。相机当前未激活，因此首次测试不把相机作为安全就绪条件。确认雷达和姿态数据、急停、站立状态及安全场地前，不得开启运动。

当前只批准传感器模式。虽然消息 ABI 已按真机修正，运动模式的 `SERVO_START/DATA/END` 时序仍需零速度现场验证，因此不得设置 `enable_motion=true`。

## 受控运动（当前锁定）

不得在当前版本设置下列值。只有先完成零速度 `SERVO_START/DATA/END` 时序验证、独立急停验证并由现场负责人批准后，才可进入下一阶段：

```text
enable_motion:=true
arm_token:=I_UNDERSTAND_REAL_ROBOT_RISK
```

然后必须由独立急停节点持续向 `/mi_dog_real/emergency_stop` 发布 `false` 心跳，再由高层算法向 `/mi_dog_real/safe_cmd_vel` 发布 `geometry_msgs/Twist`。本包会限幅并将其转换为官方 `protocol/msg/MotionServoCmd`。第一轮只测试急停心跳、零速度、极低速直行和停止 watchdog；不运行赛道自治或跳跃。

> 当前包已在这台 CyberDog 2 的 ARM64/ROS 2 Galactic 环境编译并以传感器模式运行；
> 非零运动模式的命令时序和安全链仍未完成验收，因此不得设置 `enable_motion=true`。
