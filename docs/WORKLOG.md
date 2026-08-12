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
  不依赖。三个 Type-C 暂按铁蛋一接口定义参考，CyberDog 2 三口映射仍作为实体接线前置项。
- 按铁蛋一思路完成无插接只读盘点：Tegra 内核报告 USB2 port 0 `OTG_CAP`，存在
  `3550000.xudc`，configfs 配置 NCM/RNDIS/ACM/mass-storage gadget；当前 USB/USB_HOST 状态
  均为 0，`usb0` 无 carrier。该证据只能确认 OTG/device 能力，不能把它映射到三个外部口，
  因此没有恢复 HID 正式服务或尝试插接。

## 如何继续记录

每次工作结束，在本文件追加：日期、目标、变更文件、测试条件、观测数据、最终姿态、
真机部署 commit、未解决问题和下一条可执行任务。不要只写“完成”或“测试成功”。
