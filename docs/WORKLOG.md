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

## 2026-08-13：静止命令 END-only 真机验收通过

- 提交 `5fd1a42` 已部署：静止 `safe_cmd_vel` 不再进入 303，只保持 END；只有真实非零输出才
  创建 START/DATA 会话，减速归零后立即 END。
- 真实话题验收捕获 8 个 END、0 个 START/DATA；全部速度和步高为零。运控状态始终为 112，
  90 组四足接触四路均为 0.5，odom XY 变化仅 0.018 mm；脚本输出
  `REAL_IDLE_COMMAND_ACCEPTANCE=PASS`，最终 PAUSED 且临时进程无残留。
- 用户对最终 END-only 实机验收明确确认没有离地；更早的 canary 数据也说明 contactEstimate
  在 303 切换时的瞬时零值不能单独代表真实离地。最终 END-only 设计完全避免了该步态切换。
- 最终只读状态为 51%、21.854 V、39°C、未充电、`enable_motion=False`、
  `PAUSED/run_allowed=false`、正式节点单实例。因电量接近建议的 50% 起测线，没有继续非零移动、
  姿态或活动会话停止链。
- 部署清单 `deployment_manifest_20260813T143321+0800.txt`，SHA256
  `02c075b2a0c3da95499632602fdcda7b8d41b8f8038be2a063f2dd8043034a76`，记录
  `source_commit=5fd1a42`；安装的 real 节点 SHA256 为
  `4433e7071d805003fba9222f7e88145156491d7c99e49af4cac8faa0112ec788`。
- 下一次先充至建议 70% 以上，再拔线确认空场；剩余停止链必须在有界低速非零会话中测停车
  延迟和距离，不能再用静止命令模拟活动会话。

## 2026-08-15：有界低速前进与 PAUSE 真机 canary

- 电池充满后拔除充电线，BMS 为未充电且正常；原厂起立动作 `111` 返回成功和 100% 进度，
  用户确认稳定站立。
- 使用临时独立适配器发送一次 `vx=0.05 m/s`、持续 0.25 秒的真实前进命令；正式服务始终
  `enable_motion=False`。
- 捕获 START、四个 DATA 和 PAUSE 后四个 END；PAUSE 在 0.50 秒内撤权，END 后无 DATA。
  odom XY 变化 0.031935 m。用户确认短距离前进与停止正常，无打滑、异常抬脚、持续行走、
  明显晃动或异常声音。
- 收尾只读审计通过：四个正式节点各一、临时适配器退出、`PAUSED/run_allowed=false`。
  本轮不证明 watchdog、活动重启、链路中断和其他方向，下一项仍按单变量原则验证。
- 原始摘要：`docs/evidence/2026-08-15_bounded_forward_canary.txt`。

### 同日后续：watchdog 首轮物理正常但距离门失败

- 第二次明确批准的真机测试发送同一 `vx=0.05 m/s × 0.25 s` 脉冲，随后停止发布并等待
  0.30 秒命令 watchdog。自动 END 和脚本 PAUSE END 都在 0.50 秒内，END 后无 DATA。
- 用户确认机器狗保持站立、运动正常且正常停住；114 组四足接触四路始终为 0.5。
- odom XY 变化 0.055171 m，超过预设 0.05 m 门限；Z 变化 0.093842 m，状态样本出现
  motion ID 102/111。因此工具正确输出 FAIL，watchdog 整项不勾选完成，也没有继续测试。
- 收尾只读审计通过，最终 `PAUSED/run_allowed=false`、正式 `enable_motion=False`、临时适配器
  退出。下一步先分析减速斜坡、odom 基线与 motion ID 语义，不直接放宽门限或重跑。
- 原始摘要：`docs/evidence/2026-08-15_bounded_watchdog_attempt.txt`。
- 后续只读核对狗上官方 `motion_id_map.toml`：102 为备用高阻尼趴下、111 为恢复站立、112 为
  行走后站立、303 为慢速行走。结合用户全程观察为站立，102/111 样本只能视为历史/转换状态，
  不能当作测试中实际趴下/起立。代码确认超时后直接 END；END 前六个 DATA 属于 0.30 秒命令
  有效窗口，不是超时后继续输出，但该事实本身不足以放宽 5 cm 门限。
- 进一步审计发现工具在临时适配器启动前记录 odom 起点，随后预启动 END 和 1.5 秒稳定过程
  被混入最终位移。因此 0.055171 m 不是有效的纯运动/停车距离；本轮仍记 FAIL，但归因为测量
  范围错误而不是已证明停车过远。修正版把基线移到 RUNNING 后、首条前进命令前，语法检查通过，
  SHA256 为 `7e528f2b6f830d8c70c2dec68d27d433c3f209bc43600fedf4cb1712b96aaf55`。
- 用户明确批准后用修正版复测：电量 81%、未充电，捕获 START/DATA、0.30 秒命令超时 END，
  之后 PAUSE END；两个 END 时序均在 0.50 秒内，END 后无 DATA。正确基线下 odom XY
  0.034104 m、Z -0.001086 m，状态 303→112，工具输出 `BOUNDED_WATCHDOG_TELEMETRY=PASS`。
