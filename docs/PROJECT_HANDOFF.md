# 项目交接总览

更新日期：2026-08-12（Asia/Shanghai）

仓库：`https://github.com/petershe1by/mi_dog`

本文档记录时的代码基线以当前 Git HEAD 和最新部署清单中的 `source_commit` 为准。

## 最终目标

让 CyberDog 2 在 2026 小米杯“荒野寻宝”赛题中，按照官方规则自主完成六个赛段；同时具备
可验证的安全门、电脑暂停/重启、断点保存和可控恢复。仿真与真机共享任务
逻辑，但传感器和运动适配必须隔离，不能把 x86 Gazebo 镜像直接烧录或复制到机器狗。

## 当前结论

| 范围 | 状态 | 结论 |
| --- | --- | --- |
| Gazebo 六赛段 | 已完成 | 2026-07-30/31 冷启动完整 `0→7`，823.743 秒，无人工运动控制 |
| 真机网络/SSH | 已完成 | 有线网口，主机 `mi@192.168.44.1`，ROS 2 Galactic |
| 单狗离线启动 | 无网线且无 Wi-Fi 通过 | systemd、DDS localhost、唤醒、触摸暂停和提示音均有日志 |
| 真机传感器桥接 | 部分完成 | 相机服务实测约 9.46 Hz；scan 约 7.98 Hz、odom 约 44.55 Hz；目标识别/定位尚未形成比赛感知 |
| 比赛操作 | 基础操作完成 | 启动/暂停/STOP/赛段继续和限权一键重启已真机复验；语音保持闭锁 |
| 比赛 UI/SSH | 基础功能通过 | localhost UI、随机令牌、BMS、专用密钥、XTerminal、赛段选择和移动闭锁已真机验证 |
| Supervisor | 已完成软件门 | 状态、赛段检查点、暂停/停止、运行许可和重启闭锁已验证 |
| 电量安全门 | 已完成软件门 | 低于 30% 或有线充电禁止运行；运行中撤权锁存 PAUSED，恢复须 CONTINUE |
| 额外急停 | 比赛不要求 | 旧软件守卫/HID 原型保留但不作为比赛前置条件；软件许可、暂停和 watchdog 仍必须验收 |
| 真机运动链 | 锁定 | 配置为 `enable_motion=false`；六赛段真机控制器尚未实现和验收 |
| 自动安全趴下 | 未完成 | 只有 `lie_down_request` 和只读许可，没有连接姿态动作 |
| 真机整场比赛 | 未开始 | 感知替换、零速度/停止链和分赛段控制器尚缺 |

2026-08-10 17:31 安全回退部署后的正式服务检查：`mi-dog-real-sensor.service=active`，
`manage_dialogue=false`、`enable_motion=false`，supervisor 为 `DOWN_WAITING`，急停为
`input_missing`；没有比赛运动输出。原厂高阻尼趴下动作返回完成后，用户现场确认机器狗已稳定趴下。

2026-08-12 电脑重启流程复验后，正式服务仍 active、`DOWN_WAITING/run_allowed=false`，雷达和
odom 正常，但原厂相机在 command 10 后的 command 9 调用卡住，当前 `/image` 无输出。不要为此
单独重启原厂 `cyberdog_bringup`；已改为跨本服务重启保留已有图像。随后整机安全重启和本服务
重启均完成正向复验，正式图像约 8.786 Hz。

同日拔充电线后完成整机重启：正式相机约 8.786 Hz，服务重启后图像继续有效。新增本地比赛
UI、专用 SSH/XTerminal 入口和安全赛段选择；ARM64 隔离测试、正式 stage 2/4、PAUSE、STOP、
检查点恢复及 `enable_motion=False` 移动拒绝均通过。随后安装只允许重启本项目 unit 的
NOPASSWD 规则；UI API 的 STOP→重启→新 supervisor→`DOWN_WAITING/false` 全链通过。

## 已做的工作

### 仿真

- 解析赛事 PDF/DOCX 并保存在 `extracted/`。
- 基于 `cyberdog_sim:v2026` 构建六赛段 C++ 状态机。
- 完成相机 HSV、激光雷达、Gazebo 物理坐标反馈、足球动态路径和终点趴下。
- 修正第一关漏过第四块石板及跨黄实线问题。
- 增加传感器新鲜度、跌倒恢复、桥面闭环、足球越界持续确认和 DONE 静默终态。
- 完成至少两次有效全程冷跑；当前仓库以 2026-07-30/31、823.743 秒的后续冷跑为最新证据。

