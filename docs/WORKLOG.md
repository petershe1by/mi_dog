# 工作记录与关键决策

本文档用于让接手者理解“为什么代码变成现在这样”。详细代码差异以 Git 历史为准。

## 2026-07-23 至 2026-07-26：仿真方案建立和纠错

- 建立仓库、Docker 构建、仿真状态机、相机/雷达和音频资源。
- 完成六赛段首次全程。
- 用户回归发现第一关旧路线漏过第四块石板并跨黄实线；旧镜像 `011fe01b...` 的完成证据撤销。
- 按官方 STL 重做四块石板物理门和右侧合法开口。
- 修正冷跑镜像 `7287d179...`、容器 `ca95097df251...` 在 800.277 秒完成 `0→7`。

## 2026-07-30/31：后续仿真强化

- 合并赛事资料、真机适配备份和主动 URDF。
- 增加传感器新鲜度、持续低高度判跌、恢复物理站立确认、桥面闭环、动态足球路线、越界
  持续确认和 DONE 静默终态。
- 当前仓库记录的后续正式冷跑镜像为 `3880dc...`，容器 `8d50cc1d76ba...`，823.743 秒。
- 该后续冷跑取代 07-26 作为当前 README 的最新完整回归；07-26 仍保留为纠错来源和历史证据。

## 2026-08-05：真机只读接入

- 通过物理网口确认主控 `192.168.44.1`、运控板 `192.168.44.233`、ROS 2 Galactic 和
  动态 namespace。
- 备份原厂运控和既有工作区；明确禁止运行会删除原厂目录的 `scp_to_cyberdog.sh`。
- 主控空间仅约 2.7 MB，经用户批准只删除 pip 下载缓存，恢复约 336 MB。
- 在 `/home/mi/mi_dog_ws` 独立构建 `mi_dog_real`，保持 `enable_motion=false`。

## 2026-08-08/09：语音、触摸和恢复状态机

- 多轮真人尝试后确认：唤醒后必须主动打开 `continue_dialog` 才能稳定取得 `asr_text`。
- 原厂会回答“暂时回答不上来/还在学习”，因此控制成功改以结构化事件和日志判断。
- 实测配置改为精确短口令 `启动/恢复/暂停/终止`。
- 发现头部双击是固件已识别的 `touch_state=3`，一次手势可能重复上报，增加 1.5 秒去重。
- 将声音确认改成离线 `play_id=9000`；在线 TTS `status=1` 不再作为依赖。
- 提交 `c490b2c`：supervisor、断点、语音/触摸和无运动开机服务。

## 2026-08-09：足端、距离和控制器语义

- `20926f5`：桥接官方 LCM 四足接触估计与距离传感器摘要。
- 现场趴卧/站立均观察到四路 0.5、约 50 Hz。
- 首次站立无行走标定完成，并正常趴下。
- 发现 `motor_error=-2147483648` 是官方 `kMotorNormal`，不是故障；`fe5a7d8` 修正判断。
- 完成 0.8/0.5/0.3 m 大纸箱超声静态标定；`70a40d4` 记录结果。
- `360f21e`：新增头部 ToF 中心 ROI，随后由官方位姿确认它看地面而非正前方。

## 2026-08-10：地面 ToF、充电语义和最终许可链

- `0cbc8d7`：明确头部 ToF 地面用途和安全边界。
- `fdb5e8b`：增加有效像素比例，观察部分/无回波。
- `eb5e159`：区分真实充电和拔线后运控残留 `CHARGING=14`；两者都闭锁。
- `f782922`：增加只读 `ground_tof_capture.py`。
- 完成 20 帧站立平地与黑布测试；黑布没有失回波，不能替代真实落差。
- `9eac3b8`：`run_allowed` 同时检查 supervisor、odom、运控和 BMS，新鲜度 fail-closed。
- `7ccbe74`：START/CONTINUE 到达瞬间必须安全；恢复后不自动启动。
- `c19ef2b`：最终运动节点直接订阅 `run_allowed`，missing/false/stale 均停止。
- ARM64 构建及五项隔离输出测试通过；正式服务回到 `DOWN_WAITING/run_allowed=false`。

## 关键设计决策

1. 不把 Gazebo Docker 镜像部署到狗上；使用独立 ARM64 ROS 2 包。
2. 不覆盖原厂 manager/robot-software；所有代码安装到用户工作区。
3. 安全许可必须持续新鲜，不能只在启动时检查一次。
4. START/CONTINUE 不安全时拒绝，后续恢复不自动开跑。
5. PAUSE/STOP 不受启动门限制，始终可以撤销许可。
6. 四脚接触只说明腿未抬起，不说明地面安全。
7. 头部 ToF 只能提供地面异常的停止证据，不能单独授权前进。
8. 充电和运控残留充电态都 fail-closed。
9. 语音只产生白名单事件，不直接产生方向或速度。
10. 无原始遥测的人工观察不升级为精确标定结论。

## 2026-08-10 13:47 至 13:55：部署清单与测试孤儿故障

