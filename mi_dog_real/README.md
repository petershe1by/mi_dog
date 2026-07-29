# `mi_dog_real`: CyberDog 2 真机适配包

这个包与 `cyberdog_autonomy`（Gazebo/LCM 仿真）完全隔离：不改 Dockerfile、不替换仿真控制器，也不把 x86 仿真镜像复制到狗上。

## 已实现的安全边界

- 默认 `enable_motion=false`：只订阅相机、雷达、IMU，绝不发布运动指令。
- 运动输出同时要求 `enable_motion=true` 和明确的 `arm_token`。
- 相机、雷达、IMU 三路数据都在 1 秒内到达，才允许转发 `/mi_dog_real/safe_cmd_vel`。
- 300 ms 指令超时、任一传感器失联时，发送官方 `motion_servo_cmd` 停止命令。
- 使用官方慢速步态 `motion_id=303`、`cmd_source=4`；限幅为前后 0.25 m/s、横移 0.10 m/s、转向 0.40 rad/s。步高采用开发者手册明确开放的 0.05 m。
- 不设置步长、机身高度或自定义跳跃高度：这些并非当前公开的稳定真机接口。跳跃只能待现场确认后调用官方预置动作。

## 首次接入（只读探测）

先由赛事方确认 CyberDog 2 的 Type-C 数据模式、官方 USB-C 网卡/转接方案、IP 和登录权限。不要按 CyberDog 1 的 `192.168.55.*` 教程操作，也不要在未确认网络前运行竞赛镜像中的 `scp_to_cyberdog.sh`。

在机器人官方 `cyberdog_ws`/ROS 2 环境中建立独立工作区后构建：

```bash
mkdir -p ~/mi_dog_ws/src
cp -a /path/to/mi_dog_real ~/mi_dog_ws/src/
cd ~/mi_dog_ws
source /opt/ros/<robot_ros_distro>/setup.bash
colcon build --packages-select mi_dog_real
source install/setup.bash
ros2 run mi_dog_real mi_dog_real_node --ros-args --params-file \
  $(ros2 pkg prefix mi_dog_real)/share/mi_dog_real/config/real_robot.yaml
```

先执行 `ros2 topic list`，确认并按实际版本覆盖 `camera_topic`、`lidar_topic`、`imu_topic`。配置默认使用开发者手册中的 `/image_rgb`、`/scan`、`/camera/imu`。确认每路 topic 均有数据、急停可用、狗已站稳并留有安全场地前，不得开启运动。

## 受控运动（现场验证后）

只有现场负责人批准后，才将 YAML 或命令行的下列两个值同时设置：

```text
enable_motion:=true
arm_token:=I_UNDERSTAND_REAL_ROBOT_RISK
```

然后由高层算法向 `/mi_dog_real/safe_cmd_vel` 发布 `geometry_msgs/Twist`。本包会限幅并将其转换为官方 `protocol/msg/MotionServoCmd`。第一轮只测试零速度、极低速直行和停止 watchdog；不运行赛道自治或跳跃。
