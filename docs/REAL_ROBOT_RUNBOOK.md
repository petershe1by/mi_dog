# CyberDog 2 真机操作手册

适用范围：当前默认无运动的传感器、电脑操作和 supervisor 服务。

当前禁止：设置 `enable_motion=true`、充电时执行姿态动作、直接运行整场自治。

## 急停守卫

正式无运动服务已启动 `mi_dog_estop_guard_node`。原始输入为
`/mi_dog_real/emergency_stop_input`：`true` 表示实体急停按下，`false` 表示按钮释放且链路
健康。守卫在启动、输入缺失或超过 0.25 秒未更新时都向
`/mi_dog_real/emergency_stop` 以 20 Hz 发布 `true`。

即使首次收到 `false` 也不会解锁；必须先看到一次 `true`，再看到 `false`，形成操作者明确的
按下—释放周期。链路超时后重新连接同样需要新的按下—释放周期。这是防止设备上电、插线或
单根信号线故障导致自动放行的设计。当前没有实体输入设备，因此正式状态应保持
`input_missing` 和急停 `true`；这不妨碍 `enable_motion=false` 的只读诊断。

检查命令：

```bash
ros2 topic info /mi_dog_real/emergency_stop --verbose
ros2 topic echo /mi_dog_real/emergency_stop_guard/status \
  --qos-durability transient_local --qos-reliability reliable
```

赛事已确认不要求额外实体急停。该守卫保留为兼容/诊断代码，不再是比赛前置条件；非零运动
前仍必须验证电脑暂停、服务重启、命令 watchdog 和许可撤销均能停止输出。

### 外部 Type-C 定义

用户已确认三个 Type-C 分别为 `UDisk`、`charge`、`download`，定义参考铁蛋一。实际物理
位置必须按机身标识，不按左右顺序猜测：U 盘只接 UDisk，充电器只接 charge，官方调试线只
接 download。`estop_hid_input.py` 只保留为历史软件原型，正式服务不启动它。

## 现场角色与环境

- 一人负责电脑启动/暂停/重启，一人观察机器狗和场地；非零运动前先演练暂停与重启。
- 地面平整、防滑；狗前后左右至少留出安全空间。
- 不在桥边、台阶边、桌边或人群附近开机测试。
- 运动或姿态测试前必须拔掉充电线；充电时只允许只读诊断。

## 连接信息

- 电脑有线地址：`192.168.44.100/24`
- 狗主控：`mi@192.168.44.1`，主机名 `mi-desktop`
- 运控板：`192.168.44.233`；日常工作不要登录或覆盖其原厂目录
- ROS 2 域：`42`
- RMW：`rmw_cyclonedds_cpp`
- CycloneDDS：`file:///etc/mi/cyclonedds.xml`

密码不写入仓库、脚本、shell 历史或文档。使用设备交接时单独提供的凭据。

## 开机与只读检查

若电脑已配置 SSH 公钥，可先在电脑端执行一键只读审计：

```bash
./scripts/robot_read_only_audit.sh
```

脚本强制使用密钥认证，不会提示或记录密码；它不发布 ROS 消息、不重启服务、不写入机器狗，
并要求服务 active、四个正式节点各一个、HID 原型未运行、`enable_motion=False`、
`manage_dialogue=False`、安全闭锁状态、`run_allowed=false`、急停 true 和 `input_missing`。
安全闭锁状态包括正常冷启动的 `DOWN_WAITING`、人工暂停后的 `PAUSED` 和锁存停止后的
`EMERGENCY_STOP`；`RUNNING` 或未知状态会失败。任一条件不符都会以非零状态退出。没有公钥时继续使用下面的人工只读流程，
密码只在交互式 SSH 提示中输入，不写入命令或脚本。

1. 确认狗趴在平整地面，充电线状态符合本次任务。
2. 开机，等待系统稳定，再插入网线。
3. 电脑配置 `192.168.44.100/24`，SSH 登录主控。
4. 加载环境：

```bash
source /opt/ros2/galactic/setup.bash
source /opt/ros2/cyberdog/setup.bash
source /home/mi/mi_dog_ws/install/setup.bash
export ROS_DOMAIN_ID=42
export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp
export CYCLONEDDS_URI=file:///etc/mi/cyclonedds.xml
```

