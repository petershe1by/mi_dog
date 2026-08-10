# 真机测试数据汇总

更新日期：2026-08-10。单位默认使用 SI。这里汇总当前对话和仓库中保留下来的全部有效数据；
没有保存原始 rosbag/CSV 的项目会标明证据等级，不能用于高精度控制器标定。

## 证据等级

- A：话题/程序输出和明确测试条件均有记录。
- B：现场话题读数或服务响应有记录，但没有保存完整原始序列。
- C：操作者观察，缺少同步遥测，只能指导下一次测试。

## 设备和软件

| 项目 | 数据 | 等级 |
| --- | --- | --- |
| 主控地址 | `192.168.44.1` | A |
| 电脑地址 | `192.168.44.100/24` | A |
| 运控板地址 | `192.168.44.233` | A |
| 主控 | ARM64 Tegra，Ubuntu 18.04，ROS 2 Galactic | A |
| 运控固件 | `1.2.0.3` | A |
| ROS namespace | `/mi_desktop_48_b0_2d_7a_fe_40` | A |
| 协议包 | `protocol 1.0.0` | A |
| 主控剩余空间 | 初始约 2.7 MB；清理 pip 下载缓存后约 336 MB；安装后约 332 MB | B |
| 真机工作区 | `/home/mi/mi_dog_ws`，安装占用约 7 MB | B |
| 最后代码基线 | `c19ef2b` | A |
| 最近一次记录电量 | 100%（未保存连续放电曲线） | B |

2026-08-10 13:55 的最终有效部署清单：

| 文件 | SHA256 |
| --- | --- |
| `mi_dog_real_node` | `afbe203793102d601daf14d38fa1fc30c7cf9c772c6990d5d3311a9832a7c184` |
| `mi_dog_supervisor_node` | `78dfc8a9c023af92e87632e212fba186d89147a11b1171798cf807c99acbd922` |
| `mi_dog_state_bridge_node` | `7b51445b54817013496806c6125a5fb72a685ae9de981c4fb25559ebb87c54ed` |
| `this_robot_sensor_only.yaml` | `e270a9953fa2d905d6844e90c2b1cd0dc70ff04a85d085536623d1a2d8f7e04c` |
| `supervisor.yaml` | `aba4cf5dd3c531fdf4d4823bceeaf55ffae210e4f09b7f07566d65f226b2cc57` |
| `run_sensor_gate.sh` | `df263d878364957793dbd3f48de6f0421c20f8ad52df77c99fafc174c5cf5a74` |
| `capture_deployment_manifest.sh` | `da5a6f805669150e30e5fea32cdf7510fba9f95a1af1499965e7dd6fa6f1c9b1` |
| systemd unit | `e9191a108dd8b88d16df9c14ddf7474c4a8c1e530b5e3dcb49573adcc0eea97f` |

同一清单记录 `service=active`、`enable_motion=False`、supervisor `DOWN_WAITING`、
`run_allowed=false`。两份配置哈希与仓库一致。

## 数据频率和安全参数

| 数据/参数 | 数值 | 来源/等级 |
| --- | --- | --- |
| `/odom_out` | 约 48 Hz | 现场 `topic hz`，B |
| BMS | 约 1 Hz | 现场观察，B |
| `contactEstimate[4]` | 约 50 Hz | LCM 桥，B |
| 运动适配传感器新鲜度 | 1.0 s | 配置，A |
| supervisor 状态输入新鲜度 | 0.5 s | 配置，A |
| 急停心跳超时 | 0.50 s | 配置，A |
| 急停原始输入守卫超时 | 0.25 s | `estop_guard.yaml`，A |
| 急停守卫输出频率 | 20 Hz | `estop_guard.yaml`，A |
| 速度指令超时 | 0.30 s | 配置，A |
| supervisor 许可超时 | 0.50 s | 配置，A |
| 停止心跳周期 | 0.20 s | 配置，A |
| 触摸重复锁定 | 1.5 s | 配置及复测，A |
| 趴下稳定等待 | 1.5 s | supervisor 配置，A |
| 趴下最大倾角 | 25° | supervisor 配置，A |
| 趴下最大线速度 | 0.03 m/s | supervisor 配置，A |
| 趴下最大角速度 | 0.08 rad/s | supervisor 配置，A |
| 运动适配最大倾角 | 0.60 rad | 运动节点配置，A |
| 前后速度限幅 | 0.25 m/s | 运动节点配置，A |
| 横移速度限幅 | 0.10 m/s | 运动节点配置，A |
| 转向限幅 | 0.40 rad/s | 运动节点配置，A |
| 步高 | 0.05 m | 运动节点配置，A |

