# CyberDog 2026 小米杯自主仿真方案

本仓库用于存放小米杯四足机器人“荒野寻宝”赛题的代码、配置、技术文档与实验记录。

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
- 真机接入、Type-C 数据网络和实际 topic 映射必须先经赛事方确认。具体安全流程见 [`mi_dog_real/README.md`](mi_dog_real/README.md)。

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

2026-07-30/31（Asia/Shanghai）在最终镜像 `sha256:3880dc86250ca0eb1c051c57b77161a691e0a37190c133278ca3f6170b02558d`、冷容器 `8d50cc1d76ba...` 上完成无跳段、无人工运动控制的全赛道回归：

- 状态转换完整 `0→1→2→3→4→5→6→7`；从 `stage 0 -> 1` 到正常 DONE 为 823.743 秒，比 895 秒内部保护线提前 71.257 秒。
- 四块石板实体门控为 `(1.120,-0.037)`、`(1.625,0.169)`、`(2.123,0.065)`、`(2.627,-0.016)`；随后从合法右侧开口 `x=2.921` 进入第二关。
- 橙球按列 `2、3、4、1` 去重命中；曲道与隧道全部目标完成，足球2在 `(2.122,11.464)` 物理入门。
- 独木桥确认全足登桥和四足越线；桥后低姿态由通用恢复闭环自动站稳。
- 终点足球动态对准安全南向通道，在 `(2.200,12.877)` 持续越界确认；四足入圈后直接 pure-damper，11.099 秒内完成物理趴伏。
- DONE 后持续稳定在 `(2.324,13.092,z=0.054)`，不再发送行走或恢复指令。
- `smoke_test.sh`、全部 shell 脚本 `bash -n`、镜像内 `cyberdog_autonomy` 编译及 `git diff --check` 均通过。

本轮还增加了状态新鲜度门控、持续低高度判跌、恢复后的物理站立判定、桥面闭环与落地重试、动态足球路径、边界保持确认、DONE 静默终态等保护。真机安全适配见 [`mi_dog_real/README.md`](mi_dog_real/README.md)；在拿到赛事方确认的 CyberDog 2 消息 ABI、topic、网络和端口前，不应把 x86 仿真镜像或未核验协议直接部署到机器人。
