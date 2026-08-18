# 架构与文件地图

## 两套运行环境

```text
赛事规则/场景
   ├─ Gazebo: cyberdog_autonomy + LCM + /model_states
   └─ 真机: mi_dog_real + 官方 ROS 2/LCM + supervisor 安全许可
```

两者不能直接互换：仿真依赖 x86_64 Docker、Gazebo 世界坐标和模拟实体；真机是 ARM64，
必须用真实相机、雷达、里程计、BMS、运控状态和官方运动接口。

## 真机数据流

```text
电脑 SSH 结构化事件 / 可选头部双击
      │
      v
mi_dog_real_node ──operator_event──> mi_dog_supervisor_node
      │                                  │
      │                                  ├─ state/current_stage/checkpoint
      │                                  └─ run_allowed (实时且 fail-closed)
      │                                              │
比赛控制器/维护 UI ─────────────── safe_cmd_vel ───────────────┤
      │                                              v
      └──────── 最终运动适配门 <── 传感器/急停 ── motion_servo_cmd

官方 LCM state_estimator ──> mi_dog_state_bridge_node
                                  ├─ foot_contact_estimate
                                  ├─ proximity_summary
                                  └─ head_ground_roi_summary
```

当前维护/比赛配置使用 `enable_motion=true`，但 Supervisor 默认 `DOWN_WAITING/run_allowed=false`；
比赛控制器还要求显式 `course_calibrated=true`。没有活动 Servo 会话时适配器完全静默。赛事不要求
额外实体急停，因此 maintenance/competition launch 不启动兼容 E-stop guard；sensor-only 回滚
launch 仍保留它。

## 顶层文件

| 路径 | 作用 |
| --- | --- |
| `README.md` | 项目首页、构建入口和最新仿真结果 |
| `TESTING.md` | 仿真冷跑与物理验收矩阵 |
| `REAL_ROBOT_DEPLOYMENT.md` | 真机部署事实和历史检查点 |
| `RACE_RECOVERY_DESIGN.md` | 比赛暂停、断点和恢复设计；含未实现部分 |
| `Dockerfile` | 基于官方仿真镜像构建方案镜像 |
| `.gitignore` | 排除容器产物、临时文件和本地状态 |

## 仿真代码

| 路径 | 作用 |
| --- | --- |
| `cyberdog_autonomy/src/race_autonomy.cpp` | 六赛段主状态机、感知、控制和恢复逻辑 |
| `cyberdog_autonomy/include/.../gamepad_lcmt.hpp` | 仿真运动 LCM 消息定义 |
| `cyberdog_autonomy/include/.../simulator_lcmt.hpp` | 仿真状态 LCM 消息定义 |
| `overlay/gazebo.xacro` | 相机和 180° 雷达覆盖配置 |
| `audio/*.wav` | 五条赛事规定的离线播报 |
| `urdf/` | 从真机导出的仿真 URDF 参考，不是部署包 |

## 真机 ROS 2 包

| 路径 | 作用 |
| --- | --- |
| `mi_dog_real/src/mi_dog_real_node.cpp` | 语音/触摸入口、传感器门、速度限幅、最终运动许可 |
| `mi_dog_real/src/mi_dog_supervisor_node.cpp` | 比赛状态、赛段检查点、暂停/停止和安全许可 |
| `mi_dog_real/src/mi_dog_state_bridge_node.cpp` | LCM 足端和距离传感器到 ROS 2 的只读桥接 |
| `mi_dog_real/src/mi_dog_estop_guard_node.cpp` | 独立急停输入的失效安全心跳守卫；断线、过期和启动阶段均触发急停 |
| `mi_dog_real/scripts/estop_hid_input.py` | USB HID 输入原型；仅软件隔离验证，外部 Type-C 角色未确认，正式服务不启动 |
| `mi_dog_real/scripts/estop_hid_isolated_test.py` | 用 FIFO 验证原型逻辑，不证明狗的外部接口可接 HID |
| `mi_dog_real/scripts/ground_tof_capture.py` | 只读采集头部地面 ROI 的统计工具 |
| `mi_dog_real/scripts/estop_guard_isolated_test.py` | 在隔离话题验证急停按下、释放、断线和重新解锁序列 |
| `mi_dog_real/config/this_robot_sensor_only.yaml` | 失能回滚配置和实测 topic 映射 |
| `mi_dog_real/config/this_robot_competition.yaml` | maintenance/competition 共用的 motion-enabled 最终适配配置 |
| `mi_dog_real/config/race_controller.yaml` | 真机比赛骨架参数；默认课程未标定闭锁 |
| `mi_dog_real/config/real_robot.yaml` | 通用保守模板，默认仍关闭运动 |
| `mi_dog_real/config/supervisor.yaml` | supervisor 话题、阈值、新鲜度和检查点路径 |
| `mi_dog_real/config/estop_guard.yaml` | 急停原始输入、输出、状态、0.25 秒超时及 20 Hz 心跳 |
| `mi_dog_real/config/estop_hid.yaml` | 专用 `/dev/input/by-id`、KEY_F12、常闭极性及 50 Hz 心跳 |
| `mi_dog_real/launch/sensor_only.launch.py` | 失能回滚 launch |
| `mi_dog_real/launch/maintenance.launch.py` | UI 维护栈；无自主比赛控制器 |
| `mi_dog_real/launch/competition.launch.py` | 比赛栈；包含课程标定闭锁的控制器 |
| `mi_dog_real/launch/real_robot.launch.py` | 通用 launch；不能视作已批准运动配置 |