- 用户确认短距前进、及时停车和站立均正常，无打滑、异常抬脚、明显晃动、继续行走或异常声音；
  收尾只读审计通过。因此 0.30 秒命令 watchdog 正式通过。Supervisor 0.50 秒许可过期仍须
  独立验证，不能由本轮替代。

### 同日后续：Supervisor 许可失鲜停止通过

- 首轮隔离许可发布端 QoS durability 不兼容，DDS 明确不传消息；适配器保持抑制、没有进入
  运动会话，工具 fail-closed，收尾审计通过。随后改为与正式许可一致的
  transient-local/reliable QoS。
- 用户明确批准修正版后，以正式 Supervisor 始终 `PAUSED/run_allowed=false`、临时隔离许可
  方式执行低速测试。许可停止后 0.60 秒内 END，END 后继续发布前进命令也无 DATA；最终 PAUSE
  END 在 0.50 秒内，临时进程退出，完整只读审计通过。
- odom XY 0.050199 m、Z -0.000596 m；用户确认低速运动、及时停车和站立均正常，无打滑、
  异常抬脚、晃动、继续行走或异常声音。工具因严格 `<0.05 m` 断言输出 FAIL，原始结果不改写；
  超限 0.199 mm 小于既有 0.784 mm 静止 odom 漂移。按 END 时序、END 后拒绝、现场物理观察和
  最终闭锁，Supervisor 许可失鲜停止功能独立验收通过，实测距离仍原样保留。
- 证据：`docs/evidence/2026-08-15_permission_timeout_acceptance.txt`。

### 同日后续：活动 STOP 与项目服务重启通过

- 完整关机重启清除拔充电线后残留的运控 `CHARGING=14`；只读审计通过，比赛前 6 秒频率为
  image 9.155 Hz、scan 8.489 Hz、odom 38.949 Hz。原厂起立 `111` 返回成功和 99% 进度，
  用户确认稳定站立。
- 用户明确批准后执行 `vx=0.05 m/s` 有界活动会话。结构化 STOP 在 0.50 秒内 END，END 后
  无 DATA；限权 sudo 只重启 `mi-dog-real-sensor.service`，重启后进入
  `DOWN_WAITING/run_allowed=false`，正式 `enable_motion=False`。继续发布测试前进命令只有
  END，没有自动恢复旧运动。
- odom XY 0.014769 m、Z -0.006642 m，工具输出
  `BOUNDED_STOP_RESTART_TELEMETRY=PASS`。用户确认短距前进、停车、服务重启过程和声音均正常，
  最终稳定趴卧。收尾 `READ_ONLY_AUDIT=PASS`，四个正式节点各一、临时适配器退出。
- 证据：`docs/evidence/2026-08-15_active_stop_restart_acceptance.txt`。本轮不证明电脑链路断开、
  其他方向或自治赛段。

## 如何继续记录

每次工作结束，在本文件追加：日期、目标、变更文件、测试条件、观测数据、最终姿态、
真机部署 commit、未解决问题和下一条可执行任务。不要只写“完成”或“测试成功”。

## 2026-08-17：修复空闲重复 SERVO_END 导致 BAN_TRANS

- 根因已由原厂运控日志和协议常量确认：`SERVO_END` 是活动 303 Servo 会话的结束转换，旧适配器
  却把它当作 0.20 秒空闲心跳持续发布。原厂 MotionManager 因无活动会话仍反复收到 END，返回
  `BAN_TRANS`（`switch_status=5`）和错误码 3022；此前站立状态下 END-only 未出错的验收不能推广
  到趴卧/空闲状态。
- 用户明确批准后先停止 `mi-dog-real-sensor.service`，确认 `inactive`，再修改
  `mi_dog_real_node.cpp`：抑制或空闲且没有活动 Servo 会话时不发布任何 Servo 帧；非零命令仍以
  一次 START 建立会话；命令 watchdog、Supervisor 撤权或其他安全门退出活动会话时只发布一次
  可靠 END，之后保持静默。未删除雷达、倾角、watchdog、Supervisor 和 UI STOP 安全门。
- 隔离回归使用 `/mi_dog_test/servo_sequence/*`，没有连接真实运动话题。结果：初始抑制和零命令
  均 0 帧；三个新活动会话均 START 后 DATA；0.30 秒命令超时恰好一个 END；Supervisor 撤权
  恰好一个 END；重新许可但没有新命令时 0 帧；所有 START/END 的速度和步高均为零。
- ARM64 `colcon build --packages-select mi_dog_real --symlink-install` 通过，用时 1 分 46 秒。
  机器人端源文件 SHA256 分别为 `2e6f45a53dcf6af01c314fda57cf32e4c6809445eb355253201ea2e338f7acc6`
  和 `750dacddb62f953354fa99eb0414cf28113d83b841740fb016aed8d2120678c2`；安装二进制 SHA256 为
  `e801711a2268822d2fab03190bbfba6e697f799f8c2c73e99e8fbb725e8d9184`。