- 新增只读部署清单工具，记录 commit、平台、服务、实时参数、状态和关键文件 SHA256。
- 首次采集异常显示 `enable_motion=True`；进程审计发现三次隔离运动测试和三次 supervisor
  回放留下 PPID=1 的孤儿进程。
- 三个隔离运动节点只发布 `/mi_dog_test/motion_output`，该话题订阅数为 0，没有连接真实
  `motion_servo_cmd`；但它们与正式节点同名，污染了 ROS 参数查询。
- 精确对六个已核实测试 PID 发送 SIGTERM，没有终止正式 systemd 进程。ROS graph 清理后
  只剩一个 `mi_dog_real`、一个 supervisor 和一个 bridge。
- 正式参数复核为 `enable_motion=False`、`require_supervisor_run_allowed=True`；正式状态为
  `DOWN_WAITING/run_allowed=false`。
- 工具随后改为要求三类节点进程数各等于 1，并通过 rclpy 读取持久化状态；存在重复进程、
  空参数或话题超时时不生成清单。
- 使用只执行 `sleep` 的伪同名进程验证重复保护：工具准确报告 2 个节点进程、返回失败，且
  没有写出无效清单；伪进程随后按 PID 回收。
- 13:55 最终清单保存于机器狗 `state/deployment_manifest_20260810T135515+0800.txt`，并把
  清单工具自身纳入哈希；前两份分别重命名为 `invalid-duplicate-nodes` 和
  `invalid-empty-topics`，保留故障证据。

## 2026-08-10 14:00 后：独立急停软件守卫

- 审计原厂 `cyberdog_emergency_stop`：它根据点云、里程计和激光雷达自动发布停止运动指令，
  属于障碍物保护，不是由现场人员掌握的独立实体急停，不能据此关闭 M4 缺项。
- 新增 `mi_dog_estop_guard_node`，把未来实体接口的原始 Bool 转为持续急停心跳。启动、输入
  缺失、超过 0.25 秒、收到按下都 fail-closed；只有观察到一次按下后再释放才解锁。
- ARM64 构建通过。隔离测试覆盖启动无输入、首次 false、第一次按下/释放、过期、重连 false、
  第二次按下/释放八个阶段，全部通过；测试结束后没有同名孤儿进程。
- 正式 `sensor_only.launch.py` 已启动第四个节点。重启后服务 active，守卫为急停话题唯一发布
  者，主程序为唯一订阅者，日志为 `input_missing; output_asserted=1`，运动参数仍为 false。
- 代码提交 `8d42be0` 后生成只读清单
  `deployment_manifest_20260810T141742+0800.txt`；清单 SHA256 为
  `907a4211a2abb6773bd4fb185ba0d75a575d27b791bb5937532f25f475560228`。
- 仍未完成：选择独立实体按钮/有线接口，编写或配置原始输入生产者，验证断线、电气故障、
  按钮保持、人工复位和真实停车延迟。完成前不批准非零运动。

## 2026-08-10 14:20 后：常闭 USB HID 实体输入链

- 只读盘点确认主控有 USB 2.0/3.0 Hub，`mi` 属于 `input` 组；当前没有外接 HID、串口或
  `/dev/ttyACM*`/`ttyUSB*`，因此没有冒充实物测试。
- 选定专用 USB HID 键盘编码器加常闭自锁蘑菇按钮的单通道方案。正常释放时 NC 闭合并维持
  KEY_F12 down；按钮按下、触点线断开或 USB 拔出都必须触发急停。
- 新增 `estop_hid_input.py`、`estop_hid.yaml` 和 FIFO 隔离测试。生产模式要求字符设备、读取
  `EVIOCGKEY` 初始状态并 `EVIOCGRAB` 独占；占位路径不存在时持续 fail-closed。
- ARM64 最终构建通过。完整测试取得 7/7：开路 29/0、NC 正常 0/24、按钮按下 24/0、
  释放 0/24、USB 断开 21/0、重连开路 19/0、重连正常 0/24；均为 true/false 样本数。
- 防误配负向测试确认：非字符测试设备若输出到正式命名空间会以返回码 1 拒绝启动；生产
  模式同时强制稳定 `/dev/input/by-id/` 路径。
- 正式无运动服务现有五个节点。设备未接入时 HID 状态 `open_failed:2`、原始输入 true、守卫
  `input_asserted`、`enable_motion=False`，没有运动输出。
- 提交 `bc8fc89` 后生成 v2 清单 `deployment_manifest_20260810T143522+0800.txt`，SHA256
  `b91d3cba13c2e1f84a45a48da3152bb0acd5f39e15dbb4b9c1feeb319a76ce2b`。
- 仍缺实体编码器和蘑菇按钮，因此真实 HID ioctl、接点抖动、导线断开与停车延迟未验收；该
  单通道方案也不是认证安全继电器。

## 2026-08-10：撤回未经证实的狗侧 USB 结论