以上运动参数存在于代码，但当前正式配置 `enable_motion=false`，不代表非零运动已经批准。

## 足端与姿态动作

| 条件 | 结果 | 等级 |
| --- | --- | --- |
| 趴卧、接有线电源 | RF/LF/RR/LR 均为 `0.5` | B |
| 静止站立 | 四路仍为 `[0.5, 0.5, 0.5, 0.5]` | B |
| 官方恢复站立 | `mode=12, progress=100` | B |
| 官方趴下 | `mode=7, progress=100` | B |
| `motor_error` 正常语义 | 官方哨兵 `-2147483648` 或固件值 `0` | A（官方源码+现场） |
| 正常运控开关 | `NORMAL=0`；正常切换 `TRANSITIONING=1` | A |
| 充电运控状态 | `CHARGING=14`，必须闭锁 | A |

## 趴卧距离基线

条件：机器狗趴卧、接有线电源、前后无遮挡。`proximity_summary` 顺序为
`[前超声, 头左, 头右, 后左, 后右]`。

| 通道 | 距离 | 等级 |
| --- | --- | --- |
| 前超声 | 约 0.21 m | B |
| 头部左 ToF 全阵列中值 | 约 0.22 m | B |
| 头部右 ToF 全阵列中值 | 约 0.21 m | B |
| 后部左 ToF | 约 0.05 m | B |
| 后部右 ToF | 约 0.05 m | B |

同条件下头部中心 4×4 ROI：

| 侧别 | p25 | 中值 | 等级 |
| --- | --- | --- | --- |
| 左 | 0.212 m | 0.220 m | B |
| 右 | 0.208 m | 0.216 m | B |

## 静止站立无遮挡基线

日期：2026-08-09/10。站立过程没有速度指令。

| 通道 | 结果 | 等级 |
| --- | --- | --- |
| 头部左右全阵列中值 | 约 0.37/0.37 m | B |
| 后部左右 ToF | 约 0.20/0.195 m | B |
| 前超声 | 约 0.34..0.57 m，跳变明显 | B |

2026-08-10 头部中心 ROI，20 帧：

| 地面 | 左 p25/中值均值 | 右 p25/中值均值 | 观测范围 | 有效回波 |
| --- | --- | --- | --- | --- |
| 普通平地 | 0.3631/0.3756 m | 0.3630/0.3768 m | 约 0.356..0.382 m | 有 |
| 哑光黑布 | 0.3477/0.3600 m | 0.3402/0.3604 m | 未留存逐帧范围 | 有 |

黑布相对平地约缩短 1.6 cm，没有造成失回波，因此不能模拟落差，也不能据此设自动阈值。

## 头部 ToF 几何

| 项目 | 结果 | 等级 |
| --- | --- | --- |
| 全部射线向下角 | 约 42°..87° | A（官方位姿复算） |
| 中心 4×4 向下角 | 约 56°..78° | A |
| 中心 ROI 前向落点 x | 约 0.30..0.41 m | A（几何+站立距离） |
| 左侧落点 y | 约 0.09..0.19 m | A |
| 右侧落点 y | 约 -0.19..-0.09 m | A |

结论：头部 ToF 用于前脚附近地面/落差诊断，不是正前方障碍传感器。

## 正前方纸箱静态标定

条件：机器狗静止站立，大纸箱置于正前方；每档结束后趴下并收到
`mode=7, progress=100`。

| 标称纸箱距离 | 前超声 | 头部 ToF 全阵列中值 | 等级 |
| --- | --- | --- | --- |
| 0.8 m | 约 0.50..0.75 m，波动 | 约 0.37/0.37 m | B |
| 0.5 m | 稳定约 0.468 m | 约 0.37/0.37 m | B |
| 0.3 m | 主要 0.288 m，偶尔 0.296 m | 约 0.37/0.37 m | B |

候选规则仅供后续测试：`<=0.35 m` 停车，`0.35..0.55 m` 减速，普通阈值连续三帧确认。
它尚未接入运动链，也未覆盖不同材质、宽度、横向偏置和动态工况。