- 重启维护服务后只读状态为 `active`、`DOWN_WAITING`、stage 1、`run_allowed=false`。真实
  `/motion_servo_cmd` 连续 6 秒没有任何输出，本次启动后的日志没有新的 `Receive ServoCmd`、
  `BAN_TRANS` 或 `motion error code 3022`。全程未发送 START、姿态或移动命令。
- 收尾时电池 75%、23.698 V、35°C、健康度 99，仍为有线充电，原厂状态 14，Supervisor 正确
  报告 `motion_controller_charging_inhibited`。原相机服务仍返回 result 5，属于此前已确认的独立
  相机故障；需要完整重启机器人后再验相机和拔线后的原厂运控状态，不能用本轮结果宣称可运动。
## 2026-08-15 competition-stack preflight

- Added a fail-closed six-stage real controller, competition launch/config, and strict preflight.
- Robot-side ARM64 ROS build passed; dependency-free six-stage, ordering, and fail-closed tests passed.
- Installed the explicitly approved motion-enabled competition service without sending `START`.
- Live preflight passed: camera, lidar, and odometry received; controller reported `sensors_fresh=true`, `INHIBITED`, stage 1, and `run_allowed=false`.
- UI backend status passed against the live service: `active`, `enable_motion=True`, `DOWN_WAITING`, stage 1, battery 69%.
- Robot was still wired charging (`motion_switch_status=14`), so the supervisor correctly kept motion inhibited. Unplug before the final competition START readiness check.

## 2026-08-17：完成无需赛道的课程闭锁与预检加固

- 用户明确批准在不重启整机、不切换比赛服务和不发送运动指令的边界内完成课程闭锁、预检、
  只读审计、文档、ARM64 构建和隔离验收。
- `race_controller.py` 新增默认 `course_calibrated=false`。即使 Supervisor 许可为真且相机、雷达、
  odom 都新鲜，未标定课程仍只输出零速、不会发布赛段完成，并报告
  `COURSE_UNCALIBRATED`。控制器输入输出话题全部参数化，允许测试严格隔离在
  `/mi_dog_test/race_course_gate/*`。
- 本地依赖无关回归通过六赛段顺序、输入失效闭锁和课程未标定闭锁；ARM64 增量构建通过，用时
  5.79 秒。机器人端再次运行依赖无关测试通过；ROS 隔离测试取得 23 条命令，全部为零，赛段完成
  0 条，状态持续包含 `course_calibrated=false` 且传感器新鲜。
- `competition_preflight.sh` 现在要求 service 确实为 competition 模式、四个比赛节点各一、
  `DOWN_WAITING/run_allowed=false`、课程已标定、相机/雷达/odom 有样本、电量至少 50%、未充电、
  运控状态 NORMAL、适配安全参数正确且 8 秒空闲 Servo 零帧。当前 maintenance 模式的本地流式
  和机器人已安装脚本均正确返回 `PREFLIGHT=FAIL service_not_in_competition_mode`。
- `robot_read_only_audit.sh` 改为自动识别 maintenance/competition/sensor-only，不再把已撤下的
  E-stop guard 或旧 `enable_motion=false` 当作所有模式的固定事实。真机收尾审计通过：maintenance、
  正式三节点各一、比赛控制器/guard/HID 均 0、`enable_motion=True`、`DOWN_WAITING/false`、
  空闲 Servo 0 帧；8 秒内雷达 67 帧、odom 330 帧、相机 0 帧。
- 收尾电量 73%、仍有线充电、运控状态 14；服务未重启、未切换、未收到 START/姿态/运动指令。
  相机故障仍需整机重启后只读复验，课程参数和六赛段物理逻辑仍必须等待实物/赛道证据。
- 同步一致性 SHA256：controller `59594794...e39c7a`、ROS 隔离测试
  `bf70081b...4def4`、配置 `3cac570b...73f9c`、预检 `47d9da62...9f497`、只读审计
  `a1d1c7a4...cb6a`；本地与机器人源文件逐项一致。

## 2026-08-17：头部 RGB 冷启动竞争故障与延迟启动候选

- 用户完成整机重启并拔除充电线。重启后只读状态为 52%、未充电、运控状态 0、
  `DOWN_WAITING/run_allowed=false`、安全原因 ready；雷达约 9.14 Hz、odom 约 39.67 Hz、空闲
  Servo 0 帧，但正式 `/image` 为 0。
- 本次启动日志证明 RGB 并非从未启动：`camera_server` 先持续记录约 30 fps 和递增的
  `Publishing image`，到 16:19:11 报 NVIDIA `NvCaptureGetRequest: Free request list is empty`、
  `Capture Scheduler not running` 后停止。项目服务 command 9 在 16:17:43 返回 result 0，说明
  原逻辑把服务响应当成功会产生假阳性。
- 原厂 RealSense D430 lifecycle 初始为 unconfigured；一次诊断性 configure/activate 证明它是
  独立深度/红外设备，不能恢复头部 RGB，随后已 deactivate/cleanup 回到 unconfigured。头部
  `camera_server` 进程仍活着但内部捕获调度器失效；command 10 在 20 秒超时，未继续发送 command 9，
  也未重启整个 `cyberdog_bringup`。