- 用户指出机器狗外部只有一个网口和三个 Type-C，没有 USB-A。复核比赛 PDF/DOCX 和项目
  恢复资料后确认：没有任何文件给出三个 Type-C 的 Host/Device/充电角色映射。
- 此前从内部 `lsusb` 的 Hub 推断“可直接接狗侧 USB HID”属于无依据外推。内部 Hub 和
  RealSense 不等于外部 Type-C 支持 Host；明确撤回购买和插接建议。
- HID 节点的 FIFO 测试数据仍能证明软件原型逻辑，但不能证明物理端口、电气链或实物可用。
  正式服务移除 HID 节点，急停守卫恢复 `input_missing` 且持续 true。
- 电脑侧按钮只能用于家中调试，不符合本项目单狗离线比赛架构。比赛方案必须取得官方端口
  映射并在狗本体实现，或使用赛事方明确认可的本体/官方停止装置。
- 纠错提交 `885e94b` 部署后只剩四个正式节点；清单
  `deployment_manifest_20260810T144512+0800.txt` 的 SHA256 为
  `563b5e9eb649990185e7763fe08d11a803c73ce160def05b7b0839ff040e4d4a`。

## 2026-08-10：确定单狗离线比赛架构

- 规则原文要求全程自主，程序启动后不得再次触碰电脑、再次启动或远程人为操控；补充规则
  允许语音/触摸“继续比赛”，但没有明确允许初次语音 START，需裁判确认。
- 正式方案不使用笔记本算力：网线只用于赛前部署和赛后取日志，比赛时拔除，所有进程和
  感知/决策均运行在狗主控。
- 只读确认 systemd 服务已 enabled；CycloneDDS 域 42 固定 `lo`、禁止 multicast、peer 为
  localhost，因此本机 ROS 图不依赖 eth0。
- 发现 unit 仍 `Wants/After=network-online.target`，改为仅 `After=network.target`，避免无网线
  时等待外部网络。仍需用户配合完成一次真正拔网线冷启动，不能仅凭配置标为通过。
- 当前是 sensor-only、`enable_motion=false`；开机自启不等于真机六赛段已实现。
- 提交 `ad6c06a` 部署后生成 `deployment_manifest_20260810T151435+0800.txt`，SHA256
  `612a13929260f2e23b83cfbf915ed1e791f933c52cf2c50049f4bbed2fb7c311`；服务 active、四个正式
  节点、`DOWN_WAITING`、急停 true、无运动输出。
- 用户现场确认外部 RJ45 在开机、等待、唤醒和暂停期间均已拔除，完成后才插回。系统
  `16:29:29` 启动、服务 `16:29:36` active、ROS 节点 `16:29:51` 出现，语音暂停在
  `16:33:42`，离线提示音完成且持续无运动输出。`eth0` carrier 不能映射外部插头状态，因
  主控/运控板内部网络拓扑未有文档；本轮按物理确认加日志判定单狗无外部网线启动通过。

## 2026-08-10：无网线、无 Wi-Fi 冷启动与语音安全回退

- 管理员关闭 Wi-Fi 后确认 `wlan0=unavailable`，用户关机、拔除外部 RJ45 并冷启动；重连检查
  时 Wi-Fi 仍 disabled。服务 `17:19:18` 启动，四节点 `17:19:32` 出现，随后本机唤醒、
  头部双击 `PAUSE_TOUCH` 和离线确认音均成功，正式节点持续 `enable_motion=False`。
- ASR 同时发布 `站起来`；本程序白名单拒绝，但原厂助手执行恢复站立 `motion_id=111`。
  这说明 `continue_dialog` 不是隔离的自定义识别通道，当前语音方案不能用于比赛安全控制。
- 安全门确认 `safe_to_lie_down=true/reason=ready` 后，按官方映射调用高阻尼趴下动作
  `motion_id=101`，返回 `result=true, code=0`，最终 `progress=100`。Wi-Fi 随后恢复；服务
  active、supervisor `PAUSED`、急停 `input_missing`、运动总开关 false。
- 正式配置改为 `manage_dialogue=false`。下一步先设计不进入原厂动作路由的本机关键词识别，
  在隔离/架空工装验证后，才可重新启用任何语音比赛事件。
- C++ 默认值和通用真机配置也改为 false；ARM64 构建约 1 分 41 秒成功。服务 `17:31:45`
  重启后实测 `manage_dialogue=False`、`enable_motion=False`、supervisor `DOWN_WAITING`、急停
  `input_missing`，四节点 active 且持续无运动输出。
- 清单脚本新增 `manage_dialogue` 实效参数。sensor-only launch 中两项 readiness=false 是有意
  允许只读观测的覆盖；运动总开关 false 时节点在这些门之前直接返回，不发布运动命令。
- 最终清单 `deployment_manifest_20260810T173628+0800.txt` 绑定 `37d97eb`，SHA256
  `76c00b474f706f9f37a891b0dec2d3b6bb3d622e067f1c4c27bdc0482d9c2bcc`；其中
  `manage_dialogue=False`、`enable_motion=False`、急停 true、状态 `DOWN_WAITING`。