### 真机

- 通过物理网口确认主控、运控板、ROS 2 和动态命名空间。
- 在 `/home/mi/mi_dog_ws` 建立独立 ARM64 工作区，没有覆盖原厂运控软件。
- 安装并启用默认无运动的 `mi-dog-real-sensor.service`。
- 正式架构确定为狗内置计算：systemd 不等待外部网络在线，本机 CycloneDDS 固定使用
  `lo/localhost`。电脑可经直连网线执行开始、暂停和重启，但不提供比赛算力或运动命令。
- 接通 ASR、唤醒、触摸双击和离线确认音；避免依赖失败的在线 TTS。
- 完成无外部网线且关闭 Wi-Fi 的冷启动；确认本机链可用，同时发现原厂助手会执行 ASR
  姿态口令，故正式配置关闭 dialogue 管理，语音控制退回未验收状态。
- 实现赛段 supervisor、检查点持久化、暂停/继续/停止事件和重启后 `DOWN_WAITING`。
- 从官方 LCM `state_estimator` 桥接四足接触估计，并汇总超声与五路 ToF。
- 识别 `motor_error=INT32_MIN` 为官方正常哨兵，避免误判故障。
- 区分真实有线充电和运控残留 `CHARGING=14`，两者都保持闭锁。
- 增加头部 ToF 中心 ROI、有效像素比例及只读采集工具。
- 让 `run_allowed` 同时进行实时安全门和 START/CONTINUE 边沿检查。
- 让最终运动适配节点直接消费 `run_allowed`，许可缺失、false 或超过 0.5 秒即闭锁。
- 增加独立急停软件守卫：启动及输入缺失/超过 0.25 秒均持续触发急停；必须完成一次实体
  按下再释放的周期才能解锁，断线恢复后也不能仅靠 `false` 自动解锁。
- 做过 USB HID 常闭输入原型和 FIFO 隔离测试，但这只验证软件逻辑。内部 `lsusb` 不能证明
  三个外部 Type-C 支持 Host/HID；该节点已从正式开机服务撤下，不能按此购买或接线。
- 2026-08-12 只读发现 `image=0`、`pose_filtered=0`，但 scan 约 7.98 Hz、`odom_out` 约
  44.55 Hz；手工调用原厂相机服务后 8 秒取得 76 帧 640x480 `bgr8` 图像并成功关闭。
- 增加相机启动/退出生命周期和 odom 四元数姿态备用输入；ARM64 增量编译通过，隔离节点
  连续报告 `lidar=1 pose=1` 且测试运动话题样本为零。提交 `7e70fca` 正式部署后服务连续
  报告 `camera=1 lidar=1 pose=1; no motion output`，完整只读安全审计通过。
- 按用户“参考铁蛋一”的要求只读盘点 Type-C/USB：内核报告 USB2 port 0 `OTG_CAP`、
  `3550000.xudc` UDC 和 NCM/RNDIS/ACM/mass-storage gadget；当前 extcon 的 USB/USB_HOST 均为
  0、`usb0` 无 carrier。用户随后确认三个外部口定义为 `UDisk`、`charge`、`download`；实际
  插接仍以机身口标识为准。
- 用户确认比赛开始、中途暂停和重启可使用电脑，不需要额外急停或语音控制；新增
  `scripts/competition_control.sh`，只允许结构化事件和服务重启，拒绝人工运动命令。

## 真机部署状态

- 主控工作区：`/home/mi/mi_dog_ws`
- 源码：`/home/mi/mi_dog_ws/src/mi_dog_real`
- 状态文件：`/home/mi/mi_dog_ws/state/supervisor_checkpoint.txt`
- 部署清单：`/home/mi/mi_dog_ws/state/deployment_manifest_*.txt`
- 服务：`mi-dog-real-sensor.service`
- 启动脚本：`/home/mi/mi_dog_ws/scripts/run_sensor_gate.sh`
- 正式配置：`this_robot_sensor_only.yaml`，强制 `enable_motion=false`
- 对应仓库基线：以机器狗最新 `deployment_manifest_*.txt` 的 `source_commit` 为准；清单固定
  四枚 ARM64 二进制、三份配置、启动脚本、清单脚本和 systemd unit 的 SHA256。
- 当前离线启动基础清单：`deployment_manifest_20260810T151435+0800.txt`，schema v2，
  `source_commit=ad6c06a`，文件 SHA256 为
  `612a13929260f2e23b83cfbf915ed1e791f933c52cf2c50049f4bbed2fb7c311`。
