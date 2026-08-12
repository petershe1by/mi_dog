# CyberDog 2026 小米杯自主仿真方案

本仓库用于存放小米杯四足机器人“荒野寻宝”赛题的代码、配置、技术文档与实验记录。

## 从这里开始

- [`docs/README.md`](docs/README.md)：完整文档导航。
- [`docs/PROJECT_HANDOFF.md`](docs/PROJECT_HANDOFF.md)：目标、当前状态、已完成工作和接手步骤。
- [`docs/REAL_ROBOT_RUNBOOK.md`](docs/REAL_ROBOT_RUNBOOK.md)：比赛与日常真机操作手册。
- [`docs/COMPETITION_DAY_CHECKLIST.md`](docs/COMPETITION_DAY_CHECKLIST.md)：比赛日流程和规则边界。
- [`docs/REAL_ROBOT_TEST_DATA.md`](docs/REAL_ROBOT_TEST_DATA.md)：真机全部保留测量数据。
- [`docs/ARCHITECTURE_AND_FILE_MAP.md`](docs/ARCHITECTURE_AND_FILE_MAP.md)：架构、接口和文件位置。
- [`docs/ROADMAP.md`](docs/ROADMAP.md)：下一步与最终完成条件。

当前边界：Gazebo 六赛段已完成；真机只读接入、电脑操作和 supervisor 安全门已完成基础
验收，但真机六赛段感知与控制尚未实现。正式真机配置保持 `enable_motion=false`。

## 比赛资料

`extracted/` 保留赛事题目、规则、Gazebo 与赛题文档的文本解析结果，作为仿真和真机适配的本地参考。

本目录提供基于官方 `cyberdog_sim:v2026` 的宿主持久化全自主方案，不依赖对临时容器的手工修改。

## 架构

- `overlay/gazebo.xacro`：官方 180° 激光雷达和 640×480、15 Hz 前向 RGB 相机。
- `cyberdog_autonomy`：ROS 2/C++ 状态机；相机 HSV 与雷达感知，LCM `simulator_state` 闭环定位，`gamepad_lcmt` 控制运动。
- `/model_states`：对两个足球提供物理闭环反馈；足球进门和越界均以实际坐标判定。
- 状态机覆盖石径、橙球阵、曲道、深隧、独木桥、终点足球与圈内物理趴下。
- `audio/`：五条赛题规定中文播报的离线 WAV。
- 内部保护线为 895 秒，早于官方 900 秒上限。

## 真机代码（与仿真隔离）

- `mi_dog_real/`：面向 CyberDog 2 官方 ROS 2 工作区的传感器与安全运动适配包；默认只读相机、雷达和 IMU，默认不发布运动。
- 真机包使用官方 `motion_servo_cmd` 的慢速步态接口，并将步高限定为开发者手册明确开放的 `0.05 m`；没有修改步长、机身高度或跳跃高度。
- 三个 Type-C 已确认为 `UDisk`、`charge`、`download`；比赛程序运行在狗内置主控，不依赖
  网线或 Wi-Fi。电脑仅用于开始、暂停和重启。具体流程见 [`mi_dog_real/README.md`](mi_dog_real/README.md)。
- 本地比赛 UI、赛段选择和 XTerminal/SSH 配置见
  [`docs/COMPETITION_UI.md`](docs/COMPETITION_UI.md)。

## 构建与运行

```bash
cd "/mnt/e/Competitions during college/mi_dog/solution"
./scripts/build_image.sh
./scripts/run_race.sh
docker logs -f mi-dog-race
./scripts/smoke_test.sh
```

每次正式回归都由 `run_race.sh` 删除并重建 `mi-dog-race`，不要用 `/reset_world` 代替冷启动。

## 最终验证状态

2026-07-30/31（Asia/Shanghai）在当前最新完整回归镜像 `sha256:3880dc86250ca0eb1c051c57b77161a691e0a37190c133278ca3f6170b02558d`、冷容器 `8d50cc1d76ba...` 上完成无跳段、无人工运动控制的全赛道回归。2026-07-26 的 800.277 秒纠错冷跑是较早的有效证据；两次测试关系见 [`docs/WORKLOG.md`](docs/WORKLOG.md)。

- 状态转换完整 `0→1→2→3→4→5→6→7`；从 `stage 0 -> 1` 到正常 DONE 为 823.743 秒，比 895 秒内部保护线提前 71.257 秒。
- 四块石板实体门控为 `(1.120,-0.037)`、`(1.625,0.169)`、`(2.123,0.065)`、`(2.627,-0.016)`；随后从合法右侧开口 `x=2.921` 进入第二关。
- 橙球按列 `2、3、4、1` 去重命中；曲道与隧道全部目标完成，足球2在 `(2.122,11.464)` 物理入门。
- 独木桥确认全足登桥和四足越线；桥后低姿态由通用恢复闭环自动站稳。
- 终点足球动态对准安全南向通道，在 `(2.200,12.877)` 持续越界确认；四足入圈后直接 pure-damper，11.099 秒内完成物理趴伏。
- DONE 后持续稳定在 `(2.324,13.092,z=0.054)`，不再发送行走或恢复指令。
- `smoke_test.sh`、全部 shell 脚本 `bash -n`、镜像内 `cyberdog_autonomy` 编译及 `git diff --check` 均通过。

本轮还增加了状态新鲜度门控、持续低高度判跌、恢复后的物理站立判定、桥面闭环与落地重试、动态足球路径、边界保持确认、DONE 静默终态等保护。真机安全适配见 [`mi_dog_real/README.md`](mi_dog_real/README.md)；在核验 CyberDog 2 消息 ABI、topic 和官方运动协议前，不应把 x86 仿真镜像或未核验协议直接部署到机器人。