- 用户最终现场确认机器狗已稳定趴下，与 `motion_id=101, progress=100` 的运控反馈一致。

## 2026-08-12：共享副本安全同步与只读审计工具

- 以 `/mnt/e/Competitions during college/mi_dog/solution` 的干净 Git 工作树为权威来源，发现
  共享目录 `real_robot_deploy` 仍是语音安全回退前的副本，两个 YAML 和 C++ 默认值均为
  `manage_dialogue=true`。
- 将 `mi_dog_real_node.cpp`、两份配置和包 README 精确同步到权威版本；复核除缓存目录外
  `real_robot_deploy/mi_dog_real` 与权威目录已无差异，`enable_motion=false`、
  `manage_dialogue=false`。
- 新增电脑端 `scripts/robot_read_only_audit.sh`。脚本只允许 SSH 公钥认证，不发布 ROS 消息、
  不重启服务、不写机器狗，并检查服务、四节点单实例、HID 未运行、运动/语音闭锁、
  supervisor 和急停状态。
- 本地 `bash -n`、远端嵌入脚本语法、帮助和非法参数负向测试通过；机器狗
  `192.168.44.1` 可达。随后通过交互式 SSH 执行只读审计：服务 enabled/active，四个正式
  节点各一个，HID 原型为零，`enable_motion=False`、`manage_dialogue=False`、
  `run_allowed=false`、急停 true、守卫 `input_missing`。
- 首轮审计只接受 `DOWN_WAITING`，因此对现场 `PAUSED` 报失败。启动日志证明 supervisor 于
  `15:33:48` 正常进入 `DOWN_WAITING`，随后在 `15:36:30` 和 `15:36:35` 收到两次
  `PAUSE_TOUCH` 并保持 `PAUSED`；全程持续记录 `no motion output`。脚本据此修正为接受
  `DOWN_WAITING`、`PAUSED`、`EMERGENCY_STOP` 三种闭锁状态，仍拒绝 `RUNNING` 和未知状态。
- 新增 `ORGANIZER_CONFIRMATION.md`，记录首次 START、暂停/恢复、实体急停、三个 Type-C、
  离线架构和恢复规则的正式询问与答复门。
- 本轮没有构建、部署或移动机器狗；真机部署 commit 未改变。下一步是重跑修正后的只读审计，
  然后取得官方答复并确定实体急停方案。

### 同日后续：相机与 odom 姿态适配候选

- 修正只读审计对 `PAUSED` 的误报后重跑通过：服务 enabled/active、四节点单实例、HID 为零、
  运动/语音闭锁、`run_allowed=false`、急停 true、`input_missing` 全部成立。
- SensorDataQoS 六秒计数：`scan=48`（约 7.98 Hz）、`odom_out=268`（约 44.55 Hz）；
  `/image`、`pose_filtered`、`dog_pose` 和 `tracking_pose_transformed` 均为零。
- 原厂相机服务 command 9 返回 `result=0/code=0`；8 秒取得 76 帧 640x480 `bgr8` 图像
  （约 9.46 Hz），command 10 随后成功关闭相机。
- 候选启动脚本增加相机启停生命周期；运动节点增加 `/odom_out` 四元数备用输入，避免无样本的
  `pose_filtered` 永久阻塞姿态新鲜度。无效四元数不会刷新新鲜度或覆盖最近的有效输入。
- 机器狗工作区构建前创建五文件 SHA256 备份。备份根目录中的 `CMakeLists.txt` 首次被 colcon
  识别为重复包，未开始编译；重命名为 `.backup` 后 ARM64 增量编译 1 分 53 秒通过。
- 隔离节点使用测试运动话题，连续报告 `camera=0 lidar=1 pose=1`；9 秒运动消息样本为 0，
  `ODOM_ADAPTER_ISOLATED_TEST=PASS`。
- 提交 `7e70fca` 后重启正式无运动服务。相机服务自动启用 640x480、10 fps；节点稳定报告
  `camera=1 lidar=1 pose=1; no motion output`。六秒复测得到 image 49 帧、scan 40 帧、
  odom 221 帧；完整只读审计为 `READ_ONLY_AUDIT=PASS`，机器狗未移动。
- 新部署清单 `deployment_manifest_20260812T162605+0800.txt` 绑定 `7e70fca`，SHA256 为
  `e65796f9b9aa2e178be22a522e231af98fcf61625f32e94484d2f2273ec9547e`；状态为四节点单实例、
  `enable_motion=False`、`manage_dialogue=False`、`DOWN_WAITING`、急停 true、`input_missing`。
- 用户确认正式架构允许无网线、无 Wi-Fi、狗内置主控独立运行；场地可能存在网络，但程序
  不依赖。