- 当前语音安全回退清单：`deployment_manifest_20260810T173628+0800.txt`，`source_commit=37d97eb`，
  SHA256 为 `76c00b474f706f9f37a891b0dec2d3b6bb3d622e067f1c4c27bdc0482d9c2bcc`；实效值包含
  `enable_motion=False`、`manage_dialogue=False`、`DOWN_WAITING`、`run_allowed=false`、
  `emergency_stop=true` 和 `input_missing`。
- 当前相机/odom 只读部署清单：`deployment_manifest_20260812T162605+0800.txt`，
  `source_commit=7e70fca`，SHA256 为
  `e65796f9b9aa2e178be22a522e231af98fcf61625f32e94484d2f2273ec9547e`；实效安全状态保持
  `enable_motion=False`、`manage_dialogue=False`、`DOWN_WAITING`、`run_allowed=false`、
  急停 true 和 `input_missing`。
- 当前电脑控制/重启策略清单：`deployment_manifest_20260812T171314+0800.txt`，
  `source_commit=d7900a7`，SHA256 为
  `8140aa4817ebe9b9438325003ad2be641e622d28a8b66ca18195373f93f92e4a`；服务 active、四节点
  单实例、`enable_motion=False`、`manage_dialogue=False`、`DOWN_WAITING`、
  `run_allowed=false`，并记录 Type-C、离线、电脑操作及“不要求额外急停/语音”的冻结字段。
- 当前 UI/赛段选择部署清单：`deployment_manifest_20260812T182338+0800.txt`，
  `source_commit=356289b`，SHA256 为
  `40dedf8e319f1a18ff1f0fde3a182ac7f12f0b41f85746c41b8eb62b324cf450`；新 supervisor
  二进制 SHA256 为 `52084d5f14450072f2ae39cff98db7ba3409b35dc3b6f4afc066ca455e83d20e`，
  四节点单实例且最终为 `DOWN_WAITING/stage=1/run_allowed=false`。
- 当前最终安全部署清单：`deployment_manifest_20260812T223646+0800.txt`，
  `source_commit=c66efee`，清单 SHA256 为
  `ec7da7af2e03e6da1e7074c7631b8dffac97c8f1fd794a1afee498de85cad80a`；12 个部署文件哈希
  全部通过。实效值为 `enable_motion=False`、`min_battery_soc=30`、`DOWN_WAITING`、
  `run_allowed=false`，且只允许精确重启本项目 unit 的限权 sudo 生效。

## 当前阻塞项

可执行勾选项统一维护在 [待完成真机测试清单](PENDING_REAL_ROBOT_TESTS.md)，以下为摘要：

1. 官方 `SERVO_START/DATA/END` 已完成 ARM64 隔离话题验收，但尚未在防护工装上连接真实
   运控话题验证物理停止、暂停/重启和通信中断。
2. 超声只完成纸箱静态标定，不同材质、宽度、偏置和动态响应未测。
3. 头部 ToF 已确认看地面，但真实几何落差必须在防坠工装上标定。
4. 相机和定位尚未替代 Gazebo 的 `/model_states` 与世界坐标。
5. 六个真机赛段控制器均未逐段实现和验收。
6. 自动停稳、地面判断和安全趴下执行器尚未闭环。
7. 暂停/重启后的复位位置、计分和当前赛段重试边界仍需技术会议记录。

## 接手后的第一组工作

不要直接开启运动。按以下顺序继续：

1. 阅读本目录全部文档，确认机器狗未充电、场地清空且电脑操作员知道暂停/重启流程。
2. 执行 [真机操作手册](REAL_ROBOT_RUNBOOK.md) 的只读检查并生成新部署清单。
3. 检查没有重复节点或隔离测试孤儿；清单工具会在进程数不为 1 时拒绝生成。
4. 在隔离话题复测 supervisor 与最终运动许可门，测试必须回收整个子进程组。
5. 在 `enable_motion=false` 下复验电脑 `START/PAUSE/restart`，确认每次暂停和重启都撤销许可。
6. 仅在防护工装上做零速度官方时序测试，确认停止帧、watchdog 和链路中断，不做赛道运动。
7. 建立防坠落差工装，完成地面 ToF 标定和动态超声测试。
8. 再按赛段 1→6 逐个移植感知与控制；每段通过后才进入下一段。

完成标准详见 [路线图](ROADMAP.md) 和 [真机验收矩阵](REAL_ROBOT_ACCEPTANCE.md)。