- 根因时序证据：项目在原厂 bringup 尚未完成 RealSense/VINS 启动时开启 CSI RGB；RGB 随后逐步
  降速并耗尽 NvCapture request。经用户明确批准，`run_sensor_gate.sh` 改为立即启动安全节点，
  同 cgroup 后台运行 `start_camera_when_stable.sh`；助手默认等待 uptime 240 秒，再单次请求
  640x480@10 fps，并以 20 秒内真实有效图像帧作为唯一成功条件。失败不重启服务、不放行运动。
- 两脚本通过 `bash -n` 和 `git diff --check`，已同步但没有重启当前 maintenance 服务；远端 SHA256
  分别为 `6c6e19351d4684f40bff28b3e3732796e8278920fdf2cde0f3ba1d00852ae832` 和
  `b8ad65dd1327cbf157c8eecb0e80970003af485f839d88e88dc99894b4a41cc8`。下一次必须整机重启，验证
  安全节点立即就绪、240 秒前不调用相机、之后实际出帧并连续稳定至少 3 分钟；当前不能标 PASS。
- 最终只读收尾为 44%、21.780 V、37°C、未充电、运控状态 0、maintenance active、
  `DOWN_WAITING/run_allowed=false`。因电量低于建议的 50% 起测线，先充电，不立即进行下一次重启验收。

## 2026-08-18：延迟 RGB 与前向净空过滤真机验收

- 两个完整开机周期均证明 `start_camera_when_stable.sh` 在 uptime 240 秒前不请求 RGB，之后以
  真实有效图像帧判成功。正式连续 180 秒采集 1792 帧，平均 10.012 fps、640×480、最长帧间隔
  0.310 秒；本次开机日志无 NvCapture、Capture Scheduler、BAN_TRANS 或 3022。
- 新版单次 END 运动复测首次尝试被旧前向雷达最小值门正确拒绝；空场实际扫描仍含大量
  0.02..0.30 m 的机身/地面回波，因此没有绕过安全门或重复发送运动。
- 新增纯 C++ `FrontClearanceFilter`：过滤已测自回波包络，要求连续角度障碍簇和三帧确认，
  清空同样三帧释放；前超声独立三帧确认，极近返回单帧停车。ARM64 回归覆盖空场、单帧、
  障碍簇、清空、窄噪点、超声普通/极近停车并全部通过。
- ARM64 ROS 构建通过，最终 `mi_dog_real_node` 哈希为
  `d972c6d934bab8449b14e333a112265b38fc0b948e77d8f5827082728b568c09`。新增只读
  `/mi_dog_real/front_clearance_summary`；空场 143 样本融合净空 0.413..0.516 m、超声
  0.561..0.655 m，Supervisor 为 `DOWN_WAITING/run_allowed=false`、空闲 Servo 0 帧。
- 扬声器经原厂服务从 35 调至 25，整机重启后查询仍为 25。充电后最终电量 99%、未充电、
  运控状态 0；尚未重新发送低速动作，下一项仍是使用正确真实 Servo 话题完成一次单次 END 复测。
- 充电后的新版活动会话复测使用实际安装参数指向的
  `/mi_desktop_48_b0_2d_7a_fe_40/motion_servo_cmd`。真实障碍先使净空降至 0.324..0.334 m，
  移除后恢复至 0.399..0.449 m；随后单次 0.05 m/s、0.25 秒前进严格捕获
  `START=1, DATA=1, END=1`，END 后无 DATA/重复 END，STOP 后 6 秒零帧，日志无
  BAN_TRANS/3022，用户确认短距前进和停车正常。调试脚本末尾会主动发送零速，因此本轮不冒充
  独立 watchdog 证据；0.30 秒 watchdog 沿用 2026-08-15 真机验收。
- 用户随后断开电脑链路并重新连接。狗端服务保持原 MainPID 6132、启动时间 19:04:53、
  `NRestarts=0`；Supervisor 继续为 `EMERGENCY_STOP/run_allowed=false`。重新连接后只读审计
  取得相机 70、雷达 71、odom 326、真实 Servo 0 帧，证明狗端服务连续运行和锁存停止不依赖
  电脑在线；活动运动链路丢失的停止时序沿用独立 watchdog/许可超时证据。
- 经用户明确批准，maintenance 重启到 DOWN_WAITING 后通过 UI 同后端依次执行前、后、左、右、
  左转、右转各一次 0.25 秒脉冲。每次后均复核 RUNNING/true、safety ready、运控 0；日志严格
  六次会话开始和六次单次 END。最终 STOP 为 EMERGENCY_STOP/false，6 秒真实 Servo 0 帧且无
  BAN_TRANS/3022。用户现场确认左右转方向正确；本轮未保存逐向 odom/视频，因此不声称精确位移
  或停止距离。

## 2026-08-20：第一赛段高速高步候选（未部署）

- 按用户要求将真机第一赛段候选前进速度从 `0.10 m/s` 提高到 `0.25 m/s`，比赛适配器前进
  限幅同步由 `0.15 m/s` 提高到 `0.25 m/s`；其余赛段速度不变。