- 按铁蛋一思路完成无插接只读盘点：Tegra 内核报告 USB2 port 0 `OTG_CAP`，存在
  `3550000.xudc`，configfs 配置 NCM/RNDIS/ACM/mass-storage gadget；当前 USB/USB_HOST 状态
  均为 0，`usb0` 无 carrier。该证据只能确认 OTG/device 能力，不能把它映射到三个外部口，
  因此没有恢复 HID 正式服务或尝试插接。

### 同日后续：赛事操作边界与三个 Type-C 定义冻结

- 用户确认三个 Type-C 分别为 `UDisk`、`charge`、`download`，参考铁蛋一并以机身标识为准。
- 用户确认比赛开始、中途暂停和重启可以使用电脑；电脑不作为比赛算力节点，程序仍须在
  无网线、无 Wi-Fi 时由狗内置主控独立运行。
- 用户确认不需要额外实体急停或语音控制。旧急停守卫/HID 和语音入口保留为闭锁的兼容实现，
  不再列为赛事前置条件；软件暂停、重启撤权、watchdog 和链路中断停止仍是运动前验收项。
- 新增 `scripts/competition_control.sh`：只允许 `status/start/continue/pause/stop/restart`，通过
  狗本机 ROS 2 发布结构化事件或重启服务，不提供方向、速度、步态、姿态和原始运控参数。
- 正式服务保持 `enable_motion=False`、`manage_dialogue=False` 时完成电脑控制基础复验：初始
  `status=DOWN_WAITING/stage=1/run_allowed=false`；`START` 已送达但因
  `wired_charging_motion_inhibited` 被 fail-closed 拒绝；`PAUSE` 得到 `PAUSED/false`；重启后
  恢复 `DOWN_WAITING/false`，全程无运动输出。
- 本次重启暴露原厂相机服务生命周期问题：command 10 后，后续 command 9 可发现服务并创建
  RealSense 进程，但服务调用不返回且 `/image` 不再输出；雷达和 odom 继续工作且运动闭锁。
  为避免比赛中服务重启反复停启原厂相机，启动脚本改为优先复用已有 `/image`，不再在本服务
  退出时关闭相机；只有图像未激活时才请求一次 command 9，并在响应超时后复查实际图像。
  当前相机服务已卡住，正向恢复需下次整机安全重启后验证，不重启原厂 `cyberdog_bringup`。
- `competition_control.sh restart` 最初只检查 service active，随后发现会在 supervisor 尚未创建时
  过早返回；又修正了 `pgrep` 自匹配问题。最终版本记录重启前 supervisor PID，并等待新的、
  路径锚定的 supervisor 进程，现场约 30 秒后报告 `supervisor_ready=new_process`。
- 最终状态复测：`service_active=active`、`DOWN_WAITING`、赛段 1、`run_allowed=false`、
  `wired_charging_motion_inhibited`。机器狗正在充电，因此 START 的拒绝是预期安全结果；未产生
  运动输出。当前相机仍需整机安全重启恢复，雷达和 odom 继续可用。
- 部署清单 `deployment_manifest_20260812T171314+0800.txt` 绑定 `d7900a7`，SHA256 为
  `8140aa4817ebe9b9438325003ad2be641e622d28a8b66ca18195373f93f92e4a`。清单确认四节点单实例、
  `enable_motion=False`、`manage_dialogue=False`、`DOWN_WAITING/run_allowed=false`，并写入
  `UDisk,charge,download`、无网络依赖、电脑白名单操作以及不要求额外急停/语音控制。

## 2026-08-12 后续：本地比赛 UI、SSH 与赛段选择

- 用户拔除充电线后只读确认 `enable_motion=False`、`manage_dialogue=False`、安全原因 `ready`，
  随后完成安全整机重启。使用正确的正式图像话题 8.081 秒取得 71 帧（约 8.786 Hz）；再重启
  本项目服务后仍持续 `camera=1 lidar=1 pose=1; no motion output`，相机生命周期恢复项关闭。
- 新增 localhost Web UI：每次启动随机令牌、命令/参数白名单、状态卡片、START/PAUSE/STOP、
  服务重启、赛段选择继续、六向低速调试键和操作日志。浏览器不保存 SSH 密码。
- 新增专用 Ed25519 SSH 与 `connect_robot.sh`。机器狗原 `.ssh` 为 root 所有且无
  `authorized_keys`，先用 sudo 修正为 `mi:mi` 的 0700/0600，再成功安装公钥；批处理 status
  通过。XTerminal 可直接连接 `mi@192.168.44.1:22`。
- supervisor 增加独立 `select_stage`：只在 `DOWN_WAITING/PAUSED` 接受 1..6，持久化检查点但
  不自动运行。ARM64 构建 1 分 40 秒通过；正式 stage 4 与 UI stage 2 流程通过。
- 新增可重复隔离测试，10 项覆盖等待/暂停选段、非法值、STOP态拒绝、持久化和重启闭锁，
  全部通过并完整回收测试进程。
- 正式服务始终 `enable_motion=False`。前进调试脉冲返回码3并报告
  `jog_refused=enable_motion_False`；零速度 STOP 可发送。UI STOP 锁存
  `EMERGENCY_STOP/run_allowed=false`，最终重启并恢复 stage 1 `DOWN_WAITING/false`。