## 脚本和服务

| 路径 | 作用 |
| --- | --- |
| `scripts/build_image.sh` | 构建 Gazebo 方案镜像 |
| `scripts/run_race.sh` | 删除旧容器并执行正式冷启动回归 |
| `scripts/smoke_test.sh` | 检查仿真基础设施，不替代全程验收 |
| `scripts/start_sim.sh` | 容器内启动 Gazebo、控制器和自治节点 |
| `scripts/competition_control.sh` | 电脑端比赛操作入口；只发送白名单事件或重启服务，不发送运动命令 |
| `scripts/competition_ui.py` + `ui/` | 仅本机监听的比赛 Web UI；默认比赛模式后端禁用人工运动，写操作互斥、STOP 请求绕过互斥锁、一次性视频令牌和按需 RGB 流 |
| `scripts/competition_ui_offline_test.py` | 不连接狗的 HTTP/并发回归；覆盖比赛模式闭锁、写冲突、STOP 请求并发派发、超时进程组回收和视频安全 |
| `scripts/robot_jog.sh` | 0.25 秒低速维护脉冲；非零指令额外要求显式维护环境门、运动总开关和 supervisor 许可 |
| `scripts/robot_posture.sh` | 原厂 `111/101` 维护姿态入口；要求显式维护环境门并重新读取 supervisor、BMS 和运控状态 |
| `scripts/robot_camera_stream.py` | 经 SSH 临时送入狗主控运行的只读 ROS Image→JPEG 转发器；不部署到狗上 |
| `scripts/connect_robot.sh` | 使用专用 SSH 密钥连接狗主控，适合作为 XTerminal 外的维护后备 |
| `scripts/setup_robot_ssh_key.sh` | 一次性创建和安装 UI 专用 Ed25519 公钥，不保存密码 |
| `scripts/run_sensor_gate.sh` | 真机 ROS 环境和 CycloneDDS 环境设置 |
| `scripts/capture_deployment_manifest.sh` | 拒绝重复节点并记录真机进程、参数和 SHA256 |
| `systemd/mi-dog-real-sensor.service` | 当前开机自启维护服务；切换比赛模式必须单独批准 |

## 关键真机接口

| 话题 | 类型 | 生产者 | 用途/时限 |
| --- | --- | --- | --- |
| `/mi_dog_real/operator_event` | `std_msgs/String` | 电脑控制脚本或 `mi_dog_real_node` | `START/CONTINUE/PAUSE/PAUSE_TOUCH/STOP` |
| `/mi_dog_real/supervisor/state` | `std_msgs/String` | supervisor | 持久化比赛状态 |
| `/mi_dog_real/supervisor/current_stage` | `std_msgs/Int32` | supervisor | 当前赛段 1..6 |
| `/mi_dog_real/supervisor/select_stage` | `std_msgs/Int32` | 电脑控制脚本/UI | 仅等待/暂停态接受 1..6，持久化但不自动继续 |
| `/mi_dog_real/supervisor/run_allowed` | `std_msgs/Bool` | supervisor | 最终运动许可，运动节点要求 0.5 秒内新鲜 |
| `/mi_dog_real/supervisor/safe_to_lie_down` | `std_msgs/Bool` | supervisor | 只读姿态许可，不会自动执行趴下 |
| `/mi_dog_real/supervisor/lie_down_safety_reason` | `std_msgs/String` | supervisor | 机器可读的闭锁原因 |
| `/mi_dog_real/foot_contact_estimate` | `Float32MultiArray` | 状态桥 | RF/LF/RR/LR，约 50 Hz |
| `/mi_dog_real/proximity_summary` | `Float32MultiArray` | 状态桥 | 超声、头左/右、后左/右，单位米 |
| `/mi_dog_real/head_ground_roi_summary` | `Float32MultiArray` | 状态桥 | 左右 p25/中值/有效比例，只读诊断 |
| `/mi_dog_real/safe_cmd_vel` | `geometry_msgs/Twist` | 未来高层控制器 | 300 ms 超时；当前无正式生产者 |
| `/mi_dog_real/emergency_stop_input` | `std_msgs/Bool` | 可选兼容实体接口 | 赛事不要求；当前无生产者，守卫保持急停 true |
| `/mi_dog_real/emergency_stop_hid/status` | `std_msgs/String` | 可选 HID 原型 | 正式服务不启动，不能据此选择狗的 Type-C 口 |
| `/mi_dog_real/emergency_stop` | `std_msgs/Bool` | 急停守卫 | 20 Hz；启动、断线、超时或按下均为 `true` |
| `/mi_dog_real/emergency_stop_guard/status` | `std_msgs/String` | 急停守卫 | `input_missing/input_stale/pressed/released_armed` 等诊断 |

官方动态命名空间和完整 topic 映射以
`mi_dog_real/config/this_robot_sensor_only.yaml` 为唯一配置事实来源。

## 状态持久化

supervisor 检查点只保存赛段编号。进程或整机重启时读取编号，但始终回到
`DOWN_WAITING`，不会自动恢复 `RUNNING`。状态文件不是比赛成绩数据库，不能保存感知地图、
球位置或官方剩余时间。