5. 检查服务和日志：

```bash
systemctl is-active mi-dog-real-sensor.service
systemctl status mi-dog-real-sensor.service --no-pager
journalctl -u mi-dog-real-sensor.service -n 100 --no-pager
```

6. 检查 supervisor：

```bash
ros2 topic echo /mi_dog_real/supervisor/state \
  --qos-durability transient_local --qos-reliability reliable
ros2 topic echo /mi_dog_real/supervisor/run_allowed
ros2 topic echo /mi_dog_real/supervisor/lie_down_safety_reason
```

当前正常等待结果应是：服务 `active`、状态 `DOWN_WAITING`、`run_allowed=false`。
`lie_down_safety_reason=ready` 只代表只读输入满足当前趴下许可，不表示会自动执行动作。

7. 检查配置没有开启运动：

```bash
ros2 param get /mi_dog_real enable_motion
```

预期为 `False`。不是 `False` 时立即停止服务并调查，不继续测试。

## 电脑比赛控制

比赛允许电脑用于开始、中途暂停和重启。推荐入口：

```bash
./scripts/competition_control.sh status
./scripts/competition_control.sh start
./scripts/competition_control.sh pause
./scripts/competition_control.sh continue
./scripts/competition_control.sh restart
```

脚本只发布 supervisor 白名单事件或重启服务，不接受方向、速度、步态和姿态参数。密码在
SSH/sudo 提示中交互输入，不存储。`pause` 应返回 `PAUSED/run_allowed=false`；`restart` 后应
返回 active，并按设计进入 `DOWN_WAITING`。

## 单狗离线比赛模式

正式比赛不使用电脑作为算力节点。可按现场需要使用直连网线发送上述结构化操作，也可拔除
网线让狗独立运行。`mi-dog-real-sensor.service` 安装在狗上并随
`multi-user.target` 自启；unit 只等待 `network.target`，不等待外部网络在线。CycloneDDS
配置 `/etc/mi/cyclonedds.xml` 固定使用 `lo` 和 `localhost`，本机 ROS 2 通信不依赖 eth0。

当前服务仍是无运动版本，它只能证明开机等待、语音、触摸、传感器和 supervisor 的本机
基础链，不能完成六赛段。正式运动版本必须另行逐段验收，不能通过把当前 YAML 的
`enable_motion` 直接改为 true 得到。

2026-08-10 已完成一次真实冷启动验收：用户确认外部网线在开机、等待、唤醒和“暂停”期间
均已拔除，随后才插回；日志显示四节点自启、口令被接受、离线提示音完成且无运动输出。
同日后续测试在关闭 Wi-Fi、拔除外部 RJ45 后冷启动：四节点、本机唤醒、头部双击暂停和
离线提示音仍工作，证明基础链不依赖外网。但打开 `continue_dialog` 会同时启用原厂动作
路由，现场发生原厂恢复站立。因此该结果不是语音控制验收，且不证明真机赛段控制器。

## 语音操作（非比赛要求）

> **当前禁止用于姿态或比赛控制。** 正式配置为 `manage_dialogue=false`。2026-08-10 实测中，
> 本程序拒绝了白名单外的 `站起来`，原厂助手仍执行了 `motion_id=111`。在自定义 ASR 与
> 原厂动作路由完全隔离前，不得使用下表口令启动、恢复、暂停或停止真实比赛流程。

下表仅保留为待重新验收的设计映射：

每条口令先说唤醒词“铁蛋铁蛋”，等待狗回应后说短口令：

| 目的 | 口令 | 结构化事件 |
| --- | --- | --- |
| 从第一赛段开始 | `启动` | `START` |
| 从当前检查点恢复 | `恢复` | `CONTINUE` |
| 暂停 | `暂停` | `PAUSE` |
| 锁存停止 | `终止` | `STOP` |

判断是否进入程序，以 `/mi_dog_real/operator_event`、supervisor 状态和日志为准，不以原厂
“暂时回答不上来”等云端回答为准。离线 `play_id=9000` 提示音表示命令已被程序接收。

若 START/CONTINUE 到达时安全输入不满足，事件会被拒绝；条件后来恢复也不会自动开始，
必须重新唤醒并重新下令。

## 触摸操作