- UI 批处理重启改用 `sudo -n`：当前没有限权免密规则时立即失败且服务不变，不会等待密码。
  仅限该 unit 的 NOPASSWD 配置因属于持久权限扩大，等待用户明确批准。
- 最终只读审计 `READ_ONLY_AUDIT=PASS`。部署清单
  `deployment_manifest_20260812T182338+0800.txt` 绑定 `356289b`，SHA256 为
  `40dedf8e319f1a18ff1f0fde3a182ac7f12f0b41f85746c41b8eb62b324cf450`；新 supervisor
  二进制 SHA256 为 `52084d5f14450072f2ae39cff98db7ba3409b35dc3b6f4afc066ca455e83d20e`。
- 最终 UI 回归覆盖 HTML/CSS/JS、health、真实 status、非零移动拒绝、未授权重启快速失败、
  错误令牌 403 和非法 action 400；最终真机保持 stage 1 `DOWN_WAITING/run_allowed=false`。

## 2026-08-12 后续：限权一键重启、BMS UI 与隔离伺服时序

- 用户批准持久化但严格限定的 sudo 规则。安装
  `/etc/sudoers.d/mi-dog-competition-ui`，内容仅允许用户 `mi` 免密执行
  `/bin/systemctl restart mi-dog-real-sensor.service`；临时文件和安装文件均经 `visudo -cf`
  通过，最终权限为 `root:root 0440`，`sudo -n -l` 未显示其他 NOPASSWD 命令。
- 重启控制在 systemd 操作前先发送 supervisor `STOP`。真实 UI API 验收先得到
  `EMERGENCY_STOP/run_allowed=false`，随后报告 `supervisor_ready=new_process`，最后只读状态为
  `DOWN_WAITING/stage=1/run_allowed=false`。正式服务全程 `enable_motion=False` 且有线充电闭锁。
- 状态 API 订阅真实 `protocol/msg/BmsStatus`，UI 新增电量、有线充电和电池温度。验收样本为
  19%、约 21.1 V、37°C、健康度 99、`power_wired_charging=true/power_normal=true`。
- 官方真机接口明确 `MotionServoCmd.SERVO_START=0`、`SERVO_DATA=1`、`SERVO_END=2`。运动适配器
  改为每次新会话先发送零速度 START，再发送 DATA；命令超时或 supervisor 撤权发送 END，且
  撤权时清除旧命令，重新放行不能恢复旧速度。
- ARM64 增量构建用时 2 分 3 秒并通过。新增 `/mi_dog_test/servo_sequence/...` 隔离验收，三轮
  均得到 START→DATA；命令超时和撤权均得到 END；重新放行但无新命令时只有 END；11 项断言
  全部通过。测试从未连接真实 `motion_servo_cmd`，不等于物理运控验收。
- 启动脚本的相机保活检查从不存在样本的 `/image` 别名修正为本机实际动态话题
  `/mi_desktop_48_b0_2d_7a_fe_40/image`。进一步确认真机 Galactic 不支持原脚本使用的
  `ros2 topic echo --once`；最终改为 Python `SensorDataQoS` 单帧探针并保留 12 秒外部超时，
  避免服务重启时误调用相机启动服务。
- 部署清单不读取 `root:root 0440` 的 sudoers 文件，也不放宽其权限；改为通过普通用户可用的
  `sudo -n -l` 记录精确 unit 重启授权是否生效。清单输出同时改为临时文件完整写入后原子
  改名，失败时自动清理，避免残留看似有效的部分清单。
- 仍未执行任何真实非零运动：本轮电量仅约 19% 且正在有线充电。后续必须在电量充足、拔除
  充电线并具备防护工装时，先做真实话题零速度/停止链，再做低速移动。
- 后续审计发现原 supervisor 没有独立最低 SOC 门，拔线后低电量可能只凭 `power_normal` 通过。
  新增 `min_battery_soc=30`，并让运行中任一安全输入撤销直接锁存 PAUSED；输入恢复不会自启。
  UI 从 supervisor 参数服务读取实际下限，在低电或充电时禁用 START、指定赛段继续和非零移动。
- 新增 `/mi_dog_test/power_gate/...` 隔离测试。ARM64 增量构建 1 分 43 秒通过；11 项覆盖 18%
  START 拒绝、80% 启动、运行中 20% 暂停、恢复不自启、显式 CONTINUE 和充电暂停，全部通过。
  初版探针三次在创建测试进程前因 rclpy 只读属性命名冲突退出；改用 `_subscriptions` 后通过，
  锚定检查确认没有隔离 supervisor 残留。

## 2026-08-12 推送前：待测事项集中备注

- 新增 `PENDING_REAL_ROBOT_TESTS.md`，将后续工作明确分为“已实现只缺物理验收”“感知测试未
  完成”“功能尚未实现”和“赛事流程待确认”，并使用可勾选任务防止隔离测试被误记为真机完成。
