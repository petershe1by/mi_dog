# 工作站迁移指南

更新日期：2026-08-21（Asia/Shanghai）

本文说明如何把本项目迁移到另一台 Windows/WSL2 调试电脑。迁移分为三个独立对象：

1. Git 工作树：源码、配置、文档、测试和提交历史。
2. Docker 仿真镜像：`cyberdog_sim:v2026` 基础镜像及可选的派生镜像。
3. 电脑端访问能力：新电脑自己的 SSH 密钥和直连机器狗的以太网配置。

机器人内部的 `/home/mi/mi_dog_ws`、systemd 服务和运行状态仍保存在机器人上，不属于电脑迁移。
不得从新电脑用较旧仓库直接覆盖机器人。

## 一、迁移前冻结与检查

在旧电脑 WSL 中进入仓库：

```bash
cd "/mnt/e/Competitions during college/mi_dog/solution"
git status --short
git log -1 --oneline --decorate
git diff --check
```

正式迁移应尽量从一个已提交且测试通过的工作树开始。若仍有未提交内容，不要使用
`git archive` 或只执行 `git clone`，因为两者都不会保存未提交和未跟踪文件。

确认仓库中没有私钥、口令、UI 临时令牌、ROS bag、日志或 Docker tar。`.gitignore` 已排除常见
运行产物，但提交前仍需查看 `git status --short`。

真机源代码配置必须保持 fail-closed：

- `course_perception.yaml` 中 `site_transform_valid: false`；
- `race_controller.yaml` 中 `course_calibrated: false`；
- 仓库不能保存某次开机的有效 odom 原点；
- `max_enabled_stage` 只是物理验收上限，不能代替课程标定门。

## 二、推荐方案：Git 提交加离线源码快照

提交完成后，若允许使用现有远端，可执行：

```bash
git remote -v
git push origin main
```

若远端仓库包含非公开竞赛资料或现场信息，先确认仓库可见性，不要把私有内容推送到公开仓库。

即使已经推送 Git，也建议制作一份包含 `.git` 的离线快照：

```bash
mkdir -p /mnt/e/mi_dog_transfer
cd "/mnt/e/Competitions during college/mi_dog"

tar \
  --exclude='solution/build' \
  --exclude='solution/install' \
  --exclude='solution/log' \
  -czf /mnt/e/mi_dog_transfer/mi_dog_solution.tar.gz \
  solution

cd /mnt/e/mi_dog_transfer
sha256sum mi_dog_solution.tar.gz > mi_dog_solution.sha256
```

快照放在仓库目录之外，避免把压缩包递归打包或提交到 Git。将压缩包与校验文件一起复制到移动
硬盘或受控共享目录。

## 三、迁移 Docker 仿真镜像

Dockerfile 以本地基础镜像 `cyberdog_sim:v2026` 为起点。只复制源码而没有该镜像，新电脑无法
重建 Gazebo 环境。

旧电脑检查镜像：

```bash
docker image inspect cyberdog_sim:v2026 \
  --format '{{.Id}} {{.Architecture}} {{.Size}}'
docker image inspect mi-dog-solution:latest \
  --format '{{.Id}} {{.Architecture}} {{.Size}}'
```

导出基础镜像：

```bash
docker save \
  -o /mnt/e/mi_dog_transfer/cyberdog_sim_v2026.tar \
  cyberdog_sim:v2026

sha256sum /mnt/e/mi_dog_transfer/cyberdog_sim_v2026.tar \
  > /mnt/e/mi_dog_transfer/cyberdog_sim_v2026.sha256
```

可选导出已构建派生镜像：

```bash
docker save \
  -o /mnt/e/mi_dog_transfer/mi_dog_solution_latest.tar \
  mi-dog-solution:latest
```

镜像可能很大；导出前确认目标盘空间。Docker Desktop 的镜像数据不一定包含在普通 Ubuntu WSL
导出中，因此镜像 tar 应单独保存。

