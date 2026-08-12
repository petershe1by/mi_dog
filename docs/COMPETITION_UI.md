# 比赛控制 UI 与远程连接

## 一次性准备

电脑使用直连网线并配置 `192.168.44.100/24`，狗主控为 `192.168.44.1`。首次在项目根目录
运行：

```bash
./scripts/setup_robot_ssh_key.sh
```

它创建专用 Ed25519 密钥 `~/.ssh/mi_dog_competition_ed25519`，只把公钥追加到狗的
`authorized_keys`；不在仓库、UI 或脚本中保存密码。

## 启动 UI

```bash
./scripts/start_competition_ui.sh
```

浏览器打开 `http://127.0.0.1:8765/`。服务默认只监听本机回环地址，写操作还要求每次启动随机
生成的页面令牌，不暴露到场地网络。UI 提供：

- 实时服务、supervisor、赛段、运行许可、运动总开关、电量、充电状态、电池温度和安全原因；
- 一键 START、PAUSE、STOP（失能）和服务重启；
- 选择赛段 1..6 并发送 CONTINUE；赛段选择只允许在 `DOWN_WAITING/PAUSED`，会先持久化
  检查点，选择本身不会开放运动许可；
- 六向低速调试移动和 STOP；每次非零按钮只产生 0.25 秒脉冲，并同时要求真机
  电量不低于 supervisor 的实时下限、未接充电线、`enable_motion=True` 与
  `run_allowed=true`。当前运行下限为 30%，正式配置为 `enable_motion=False`，所以按钮按设计
  拒绝，直到物理停止链完成验收；
- 起立与安全趴下按钮。两者只调用真机已识别的原厂动作号 `111/101`，并要求电量达标、未接
  充电线、BMS 正常、无运控错误、处于 `DOWN_WAITING/PAUSED` 且 `run_allowed=false`；趴下还
  要求 supervisor 的 `safe_to_lie_down=true` 和 `lie_down_safety_reason=ready`。浏览器执行前会
  再次要求人工确认；
- 按需开启头部 RGB 画面。UI 通过一条专用 SSH 长连接在狗上临时运行只读转码程序，将
  640×480 原始图像转为 JPEG/MJPEG；不安装文件到狗上，关闭画面后立即终止进程。源配置上限
  为 10 fps，既有 ROS 话题测量约 8.37–9.46 fps，UI 会显示实际接收帧率；
- SSH 连接信息与状态测试。

UI、姿态按钮和视频都要求电脑能 SSH 到狗；狗内置主控上的正式比赛流程不要求电脑持续在线。
断开网线、Wi-Fi 或关闭 UI 不会把比赛自治进程迁移到电脑。只有查看视频或点击人工操作时才需
要保持连接。

## XTerminal 连接

在 XTerminal 新建 SSH 主机：

| 字段 | 值 |
| --- | --- |
| 主机 | `192.168.44.1` |
| 端口 | `22` |
| 用户 | `mi` |
| 认证 | 现有密码，或导入专用私钥 `~/.ssh/mi_dog_competition_ed25519` |

连接后主机名应为 `mi-desktop`。XTerminal 是维护终端，不用于发送人工方向/速度比赛控制。
命令行也可运行：

```bash
./scripts/connect_robot.sh
```

## 无 UI 的后备命令

```bash
./scripts/competition_control.sh status
./scripts/competition_control.sh start
./scripts/competition_control.sh pause
./scripts/competition_control.sh stop
./scripts/competition_control.sh restart
./scripts/competition_control.sh --stage 4 select-stage
./scripts/competition_control.sh --stage 4 continue-stage
./scripts/robot_posture.sh stand
./scripts/robot_posture.sh lie-down
```

STOP 会锁存 `EMERGENCY_STOP`，需要重启服务才能回到 `DOWN_WAITING`；服务重启绝不自动继续。
UI 后端使用非交互式 `sudo -n`，不会弹出或保存 sudo 密码。真机已安装仓库中的
`systemd/mi-dog-competition-ui.sudoers`，只允许 `mi` 免密重启
`mi-dog-real-sensor.service`，不授予其他免密命令。2026-08-12 真机 API 验收确认重启前先
STOP，随后产生新 supervisor 进程，并最终回到 `DOWN_WAITING/run_allowed=false`。

## 故障回退

- UI 显示连接异常：先用 XTerminal 或 `connect_robot.sh` 检查 SSH，再检查直连 IP。
- `START/CONTINUE` 被拒绝：读取 `safety_reason`，修复输入后重新点击，系统不会自动放行。
- 调试移动被拒绝：不要改 YAML 绕过；先完成零速度 ABI、watchdog、暂停、重启和物理场地验收。
- 姿态按钮被拒绝：先看电量、充电状态、supervisor 状态、`run_allowed` 和趴下许可，不要绕过
  脚本的二次安全检查。
- 视频连接失败：确认狗开机且 SSH 密钥可用，再检查真实相机话题；关闭视频不影响狗上自治。
- UI 卡住：XTerminal 执行 `competition_control.sh pause` 或 `stop`；必要时按赛事允许流程重启。