- 冻结本轮最终部署证据：提交 `c66efee`，清单
  `deployment_manifest_20260812T223646+0800.txt`，SHA256
  `ec7da7af2e03e6da1e7074c7631b8dffac97c8f1fd794a1afee498de85cad80a`。
- 当前最后实测电量 17%，BMS 虽报告有线充电但电量未上升。正式服务保持
  `enable_motion=False`、`min_battery_soc=30`、`DOWN_WAITING/run_allowed=false`；充电恢复前
  不执行物理运动测试。

## 2026-08-12 后续：UI 姿态控制与远程头部 RGB

- UI 新增“起立”和“安全趴下”，后端只接受白名单动作并使用真机已观察成功的原厂上层动作号
  `111/101`。脚本在真正调用服务前重新读取 supervisor、BMS、充电、运控错误和最低 SOC；仅在
  `DOWN_WAITING/PAUSED`、`run_allowed=false` 时允许，趴下另需 `safe_to_lie_down=true` 与
  `reason=ready`。前端还有一次现场安全确认。
- 新增按需头部 RGB。浏览器访问 localhost 上的令牌化 MJPEG 端点；UI 后端只建立一条 SSH
  会话，把只读 Python 转码程序经标准输入临时送入狗主控，不写入真机文件。转码限制为
  640 像素宽、JPEG 质量 72、最高 10 fps，UI 用 5 秒滑动窗口显示实际接收帧率。
- 真实相机源已知为 640×480、10 fps 配置，已留档话题测量约 8.14–9.46 fps；新增 SSH-MJPEG
  链路尚未在本轮断开/关机后的狗上实测，因此没有把历史源话题数据冒充远程 UI 帧率。
- 离线检查覆盖 shell、11 个 Python 源文件、JavaScript、HTML 元素引用与 diff 格式；假相机
  HTTP 回归通过页面/指标、错误视频令牌 403、非法姿态 400、MJPEG 帧和活动计数。测试不连接狗、
  不执行姿态动作。最终仍需在电量至少 50%、拔除充电线和有防护的条件下验收两个姿态按钮，
  并连续测量真实视频 fps/延迟/断线回收。
- UI/代码工作和狗内置主控自治均不要求电脑持续连接；只有查看视频、人工按钮和最终实机验收
  需要狗开机且 SSH 可达。

## 2026-08-13：UI 复盘修正

- 修正正式操作边界：UI 默认进入比赛模式，人工移动和姿态不再只靠前端变灰，后端也固定返回
  403。只有本机启动参数 `--maintenance-controls` 能显式开启维护接口；网页不能自行切换，正式
  比赛文档明确禁止携带该参数。UI 启动模式还会覆盖子进程环境；非零 jog 和姿态脚本自身也要求
  `MI_DOG_MAINTENANCE_CONTROLS=1`，避免绕过 UI 直接误调用，零速 STOP 始终保留。
- 所有非紧急机器人写操作共用非阻塞互斥锁；并发请求返回 HTTP 409。结构化 STOP 和维护零速
  STOP 不等待该锁，可立即派发请求；这不被解释为已经证明能取消任意进行中的原厂姿态动作。
  状态读取和视频不占用运动写锁。命令在独立本机进程组中运行，超时按 TERM→3 秒→KILL 回收
  外层脚本及 SSH 子进程。
- 姿态脚本只接受类型为整数、范围 30..100 的 supervisor `min_battery_soc`，并保留 30% 本地
  硬下限；缺失、错误类型、0 或越界值全部 fail-closed。
- 主页面令牌不再放入视频 URL。前端先用请求头换取 15 秒有效、只能消费一次的短期视频令牌；
  access log 对 `token=` 脱敏。相机 SSH stderr 由独立线程持续排空并仅保留 16 KiB 尾部，避免
  长时间运行因管道写满而停流；UI 同时显示接收 fps 和平均带宽。
- 新增可重复的 `competition_ui_offline_test.py`。假机器人/假相机回归实际通过：比赛模式移动与
  姿态 403、并发写 409、STOP 请求绕过锁、视频令牌单次消费与日志脱敏、128 KiB stderr 排空和 MJPEG
  帧转发，以及超时子进程组回收。测试不连接机器狗，也没有执行运动。
- 修正文档中没有落盘依据的 8.37 fps；统一使用已有记录支持的原始话题约 8.14–9.46 fps。真实
  SSH-MJPEG 验收须额外记录狗主控 CPU、内存、温度与自治节点频率。

## 2026-08-13：头部 RGB 真机验收与安全复核

- 真机保持默认比赛 UI、`enable_motion=False`、有线充电闭锁和
  `DOWN_WAITING/run_allowed=false`，没有发送姿态或运动命令。BMS 复核为 99%、24.681 V、
  37°C；运行项目只读审计得到 `READ_ONLY_AUDIT=PASS`，四个正式节点均为单实例。