## 充电状态测试

| 条件 | BMS/运控 | 诊断 | 结果 |
| --- | --- | --- | --- |
| 真实有线充电 | BMS wired=true，运控 14 | `motion_controller_charging_inhibited` | 闭锁 |
| 拔线后残留 | BMS wired=false，运控仍为 14 | `motion_controller_charging_state_stale` | 闭锁 |
| 正常重启后 | BMS 未充电，`switch_status=0` | `ready`（其余输入健康时） | 只读恢复 |

隔离回放覆盖真实充电与残留充电，两种情况下安全值都保持 false。

## 语音、声音和触摸

| 项目 | 结果 | 等级 |
| --- | --- | --- |
| 唤醒词 | `铁蛋铁蛋` 有回应 | C/B |
| 实测短口令 | `启动/恢复/暂停/终止` | A（配置+真人验收） |
| 在线自定义 TTS | `status=1` | B |
| 离线提示音 | `play_id=9000`，`status=0` | B |
| 双击状态 | `touch_state=3` | A |
| 双击副作用 | 同时触发原厂电量播报 | C/B |
| 单击 | 未观察到可用 `touch_status` | C |

## Supervisor 和许可隔离测试

START/CONTINUE 状态机序列全部通过：

- 不安全 START 被拒绝，保持 `DOWN_WAITING`；
- 输入恢复后不会自动 START；
- 安全 START 进入 `RUNNING` 且许可为真；
- PAUSE 进入 `PAUSED` 且许可为假；
- 不安全 CONTINUE 被拒绝；
- 输入恢复后不会自动 CONTINUE；
- 安全 CONTINUE 恢复 `RUNNING`；
- STOP 进入 `EMERGENCY_STOP`。

实时 `run_allowed` 回放：`NORMAL`、`TRANSITIONING` 可为真；ESTOP、30° 倾斜、里程计
过期、有线充电和运控姿态错误均为假，恢复后可重新为真。

最终运动节点 ARM64 隔离输出测试：许可 missing、false、stale 均只产生停止帧；fresh true
允许 `/mi_dog_test/...` 隔离 servo data；fresh true 恢复后再次放行。未连接真实运动话题。

## 急停守卫 ARM64 隔离测试

日期：2026-08-10。输入、输出和状态全部重映射到 `/mi_dog_test/...`，未连接真实运动话题。
测试脚本用独立进程组启动节点，并在结束时回收整组进程；结束后未发现同名孤儿。

| 阶段 | 样本 true/false | 结果 |
| --- | --- | --- |
| 启动无输入 | 5/0 | 触发 |
| 首次只发 false | 11/0 | 保持触发，不能自动解锁 |
| 第一次按下 true | 7/0 | 触发 |
| 第一次释放 false | 0/11 | 解锁 |
| 输入停止至过期 | 8/0 | 重新触发 |
| 重连后只发 false | 11/0 | 保持触发 |
| 第二次按下 true | 7/0 | 触发 |
| 第二次释放 false | 0/11 | 再次解锁 |

八项断言全部通过。正式服务重启后守卫为唯一急停发布者，主程序为唯一订阅者；由于没有实体
输入，日志为 `input_missing; output_asserted=1`，`enable_motion=False`。这只证明软件失效
安全语义，不包含实体按钮电气故障、线缆断开和真实停车延迟。

最终部署清单为机器狗上的
`/home/mi/mi_dog_ws/state/deployment_manifest_20260810T141742+0800.txt`：
`source_commit=8d42be0`，清单 SHA256 为
`907a4211a2abb6773bd4fb185ba0d75a575d27b791bb5937532f25f475560228`。清单实时记录
`service_active=active`、`enable_motion=False`、`DOWN_WAITING`、`run_allowed=false`、
`emergency_stop=true` 和 `estop_guard_status=input_missing`。

## USB HID 常闭输入 ARM64 隔离测试

日期：2026-08-10。以 Linux FIFO 代替实体 event 设备，仅在显式测试参数下允许非字符设备；
正式 YAML 固定关闭该参数。输出重映射至 `/mi_dog_test/hid/output`，未连接真实运动话题。

