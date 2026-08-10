# 项目交接总览

更新日期：2026-08-10（Asia/Shanghai）

仓库：`https://github.com/petershe1by/mi_dog`

本文档记录时的代码基线以当前 Git HEAD 和最新部署清单中的 `source_commit` 为准。

## 最终目标

让 CyberDog 2 在 2026 小米杯“荒野寻宝”赛题中，按照官方规则自主完成六个赛段；同时具备
可验证的安全门、独立停止能力、语音/触摸暂停、断点保存和可控恢复。仿真与真机共享任务
逻辑，但传感器和运动适配必须隔离，不能把 x86 Gazebo 镜像直接烧录或复制到机器狗。

## 当前结论

| 范围 | 状态 | 结论 |
| --- | --- | --- |
| Gazebo 六赛段 | 已完成 | 2026-07-30/31 冷启动完整 `0→7`，823.743 秒，无人工运动控制 |
| 真机网络/SSH | 已完成 | 有线网口，主机 `mi@192.168.44.1`，ROS 2 Galactic |
| 单狗离线启动 | 无网线且无 Wi-Fi 通过 | systemd、DDS localhost、唤醒、触摸暂停和提示音均有日志 |
| 真机传感器桥接 | 部分完成 | 里程计、运控、BMS、足端、超声和 ToF 已接入；相机/定位尚未形成比赛感知 |
| 语音/触摸 | 触摸通过、语音闭锁 | 双击产生暂停；原厂动作与自定义 ASR 未隔离，`manage_dialogue=false` |
| Supervisor | 已完成软件门 | 状态、赛段检查点、暂停/停止、运行许可和重启闭锁已验证 |
| 独立急停 | 守卫完成、接口待定 | HID 仅为软件原型；三个 Type-C 的 Host 角色无文档依据，正式服务不启动 HID |
| 真机运动链 | 锁定 | 配置为 `enable_motion=false`；六赛段真机控制器尚未实现和验收 |
| 自动安全趴下 | 未完成 | 只有 `lie_down_request` 和只读许可，没有连接姿态动作 |
| 真机整场比赛 | 未开始 | 感知替换、急停装置和分赛段控制器尚缺 |

2026-08-10 17:31 安全回退部署后的正式服务检查：`mi-dog-real-sensor.service=active`，
`manage_dialogue=false`、`enable_motion=false`，supervisor 为 `DOWN_WAITING`，急停为
`input_missing`；没有比赛运动输出。原厂高阻尼趴下动作已返回完成，最终物理姿态仍需现场确认。

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
- 正式架构确定为狗内置计算：网线只用于调试，比赛时拔除；systemd 不再等待外部网络在线，
  本机 CycloneDDS 固定使用 `lo/localhost`。
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

## 当前阻塞项

1. 急停守卫已完成，但实体接口方案尚未选定；需取得 Type-C 角色文档或赛事方认可的本体方案。
2. 官方 `SERVO_START/DATA/END` 零速度时序尚未形成可重复验收记录。
3. 超声只完成纸箱静态标定，不同材质、宽度、偏置和动态响应未测。
4. 头部 ToF 已确认看地面，但真实几何落差必须在防坠工装上标定。
5. 相机和定位尚未替代 Gazebo 的 `/model_states` 与世界坐标。
6. 六个真机赛段控制器均未逐段实现和验收。
7. 自动停稳、地面判断和安全趴下执行器尚未闭环。
8. 自定义 ASR 尚未与原厂动作路由隔离；当前只能使用已验收的触摸事件，语音控制必须重做。
9. 正式比赛允许的初次启动、暂停、触摸和重试范围仍需裁判确认。

## 接手后的第一组工作

不要直接开启运动。按以下顺序继续：

1. 阅读本目录全部文档，确认机器狗未充电、场地清空且有人持独立急停。
2. 执行 [真机操作手册](REAL_ROBOT_RUNBOOK.md) 的只读检查并生成新部署清单。
3. 检查没有重复节点或隔离测试孤儿；清单工具会在进程数不为 1 时拒绝生成。
4. 在隔离话题复测 supervisor 与最终运动许可门，测试必须回收整个子进程组。
5. 给现有急停守卫接入独立实体按钮/接口并验收断线和延迟；在此之前保持 `enable_motion=false`。
6. 仅做零速度官方时序测试，确认停止帧和 watchdog，不做赛道运动。
7. 建立防坠落差工装，完成地面 ToF 标定和动态超声测试。
8. 再按赛段 1→6 逐个移植感知与控制；每段通过后才进入下一段。

完成标准详见 [路线图](ROADMAP.md) 和 [真机验收矩阵](REAL_ROBOT_ACCEPTANCE.md)。