- 运动适配器新增当前赛段订阅：第一赛段非零运动使用 `0.10 m` 步高，第二至第六赛段及赛段
  信息缺失/非法时保持或回退到 `0.05 m`。START、END、静止 DATA 仍固定为零步高。
- 保留 0.30 m/s² 前进加速度斜坡、0.70 m 前方减速区、0.35 m 停止线、传感器新鲜度、
  supervisor 许可和命令超时闭锁。
- 依赖无关回归通过：race controller 六赛段顺序、输入 fail-closed、课程未标定闭锁、官方几何、
  mission 六赛段/断点和 course perception 测试全部 PASS；全部 Python 脚本语法检查及
  `git diff --check` 通过。
- 更新 ARM64 隔离 Servo 测试，新增第一赛段 DATA 为 `0.10 m`、第二赛段 DATA 回落 `0.05 m`，
  START/END 零步高的既有断言保留。当前宿主没有 ROS 2/colcon，故尚未执行 ARM64 编译和该
  ROS 隔离测试。
- 本轮没有部署、没有发布真机运动命令，机器狗姿态未观测、真机部署 commit 未改变。
- 未解决：`0.10 m` 超出此前已观察的原厂 303 预设 `0.05 m`，必须先完成 ARM64 构建和隔离
  输出验证，再在急停可用、保护工装/牵引保护和低速起步条件下逐级验证；在此之前不能把
  “第一赛段正常运行”标为真机通过。

### 同日逻辑复核与实机前置检查

- 复核确认赛段步高订阅 QoS 与 Supervisor 的 transient-local/reliable 发布一致，第一赛段
  `0.10 m`、其他或非法赛段回退 `0.05 m` 的适配逻辑成立；停止、命令超时、许可、姿态和前方
  障碍闭锁没有被参数修改绕过。
- 但完整第一赛段目前不能标为逻辑正确：正式 `race_controller.yaml` 仍为
  `course_calibrated=false`，必然输出零速；通用骨架的 stage 1 前方净空阈值为 `0.42 m`，会把
  需要正面通过的石板当作普通障碍。当前控制器也仍是距离/三扇区骨架，不具备四石板物理门控。
- 按用户要求准备实机试验前先执行只读审计；沙箱外 SSH 连接
  `mi@192.168.44.1:22` 超时，未取得机器狗状态。因此没有构建、部署、重启或发布运动命令。
- 下一步：恢复电脑 `192.168.44.100/24` 与狗主控有线连接后重跑只读审计；先做 ARM64 编译和
  隔离 Servo 输出验证。完整第一赛段必须补齐石板专用感知/门控并完成低速分级测试，不能直接
  用现有通用骨架以 `0.25 m/s` 开跑。

### 同日第一赛段参数实机直行测试

- 网络恢复后只读审计通过：maintenance、三个正式节点单实例、stage 1、99% 电量、未充电、
  `DOWN_WAITING/run_allowed=false`、空闲真实 Servo 0 帧。
- 在狗侧用户工作区创建三文件备份 `state/pre_stage1_highstep_20260820/`，同步运动适配源码、
  competition 配置和隔离 Servo 测试；没有覆盖原厂 manager/robot-software。
- ARM64 `colcon build --packages-select mi_dog_real --symlink-install` 用时 2 分 14 秒并通过。隔离
  Servo 回归全部通过：stage 1 DATA 步高 `0.10 m`、stage 2 DATA `0.05 m`、START/END 零步高，
  watchdog 和撤权均单次 END。
- 重启 maintenance 后只读审计再次通过；官方站立动作 111 返回
  `result=true/code=0/progress=100`。Supervisor START 后为 `RUNNING/stage=1/run_allowed=true`。
- 执行有界 odom 直行测试，请求 `2.0 m @ 0.25 m/s`，带 35 秒超时、0.50 m 横移和 0.50 rad
  航向保护。真实 Servo 会话于 22:50:33 START；22:51:02 前方融合净空降至 0.333 m，小于
  0.350 m 停止线，适配器正确发送单次 END，后续净空为 0.321..0.326 m 并持续拒绝前进。
- 因前方障碍门提前停止，脚本最终 `distance_timeout`，未证明达到 2.0 m；首版失败路径未打印
  最终 odom 位移，已修正脚本使后续 PASS/FAIL 都输出前进、横移、航向、最大 Servo 速度和步高。
- 测试后发送锁存 STOP。最终只读审计通过：`EMERGENCY_STOP/run_allowed=false`、空闲 Servo
  0 帧、93% 电量、未充电、运控状态 0；用户目视直线性结论待记录。

### 同日 0.6 m/s 与更高步高请求复核

- 狗上官方 `motion_id_map.toml` 确认 303 为慢速行走、305 为快速行走；303/305 预设都只给出
  `vel_des=[0.1,0,0]`、`step_height=[0.05,0.05]`，没有给出 `0.6 m/s` 或高于 0.10 m 步高的
  允许范围。当前适配器和真实停止链只验收到 303、0.25 m/s 包络，不能把 305/0.6 当作已支持。