- localhost UI 经 SSH-MJPEG 连续运行 120 秒取得 709 帧，实测 6.03–6.83 fps、约
  1.26 Mbit/s，读取无错误。流期间记录转码、相机和正式节点 CPU/RSS，流后 CPU 温度约
  51.5°C；系统可用内存保持约 4.8 GB。
- 30 秒重连取得 131 帧，估算 SSH/相机首次出帧启动约 8.91 秒；客户端退出后立即检查未发现
  远端转码进程。该启动耗时不代表画面的真实端到端逐帧延迟，后者仍需同步画面测试。
- 对正在运行的默认 UI 直接提交前进和起立 API，均被后端以 HTTP 403 拒绝；日志中的一次性视频
  令牌保持脱敏。原始摘要落盘到 `docs/evidence/2026-08-13_ui_rgb_acceptance.txt`。
- 下一步仍是物理验收：先由现场人员拔除充电线并确认空场/防滑/防护工装，再做真实零速度
  servo、PAUSE/STOP/watchdog/重启链，最后才允许起立、趴下和六向短脉冲。端到端视频延迟与
  同窗口自治频率也仍未完成。

## 2026-08-13：真实零速踏步失败与零步高修复

- 用户确认拔除充电线和场地安全后开始真实零速度伺服测试。前置状态为 95%、未充电、BMS 正常、
  正式服务 `enable_motion=False`，测试使用单独临时适配器，退出时强制 PAUSE。
- 第一版验收工具暴露两项自身问题：机器狗 Python 不支持 `Popen(text=...)`，且异常后错误地把
  已完成的前置项判为 PASS；已改为兼容参数、完整结果集合和异常必定 FAIL。随后又将 ROS 回调
  改为多线程执行并在 START 前等待控制器 END 转换稳定，避免阶段采样错位。
- 最完整一轮真实获得 START→DATA→watchdog END、重新放行、START→DATA→PAUSE END；速度均为
  零且两个 END 在 0.50 秒内出现。然而现场确认发生原地踏步和少量位移，odom XY 变化
  0.040369 m，因此真实零速度验收明确失败，后续非零脉冲和自治测试停止。
- 根因是 303 慢速行走的静止帧仍携带 0.05 m 步高。真机原厂 303 预设也记录 0.05 m，而 OFF
  预设为 0 m。运动适配器已修正为 START、END 和静止 DATA 使用零步高，只有实际平移/转向输出
  非零时才使用配置步高。
- 修复在 ARM64 上 1 分 59 秒构建通过；隔离 `/mi_dog_test` 回归新增三类零步高断言并全部通过。
  真机最终保持站立、`PAUSED/run_allowed=false`，无临时适配器残留。零步高修复仍需新的现场
  确认后重新连接真实话题验收。
- 修复提交并推送为 `4dc93f0`。随后按 STOP→限权 systemd 重启加载新二进制，最终回到
  `DOWN_WAITING/run_allowed=false` 且 `enable_motion=False`。部署清单
  `deployment_manifest_20260813T140604+0800.txt` 的 SHA256 为
  `1f9dab0bc7b30225df56e3ef299cfa41306f0fdd0961cc0a6fe8cc885b0c47da`。该重启只证明失能部署
  和冷等待策略，不能替代活动零速会话中的重启 END 验收。
- 零步高短 canary 的遥测和现场观察均通过：XY 变化 0.29 mm，用户确认没有踏步、挪脚或平移。
  随后的完整 watchdog+PAUSE 双会话也满足零速度、零步高、两个 END 小于 0.50 秒和 XY
  变化 12.6 mm，但用户观察到机身晃动，不能确定足端是否略微离地，因此没有把该轮记为物理
  通过，也没有继续重启链或非零动作。
- 事后 5 秒静止基线取得 255 组四足接触，四路始终为 0.5；静止 odom 最大 XY 漂移 0.78 mm。
  验收工具新增会话内 50 Hz 四足接触样本与各足最小/最大值记录。下一轮仍需现场近距离观察足端
  或使用防护工装；接触估计不能推翻肉眼确认的离地。
- 足端清晰可见条件下再次运行最短 canary：四路接触估计在 303 切换期间都曾瞬时为 0，odom XY
  变化 6.68 mm，但用户现场明确确认四足均未离地。由此修正证据解释：该固件的
  `contactEstimate=0` 在模式切换时不能单独证明物理离地；现场观察优先。
- 尽管本轮没有真实离地，静止命令进入 303 仍会造成模式/重心切换。适配器进一步改为静止命令
  只保持 END、绝不 START/DATA；活动会话减速到零后立即 END。ARM64 构建 1 分 52 秒通过，
  隔离回归确认 END-only 静止、非零 START/DATA、watchdog、撤权和陈旧命令行为均正确。新的
  真实 END-only 验收尚未执行。

## 如何继续记录

每次工作结束，在本文件追加：日期、目标、变更文件、测试条件、观测数据、最终姿态、
真机部署 commit、未解决问题和下一条可执行任务。不要只写“完成”或“测试成功”。
