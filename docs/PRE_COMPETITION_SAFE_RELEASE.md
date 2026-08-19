# 比赛前真机安全版部署与回滚清单

冻结日期：2026-08-18。此清单描述源码提交和部署包的边界；比赛模式仍须在场地参数标定、只读
预检通过后由操作员显式切换，发布冻结本身不得切换服务或发送运动指令。

## 发布内容

- `mi_dog_real`：安全适配器、Supervisor、状态桥、比赛控制器、maintenance/competition launch，
  以及前向净空过滤的单元测试。
- `scripts`：服务启动、延迟相机验证、比赛预检、只读审计、姿态安全门和本地 UI 后端。
- `ui`：START/STOP、状态、姿态、低速调试脉冲和 RGB 视频界面。
- `systemd/mi-dog-real-sensor.service`：默认 maintenance 启动，重启后保持
  `DOWN_WAITING/run_allowed=false`。
- `docs/evidence`：已执行的 watchdog、许可超时、活动 STOP/重启、单次 END、断开电脑及六方向
  低速真机证据。

明确排除：ROS/colcon 构建产物、日志、bag、私钥、口令、UI 一次性运行令牌和任何原厂运控目录。

## 部署顺序

1. 校验源码提交和回滚包 SHA256；确认工作树干净。
2. 复制 `mi_dog_real` 源码、`scripts` 和 systemd unit；在 ARM64 主控构建。
3. 保持 unit 的 `ExecStart=... run_sensor_gate.sh maintenance`，不得在部署时改为 competition。
4. 只重启本项目 unit；确认 `active`、`NRestarts=0`、三种 maintenance 节点各一份，且不存在
   `race_controller.py` 与 `mi_dog_estop_guard_node` 进程。
5. 只读确认 `DOWN_WAITING` 或 `EMERGENCY_STOP`、`run_allowed=false`、空闲 Servo 消息为零。
6. 用 `capture_deployment_manifest.sh --source-commit COMMIT` 生成 schema v3 清单并保存 SHA256。

## 回滚

回滚包由 `scripts/create_rollback_bundle.sh --source-commit COMMIT` 按白名单生成，必须包含源码树、
工作区脚本、systemd unit、安装树和生成时的 `SHA256SUMS`；归档外另有 `.sha256`。恢复时先保持
STOP，解包到临时目录并校验哈希，再按清单逐项安装；默认恢复 maintenance。若安全状态或哈希
不一致，改用 `sensor_only.launch.py` 的 `enable_motion=false` 路径，不得启动 competition。

回滚完成的接受条件与部署相同：项目服务 active、无重复节点、无比赛控制器、
`run_allowed=false`、空闲 Servo 零消息。回滚不授权任何姿态或运动测试。

## 已完成的无运动验证

- Python 语法、Shell 语法和 `git diff --check` 通过。
- 比赛控制器离线六赛段、失效闭锁和 `course_calibrated=false` 默认门通过。
- UI 离线回归通过：比赛模式拒绝手动控制、并发写返回 409、STOP 可抢占锁、超时清理进程组。
- 机器狗只读确认 maintenance active、`NRestarts=0`、三节点单实例、无比赛控制器。

最终提交号、部署清单路径、回滚包路径及各自 SHA256 在提交完成后作为外部发布证据记录，避免把
压缩二进制包提交进 Git。