| 阶段 | 样本 true/false | 结果 |
| --- | --- | --- |
| 打开但触点开路 | 29/0 | 触发 |
| NC 闭合、按钮正常 | 0/24 | 原始输入健康 |
| 按下、NC 断开 | 24/0 | 触发 |
| 人工释放、NC 闭合 | 0/24 | 原始输入健康 |
| USB 断开 | 21/0 | 触发 |
| USB 重连但仍开路 | 19/0 | 保持触发 |
| 重连后 NC 闭合 | 0/24 | 原始输入健康 |

七项断言全部通过，测试进程组完整回收。正式服务已启动 HID 节点；占位设备路径不存在时
状态为 `open_failed:2`，原始输入持续为 true，守卫状态为 `input_asserted`，运动仍关闭。
尚未测试真实 HID 的 `EVIOCGKEY/EVIOCGRAB`、实体触点抖动与电气故障。
额外负向测试尝试让非字符测试设备发布到正式话题，进程以返回码 1 拒绝启动并报告
`test devices may publish only under /mi_dog_test/`。

当前 v2 部署清单为
`/home/mi/mi_dog_ws/state/deployment_manifest_20260810T143522+0800.txt`，
`source_commit=bc8fc89`，清单 SHA256 为
`b91d3cba13c2e1f84a45a48da3152bb0acd5f39e15dbb4b9c1feeb319a76ce2b`。它记录五个唯一
进程、`DOWN_WAITING/run_allowed=false`、`enable_motion=False`、`emergency_stop=true`、
HID `open_failed:2` 和守卫 `input_asserted`，并哈希 HID 脚本与配置。

更正：上述清单准确记录了当时运行状态，但“狗侧 HID 可接实物”的部署前提随后被撤回。
`lsusb` 只能看到内部 Hub/RealSense，不能映射三个外部 Type-C。HID 节点已从正式服务移除；
其 7 阶段结果只保留为软件原型证据，不是端口或实体急停验收。

纠错后的当前清单为 `deployment_manifest_20260810T144512+0800.txt`，
`source_commit=885e94b`，SHA256 为
`563b5e9eb649990185e7763fe08d11a803c73ce160def05b7b0839ff040e4d4a`。清单明确记录
`estop_hid_input_active=false`、`estop_hid_connection=unverified_no_external_port_mapping`、
四个正式节点、`input_missing`、急停 true 和 `enable_motion=False`。

移除 `network-online.target` 后生成的新清单为
`deployment_manifest_20260810T151435+0800.txt`，`source_commit=ad6c06a`，SHA256
`612a13929260f2e23b83cfbf915ed1e791f933c52cf2c50049f4bbed2fb7c311`。服务重启后 enabled、
active，`Wants` 为空，`After` 只包含 `network.target` 等本机启动目标；安全状态保持不变。
这不是拔网线冷启动证据，现场测试仍待完成。

## 早期人工控制运动观察

这些试验发生在安全场地，由用户现场确认，但没有保存同步里程计、轨迹文件或控制版本，
因此等级为 C，不得作为控制精度验收：

| 指令/试验 | 操作者观察 |
| --- | --- |
| 约 0.3 m 短距离 | 位移可完成；小修正不明显 |
| 前进 0.8 m、后退 0.4 m | 距离基本正确，但轨迹有斜偏 |
| 直接倒车 | 距离正确，方向偏斜 |
| 前进与倒车组合 | 两条轨迹向相反方向斜，形成 X 状交叉 |
| 原地转身约 180° | 已执行；未保存角度遥测 |
| 转身后前进约 0.5 m | 已执行；未保存轨迹遥测 |
| 原地踏步步高 0.02/0.1 m | 曾按各 10 秒请求测试；没有保存关节/足端高度数据 |

下一次必须记录 odom/IMU/命令时间序列和地面轨迹，分别拟合前进、倒车的横向与航向误差，
不能继续只靠目测修正常数。

## 尚未取得的数据

- 相机比赛目标数据集和识别精度；
- 激光雷达赛道定位误差；
- 独立实体急停电气链、延迟及断线停车距离；
- 超声多材质/宽度/偏置/动态统计；
- 防坠工装上的真实落差 ToF 分布；
- 非零运动许可撤销后的真实停车距离；
- 六赛段真机耗时和成功率；
- 完整 rosbag、视频与同步版本清单。

这些缺项属于路线图任务，不允许用仿真数据或主观观察填补。