- 0.6 m/s 在现有 0.30 m/s² 加减速包络下，仅理想制动距离就约 0.60 m，已大于当前 0.35 m
  停止线；且没有独立实体急停。故保持真机锁存 STOP，没有提高速度/步高或发起新运动。
- 有界直行测试脚本新增 odom/IMU 航向与横向闭环：`wz=clamp(-1.2*yaw_error-0.4*lateral,
  ±0.25)`，并记录真实 Servo 最大角速度。该闭环尚未再次实机运行。

### 同日 0.4 m/s 高步直行闭环实测

- 用户确认现场清空后，将第一赛段候选请求和 competition 适配上限提高到 `0.40 m/s`；步高
  保持 `0.10 m`。狗侧旧配置备份在 `state/pre_stage1_040_20260820/`，重启后实时参数查询确认
  `max_forward_mps=0.4`、`stage_1_step_height_m=0.1`、加速度 0.3、停车线 0.35、减速线 0.7。
- START 放行后执行 2.0 m odom/IMU 闭环。测试 PASS：前进 `2.0001 m`、横移 `0.0319 m`、
  末端航向误差 `0.0157 rad`（约 0.90°）、耗时 `25.245 s`；闭环真实 Servo 最大角速度
  `0.0569 rad/s`。
- 捕获的真实 Servo 最大步高为 `0.1000 m`，证明本轮高步命令确实进入真实运控话题。上层请求
  虽为 `0.40 m/s`，真实 Servo 峰值仅 `0.1391 m/s`，说明保留的前方净空减速链显著限速；
  本轮验证了 0.4 请求包络与直行修正，但没有证明机器狗物理达到 0.4 m/s。
- 结束后立即锁存 STOP。最终只读审计 PASS：`EMERGENCY_STOP/run_allowed=false`、空闲 Servo
  0 帧、79% 电量、未充电、运控状态 0；用户现场目视评价待补充。

### 同日 0.15 m 步高复测

- 用户目视确认 0.10 m 步高一轮“挺直”，随后明确要求 0.15 m 再测。0.10 m 版本备份于狗侧
  `state/pre_stage1_step015_20260820/`；源码参数上限、competition 配置和隔离断言同步改为
  0.15 m。
- ARM64 构建 2 分 10 秒通过；隔离 Servo 回归全部 PASS，确认 stage 1 DATA 为 0.15 m、stage 2
  为 0.05 m、START/END 零步高、watchdog 与撤权单次 END。重启后实时参数为
  `max_forward_mps=0.4`、`stage_1_step_height_m=0.15`。
- 2 m odom/IMU 闭环实测 PASS：前进 `2.0007 m`、横移 `0.1079 m`、末端航向误差
  `-0.0153 rad`（约 -0.88°）、耗时 `27.585 s`、真实 Servo 最大前进速度 `0.1543 m/s`、
  最大角速度 `0.0440 rad/s`、最大步高 `0.1500 m`。
- 与上一轮 0.10 m 的横移 0.0319 m 相比，本轮横移增至 0.1079 m；航向角仍接近初始方向，说明
  高步下存在更明显的侧向漂移，当前横向闭环增益需要结合用户目视反馈再调，不能仅凭到达 2 m
  判为更优。
- 测试结束立即锁存 STOP；最终审计 PASS：`EMERGENCY_STOP/run_allowed=false`、空闲 Servo 0 帧、
  70% 电量、未充电、运控状态 0。

### 同日第一赛段中心线回拉与越线前停车

- 用户要求比赛流程检测偏移并主动往回拉。审计发现正式流程此前只有相机黄线航向误差和左右
  雷达差转向，没有基于 stage 入口 odom 中心线的横向误差，也没有横偏减速/停车；维护测试脚本
  的横向增益仅 0.4，0.15 m 高步实测横移达到 0.1079 m。
- 新增 `StraightLineGuard`：stage 1 首个 RUNNING 位姿锁定为参考直线，使用
  `wz=clamp(base_yaw-1.2*heading_error-1.5*lateral_error, ±0.25)`；横偏超过 0.08 m 逐渐减速，
  达到 0.18 m 输出零速并报告 `TRACK_DEVIATION`。换赛段会重置参考线；无效四元数不刷新 odom。
- 正式状态输出新增 `track_guard_state`、`cross_track_error_m` 和 `odom_heading_error_rad`。维护
  2 m 测试脚本同步使用 1.5 横向增益，并把横偏硬停止从 0.50 m 收紧到 0.18 m。
- 同时修复正式比赛速度配置未生效的问题：`race_mission.py` 原先硬编码 stage 1 为 0.08 m/s，
  现在从六个 `stage_N.speed_mps` 配置接收速度；默认课程未标定闭锁仍保持 false/零输出。
- 狗侧旧文件备份于 `state/pre_track_guard_20260820/`。ARM64 增量构建 2.01 秒通过；离线六赛段、
  fail-closed、mission 回归和隔离 ROS 测试全部 PASS。隔离测试证明 fresh 输入产生候选运动、
  0.20 m 横偏归零、原始图像失鲜归零，且仅使用 `/mi_dog_test` 话题，没有连接真实运控。