- 头部触摸区双击对应 `touch_state=3`，程序发布 `PAUSE_TOUCH`。
- 一次手势可能重复上报，程序用 1.5 秒锁定窗口去重。
- 原厂可能同时播报电量，这是硬件识别双击的现象，不代表暂停逻辑失败。
- 单击在现有测试中没有产生可用的 `touch_status`，不要把单击当作控制手势。

## 暂停、恢复和停止

当前软件暂停会撤销 `run_allowed` 和速度许可，但自动安全趴下尚未连接。

- 普通暂停：电脑执行 `competition_control.sh pause`，确认 `PAUSED/run_allowed=false`。
- 恢复：先确认环境安全和裁判许可，再执行 `competition_control.sh continue`。
- 锁存停止：执行 `competition_control.sh stop`；它不接受人工运动参数。
- 重启：执行 `competition_control.sh restart`。服务读取赛段编号，但强制回到
  `DOWN_WAITING`，不会自动继续。

## 只读传感器采集

头部地面 ToF：

```bash
ros2 run mi_dog_real ground_tof_capture.py --samples 20 --timeout 15
```

该工具不导入运动接口。站立时 ROI 落点接近前脚，禁止人员伸手放置物体；几何落差只能在
防坠工装上远程改变目标板。

常用话题：

```bash
ros2 topic hz /mi_dog_real/foot_contact_estimate
ros2 topic echo /mi_dog_real/proximity_summary
ros2 topic echo /mi_dog_real/head_ground_roi_summary
```

## 重新构建和部署

在主控独立工作区构建：

```bash
cd /home/mi/mi_dog_ws
source /opt/ros2/galactic/setup.bash
source /opt/ros2/cyberdog/setup.bash
colcon build --packages-select mi_dog_real
```

构建后先记录仓库 commit 和文件哈希，再重启无运动服务：

```bash
sudo systemctl restart mi-dog-real-sensor.service
systemctl is-active mi-dog-real-sensor.service
```

把清单工具安装到工作区后生成只读清单：

```bash
install -m 0755 /path/to/capture_deployment_manifest.sh \
  /home/mi/mi_dog_ws/scripts/capture_deployment_manifest.sh
/home/mi/mi_dog_ws/scripts/capture_deployment_manifest.sh --source-commit COMMIT
```

工具要求四种正式节点各只有一个进程；HID 原型不得出现在正式服务中。若隔离测试留下同名
孤儿进程，工具会拒绝生成清单。
不要在存在重复节点时相信 `ros2 param get /mi_dog_real ...` 的单次结果。

不得运行赛事镜像中的 `scp_to_cyberdog.sh`；它会删除或覆盖原厂运控目录。

## 故障排查

| 现象 | 检查 | 处理 |
| --- | --- | --- |
| SSH 不通 | 电脑地址、网线、`192.168.44.1` | 不猜其他口令或拆机，先恢复有线配置 |
| 服务反复重启 | `journalctl -u ...` | 保持狗趴卧，修复配置/ABI 后再启动 |
| 只回应唤醒词 | `dog_wakeup`、`continue_dialog`、`asr_text` | 以程序话题判断，不依赖云端问答 |
| START 无效 | supervisor reason、BMS、odom、motion_status | 修复输入后重新说 START，不等待自动启动 |
| 显示充电闭锁 | 拔线状态、BMS、`switch_status` | 真实充电不得运动；残留 14 时正常重启 |
| ToF 对纸箱不变 | 这是向下看的地面传感器 | 正前障碍使用超声/雷达，不改成危险阈值 |
| `run_allowed` 过期 | supervisor 服务和 DDS | 最终适配器会自动停止；先修通信 |
| 参数与 YAML 不符 | `ps`、重复 node name、清单工具 | 先精确清理隔离测试孤儿，再重新采集 |

## 收尾

1. 确认状态不是 `RUNNING`，`run_allowed=false`。
2. 确认狗处于稳定趴卧；自动趴下未实现时由已验收的人工/官方流程处理。
3. 导出 `journalctl`、测试命令、版本和配置哈希。
4. 若需要关机，使用设备官方关机方式；不要直接拔主电源。
5. 在 [工作记录](WORKLOG.md) 中写明最终姿态、是否充电、异常及下一步。