## 四、可选：导出整个 WSL 发行版

需要最大程度复现旧电脑的 Linux 包和工具时，在 Windows PowerShell 中执行：

```powershell
wsl --list --verbose
wsl --shutdown
wsl --export Ubuntu-22.04 E:\mi_dog_transfer\ubuntu2204-mi-dog.tar
```

新电脑导入：

```powershell
wsl --import Ubuntu-mi-dog D:\WSL\Ubuntu-mi-dog `
  E:\mi_dog_transfer\ubuntu2204-mi-dog.tar --version 2
wsl -d Ubuntu-mi-dog
```

注意：WSL 导出不包含 `/mnt/e` 这类 Windows 挂载盘内容，所以项目源码仍必须用 Git 或第二节的
压缩包迁移；Docker Desktop 镜像也仍建议按第三节单独导出。

## 五、新电脑基础环境

推荐环境：Windows 11、WSL2、Ubuntu 22.04、Docker Desktop 和 Git。管理员 PowerShell：

```powershell
wsl --install -d Ubuntu-22.04
```

在 Docker Desktop 中为目标 Ubuntu 发行版启用 WSL Integration。新电脑 WSL 中确认：

```bash
uname -m
git --version
docker version
python3 --version
ssh -V
```

仿真镜像为 x86_64；不要把它复制到 CyberDog 2 ARM64 主控。

## 六、恢复源码和镜像

为了兼容已有文档和操作命令，建议恢复到同一路径：

```text
E:\Competitions during college\mi_dog\solution
```

使用离线快照时：

```bash
mkdir -p "/mnt/e/Competitions during college/mi_dog"
cd /mnt/e/mi_dog_transfer
sha256sum -c mi_dog_solution.sha256

tar -xzf mi_dog_solution.tar.gz \
  -C "/mnt/e/Competitions during college/mi_dog"
```

或者从已经推送的 Git 远端恢复：

```bash
mkdir -p "/mnt/e/Competitions during college/mi_dog"
cd "/mnt/e/Competitions during college/mi_dog"
git clone https://github.com/petershe1by/mi_dog.git solution
```

恢复 Docker 基础镜像：

```bash
cd /mnt/e/mi_dog_transfer
sha256sum -c cyberdog_sim_v2026.sha256
docker load -i cyberdog_sim_v2026.tar
```

若没有迁移派生镜像，在仓库中重建：

```bash
cd "/mnt/e/Competitions during college/mi_dog/solution"
./scripts/build_image.sh
```

## 七、为新电脑单独配置机器人 SSH 密钥

不要复制或提交旧电脑的私钥。新电脑应生成自己的专用密钥：

```bash
cd "/mnt/e/Competitions during college/mi_dog/solution"
./scripts/setup_robot_ssh_key.sh
```

默认密钥路径为 `~/.ssh/mi_dog_competition_ed25519`。脚本会调用 `ssh-copy-id`，首次需要输入一次
机器人账户密码。若现场不允许密码登录，可在旧电脑仍可连接时，把新电脑的 `.pub` 公钥交给旧
电脑管理员，通过已有授权追加到机器人 `~/.ssh/authorized_keys`。只能传公钥，不能通过聊天、
Git 或普通共享目录传私钥。

权限必须为：

```bash
chmod 700 ~/.ssh
chmod 600 ~/.ssh/mi_dog_competition_ed25519
chmod 644 ~/.ssh/mi_dog_competition_ed25519.pub
```

## 八、直连网络配置

当前验证地址为机器人 `192.168.44.1/24`、账户 `mi`。可将新电脑专用以太网口手动设置为未
占用的同网段地址，例如：

```text
IP：192.168.44.100
掩码：255.255.255.0
网关：留空
DNS：留空
```

不要把电脑设置成 `192.168.44.1`。测试：

```bash
ping -c 3 192.168.44.1