- maintenance 服务没有重启或启动比赛控制器，本轮没有新的真机运动；正式六赛段仍因
  `course_calibrated=false`、物理 facts 生产者未完成而不可开赛。

### 同日安全趴下与全赛道 0.08 m 外边界保护

- 用户要求省电后，通过安全重启解除锁存 STOP 到 `DOWN_WAITING`，在 `run_allowed=false` 下调用
  原厂趴下动作 101；服务返回 `result=true/code=0`，动作进度由 99% 到 100%。最终状态保持
  `DOWN_WAITING/run_allowed=false`，电量 62%、温度 36°C，未发送行走指令。
- 复核确认此前只有第一赛段 0.08 m 减速、0.18 m 停车的中心线保护；官方几何中的 0.15 m
  `solid_boundary_keepout_m` 仅用于几何校验，并未限制六赛段输出。
- 新增独立 `CourseBoundaryGuard`，按用户选择把全局外边界最终不可侵入余量设为 0.08 m；六个赛段
  的 RUNNING 输出均检查标定后的 `course_pose`。从 0.30 m 开始减速回拉，并用 0.20 s 反应时间、
  0.40 m/s² 限减速度计算停车点；当前位置或预测停车点触线，以及坐标缺失/非法时输出零速。
- 黄色边界不是固定坐标：颜色阈值和最少像素数当前为固定参数/常量，左右线像素位置、车道中心与
  航向修正每帧实时识别。离线边界、黄色识别、六赛段任务和 fail-closed 回归 PASS，语法检查与
  `git diff --check` PASS；尚未构建、部署或实机运动，狗保持趴下。
- 2026-08-21 部署前只读审计 PASS：maintenance、`DOWN_WAITING/run_allowed=false`、Servo 0 帧；
  电量 71%、有线充电、`motion_switch_status=14`，充电闭锁进一步禁止运动。狗侧旧文件备份于
  `state/pre_boundary_guard_20260821/`，新文件先进入 `state/boundary_guard_staging_20260821/`，
  本机与暂存 SHA256 一致后才安装到独立 `/home/mi/mi_dog_ws`，未修改原厂软件。
- ARM64 `colcon build --packages-select mi_dog_real --symlink-install` PASS：1 个包，构建 2.59 秒。
  已安装版本的边界、六赛段、fail-closed 和黄色识别纯算法回归全部 PASS；隔离 ROS 验收证明
  fresh 输入产生候选速度、0.20 m 第一赛段横偏归零、预测外边界侵入归零、原始图像失鲜归零。
  首轮 2.5 秒等待因 ARM64 首次 ROS discovery 未取得候选速度而失败；将隔离测试的首次发布窗口
  增至 4.0 秒后连续复验 PASS，不改控制器运行参数。
- 最终安装哈希与本机一致：控制器 `8767c852...be3cec`、离线测试 `b6c7ab47...5795d`、隔离测试
  `fb6692e3...a1f60`、配置 `5392a3ba...bad0e`。部署后只读审计再次 PASS：maintenance、
  `DOWN_WAITING/run_allowed=false`、Servo 0 帧、电量 72%、有线充电；没有重启服务、切换
  competition、发送 START 或真实运动指令。
- 生成 schema v3 部署清单
  `/home/mi/mi_dog_ws/state/deployment_manifest_20260821T000839+0800.txt`，SHA256 为
  `e0882005d2d6b57dd2bff9bdfb6b869f6632aefdf658436124b30c4af9e718f5`。因本地连续改动尚未
  冻结，清单诚实记录 `source_commit=unknown`；清单确认 maintenance active、比赛控制器未运行、
  `DOWN_WAITING/run_allowed=false`。正式提交和回滚归档留到场地验收后的版本冻结步骤。

### 2026-08-21 UI 功能复验

- `competition_ui_offline_test.py` 完整 PASS：正式模式拒绝人工移动/姿态、并发写 HTTP 409、STOP
  抢占、相机单次令牌与日志脱敏、stderr 回收、姿态电量参数门、直接脚本门、超时进程组清理及
  裁判事件后端流程均通过。首次受宿主沙箱禁止回环 socket，授权仅绑定 `127.0.0.1` 后通过。
- 实机 UI 以正式比赛模式启动，`maintenance_controls=false`、目标 `mi@192.168.44.1`；health 200，
  无令牌 status 403，带令牌只读 status 200。前进 jog 和 stand 姿态请求均由 UI 后端返回 403，
  没有到达机器人控制脚本。
- UI 相机单次流取得 HTTP 200、multipart 边界和 JPEG 内容类型，首个分片 4.24 秒；断开后指标
  `active=false`，后台流进程正常回收。访问日志中的视频 token 显示为 `<redacted>`。
- UI 随后正常关闭。最终只读状态：service active、`DOWN_WAITING`、stage 1、
  `run_allowed=false`、98% 电量、31°C、未充电、`motion_id=0/progress=100/switch_status=0`；
  本轮没有调用 START、CONTINUE、PAUSE、STOP、restart、选关、姿态动作或真实运动命令。
