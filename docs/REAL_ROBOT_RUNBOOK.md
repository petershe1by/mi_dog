# CyberDog 2 真机操作手册

适用范围：当前默认无运动的传感器、语音、触摸和 supervisor 服务。

当前禁止：设置 `enable_motion=true`、充电时执行姿态动作、直接运行整场自治。

## 现场角色与环境

- 一人负责电脑和口令，一人靠近独立急停；未完成独立急停验收前不做非零运动。
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

## 语音操作

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

- 普通暂停：说“暂停”或头部双击，确认状态变为 `PAUSED`、许可为 false。
- 恢复：先确认环境安全，再说“铁蛋铁蛋—恢复”；不安全时系统应拒绝。
- 严重故障：说“终止”只能作为软件停止；真实运动测试必须使用独立急停。
- 重启：服务读取赛段编号，但强制回到 `DOWN_WAITING`，不会自动继续。

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

## 收尾

1. 确认状态不是 `RUNNING`，`run_allowed=false`。
2. 确认狗处于稳定趴卧；自动趴下未实现时由已验收的人工/官方流程处理。
3. 导出 `journalctl`、测试命令、版本和配置哈希。
4. 若需要关机，使用设备官方关机方式；不要直接拔主电源。
5. 在 [工作记录](WORKLOG.md) 中写明最终姿态、是否充电、异常及下一步。