MI_DOG_SSH_IDENTITY="$HOME/.ssh/mi_dog_competition_ed25519" \
  ./scripts/connect_robot.sh hostname
```

## 九、新电脑首次验收

先做本地离线检查：

```bash
cd "/mnt/e/Competitions during college/mi_dog/solution"
git status --short
git log -1 --oneline --decorate
git diff --check

PYTHONDONTWRITEBYTECODE=1 python3 mi_dog_real/scripts/race_controller_offline_test.py
PYTHONDONTWRITEBYTECODE=1 python3 mi_dog_real/scripts/race_mission_offline_test.py
PYTHONDONTWRITEBYTECODE=1 python3 mi_dog_real/scripts/course_perception_offline_test.py
python3 scripts/capture_course_origin.py --self-test
```

第一次连接机器人只运行只读审计：

```bash
./scripts/robot_read_only_audit.sh \
  --target mi@192.168.44.1 \
  --identity "$HOME/.ssh/mi_dog_competition_ed25519"
```

读取比赛状态：

```bash
MI_DOG_SSH_IDENTITY="$HOME/.ssh/mi_dog_competition_ed25519" \
MI_DOG_SSH_BATCH_MODE=1 \
  ./scripts/competition_control.sh --target mi@192.168.44.1 status
```

验收前不得发送 `start`、`continue`、姿态或手动运动命令。至少确认：服务 active、目标主机正确、
关键节点单实例、监督器许可为 false、空闲 Servo 为零帧、电源正常且未充电。

## 十、UI 与仿真验证

启动本地比赛 UI：

```bash
MI_DOG_SSH_IDENTITY="$HOME/.ssh/mi_dog_competition_ed25519" \
  ./scripts/start_competition_ui.sh
```

UI 默认绑定本机回环地址；不要为了迁移测试直接暴露到公网。公网访问必须使用独立认证代理和受控
隧道，并保持内网 UI 可用。

仿真冷启动验证：

```bash
./scripts/run_race.sh
docker logs -f mi-dog-race
./scripts/smoke_test.sh
```

正式回归必须冷启动，不使用 `/reset_world` 替代。

## 十一、现场标定与部署边界

电脑迁移不会迁移有效课程标定。机器狗整机重启后 odom 零点可能变化，因此旧的
`site_origin_x_m`、`site_origin_y_m` 和 `site_origin_yaw_rad` 不得复用。

标定时将机器狗身体几何中心放在图纸坐标 `(0.50, 0.50)`，朝场地 `+x`，保持静止，然后在机器
狗实际 ROS/DDS 环境中运行 `scripts/capture_course_origin.py`。至少核对采样数量、位置抖动和航向
抖动；写入配置后仍需现场方向验证。只有完成授权赛段的物理验收，才可同时解除
`site_transform_valid` 和 `course_calibrated` 门。

当前雷达+里程计降级模式不以 RGB 新鲜度作为赛段一二运动门，但无法可靠区分和播报橙色球。
不得把该模式描述为完整视觉比赛验收。`max_enabled_stage: 2` 会在监督器进入第三赛段时输出零速，
三至六赛段未验收前不得提高。

## 十二、迁移完成判定

以下项目全部通过后，才算新电脑接手完成：

- 源码压缩包和 Docker 镜像 SHA256 校验通过；
- Git HEAD 与预期提交一致，工作树状态已解释；
- 三组离线控制器/感知测试通过；
- `capture_course_origin.py --self-test` 通过；
- 新电脑使用自己的 SSH 密钥连接成功；
- 机器人只读审计通过或每一项失败均已解释；
- 未向机器人部署旧文件，未发送 START、CONTINUE 或人工运动；
- UI 本地只读状态可用；
- 需要仿真时，基础镜像可加载且冷启动流程可运行。

迁移后的第一次真实运动仍属于新的现场验收，不因电脑、源码和 Docker 已成功迁移而自动获准。