## 2026-08-21：赛段一距离复核与赛段二直通部署

- 首次仅按文字尺寸把赛段一误算为 2.60 m；随后直接高分辨率读取官方 PDF 第3页并撤销该值。
  官方起点箭头朝图纸 `+x`，起点中心约 `(0.50,0.50)`，右上 0.60 m 开口中心约
  `(3.70,1.00)`：穿板直线段为约 3.20 m，随后必须左转到 `(3.70,1.30)` 才完全进入球区。
- 赛段二取消逐球遍历和四枚橙球完成门，改为从右下入口向左上 0.60 m 出口对角导航；两开口
  中心线约 5.25 m，出口门使用 `x<=0.60,y>=5.00`，目标延伸到 `(0.30,5.30)` 接入曲道。
  橙球检测仅做连续帧去重播报，不影响路径或完成条件。
- 适配器只在赛段二把前方硬停/减速距离改为 0.18/0.40 m，以允许低速接触密集小球；其余
  赛段继续使用 0.35/0.70 m，边界、姿态、传感器鲜度、许可和 watchdog 门不变。
- 本地三组依赖无关回归通过；狗端 ARM64 增量构建 2 分 28 秒通过，狗端同组回归和隔离
  Servo 序列全部通过。离线 `orange_ball.wav` 已安装，`paplay` 返回 0。
- 激活前发送 STOP，维护服务重启后为 `DOWN_WAITING/stage=1/run_allowed=false`；实时参数为
  stage-1 步高 0.15 m、stage-2 前方门 0.18/0.40 m，6 秒空闲 Servo 无帧。电池 84%、36°C、
  有线充电，运动继续被闭锁。回滚目录为
  `/home/mi/mi_dog_ws/state/pre_stage2_direct_20260821/`。

### 同日官方图纸坐标系复核（赛段三至六）

- 沿用起点左下外角为 `(0,0)`、图纸向右为 `+x`、向上为 `+y` 的统一坐标系，按第 3 页高清图
  复核后记录：第三段入口/出口中心 `(0.30,5.00)` / `(3.70,7.00)`；第四段位于
  `y=7.00–11.00`，三条搜索通道中心 `x=0.50/1.50/2.50`；第五段独木桥中心 `x=3.75`、
  `y=7.00–12.00`，跳下线 `y=11.50`；第六段区域 `y=12.00–16.00`。
- 更正此前几何记录：独木桥图纸净宽是 `0.50 m`，不是 `0.60 m`；`0.60 m` 属于弯道及开口。
  第六段环道中心线为 `y=12.25 -> x=0.25 -> y=15.75 -> x=3.75`，图示足球中心
  `(1.00,15.00)`、右侧出口约 `y=13.50`、终点圆中心约 `(3.75,13.25)`。
- S 弯未给圆弧半径，只固化入口/出口锚点，弯内必须使用黄色双边界闭环；第四段目标和障碍物
  赛前随机，只固化区域及通道坐标，明确禁止把目标坐标写死。
- 修复第一段直行保护作用域：只在四块石板尚未通过时保持入口 odom 直线，通过第四块后重置，
  不再阻碍右侧出口的 90 度转弯。新增坐标关系、桥宽、跳下线和保护切换回归，三组本地离线
  测试及 `git diff --check` 均通过。
- 部署前确认维护服务 active、比赛控制器/感知节点均未启动，服务日志持续报告运行许可为 false、
  missing 或 stale。旧版备份到
  `/home/mi/mi_dog_ws/state/pre_official_coordinate_audit_20260821/`；ARM64 `colcon build` 通过，
  本地/狗端 5 个关键文件 SHA256 一致，狗端三组离线回归全部 PASS。构建后仍为 maintenance，
  未重启服务、未启动比赛节点、未发送任何运动指令。

## 2026-08-21：调试工作站迁移准备与仓库冻结

- 新增 `docs/WORKSTATION_MIGRATION.md`，覆盖 Git 工作树、离线完整快照、Docker 基础/派生镜像、
  可选 WSL 导出、新电脑独立 SSH 密钥、直连网卡、首次只读审计、UI、仿真和现场重标定流程。
- 明确 WSL 导出不包含 `/mnt/e` 项目目录，Docker Desktop 镜像也需单独导出；新电脑不得使用旧
  Git 版本直接覆盖机器人 `/home/mi/mi_dog_ws`。
- 提交前发现本地配置保存了某次开机后的有效 odom 变换。机器人随后已经重启，该变换不再可移植；
  因此仓库默认恢复为 `site_transform_valid=false`、零变换和 `course_calibrated=false`。标定工具、
  雷达+里程计降级支持及 `max_enabled_stage: 2` 保留，但都不能绕过现场标定门。
- 提交前曾启动一次新镜像冷跑：镜像构建和 smoke test PASS；赛段一四块石板及合法开口通过，
  赛段二直通并进入三、赛段三进入四。用户指出整场仿真不在本次“提交和打包”授权范围后，立即
  中止日志跟踪并删除专用容器；该次运行没有完成赛段四至六，明确不作为整场验收证据。
