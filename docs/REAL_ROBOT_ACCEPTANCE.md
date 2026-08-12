# 真机验收矩阵

更新日期：2026-08-12。`通过` 只适用于表中明确的范围，不代表真机整场比赛完成。

| 项目 | 方法和证据 | 状态 |
| --- | --- | --- |
| 有线网络与 SSH | `192.168.44.1` 主控可登录；ROS 2 topic 可发现 | 通过 |
| ARM64 构建 | `mi_dog_real` 在狗上 Galactic/`protocol 1.0.0` 构建 | 通过 |
| 开机无运动服务 | systemd active，配置固定 `enable_motion=false` | 通过 |
| 电脑结构化操作 | `status/start/continue/pause/stop/restart`；无比赛人工运动参数 | 基础链通过 |
| 本地比赛 UI | localhost+随机令牌；状态/BMS、START/PAUSE/STOP、赛段继续和移动闭锁 | API 真机通过；限权一键重启通过 |
| 专用 SSH/XTerminal | Ed25519 批处理 status；XTerminal 可用 `mi@192.168.44.1:22` | 通过 |
| 赛段选择 | 等待/暂停态选择 1..6、持久化、重启不自动运行 | ARM64 隔离 10 项及正式 stage 2/4 流程通过 |
| 部署版本清单 | 单进程检查、实时参数、状态及关键文件 SHA256 | 通过 |
| 唤醒与 ASR | `铁蛋铁蛋` 后产生 `dog_wakeup/asr_text` | 通过 |
| 精确短口令 | `启动/恢复/暂停/终止` 映射结构化事件 | 通过 |
| 双击暂停 | `touch_state=3`，1.5 秒去重，产生 `PAUSE_TOUCH` | 通过 |
| 离线确认音 | `play_id=9000` 返回 `status=0` | 通过 |
| 在线自定义 TTS | 返回 `status=1` | 不可依赖 |
| 检查点重启 | 恢复赛段编号但状态强制 `DOWN_WAITING` | 通过 |
| START/CONTINUE 边沿门 | 不安全拒绝，恢复不自启，必须重发命令 | 隔离测试通过 |
| 实时 `run_allowed` | ESTOP、倾斜、过期、充电、运控错误撤销 | 隔离测试通过 |
| 最终运动节点许可 | missing/false/stale 停止；fresh true 隔离放行 | ARM64 隔离测试通过 |
| 急停软件守卫 | 启动、首次 false、按下/释放、超时、重连和重新解锁共 8 阶段 | ARM64 隔离测试通过 |
| USB HID 常闭输入原型 | 7 阶段仅验证 FIFO 软件逻辑；不证明外部 Type-C 可用 | 原型通过、部署撤回 |
| 四足接触桥 | RF/LF/RR/LR 约 50 Hz，趴卧/站立均观察到 0.5 | 只读通过 |
| 原始相机流 | 服务启停成功；640x480 `bgr8`，正式服务复测约 8.14 Hz | 传感器链通过 |
| 相机服务重启恢复 | 整机重启约 8.786 Hz；本服务重启后继续 `camera=1` | 通过 |
| odom 姿态备用 | ARM64 编译、隔离零输出、正式服务 `pose=1` | 只读通过 |
| 超声静态纸箱 | 0.8/0.5/0.3 m 三档数据 | 静态标定完成 |
| 超声动态避障 | 多材质、偏置、低速动态 | 未完成 |
| 头部 ToF 方向 | 官方几何与现场数据证明向下看地面 | 通过 |
| 头部 ToF 平地/黑布 | 20 帧平地和黑布数据 | 静态诊断通过 |
| 真实落差检测 | 防坠工装、几何落差 | 未完成 |
| 自动安全趴下 | 地面/空间判断并调用姿态动作 | 未实现 |
| 额外实体急停 | 用户确认赛事不要求；旧守卫/HID 不作为比赛前置条件 | 不需要 |
| Type-C 定义 | 三口为 `UDisk`、`charge`、`download`，物理插接按机身标识 | 已确认 |
| 电脑暂停/重启停止链 | PAUSE 得到 `PAUSED/false`；重启得到 `DOWN_WAITING/false` | 事件/重启通过，运动 watchdog 待测 |
| UI 调试移动闭锁 | 正式 `enable_motion=False` 时前进返回码 3；STOP 零脉冲可发送 | 通过，非零运动未批准 |
| 零速度官方时序 | 官方常量 `0/1/2`；隔离话题三轮 START→DATA，超时/撤权 END | ARM64 隔离 11 项通过；真实运控话题待工装验收 |
| 非零运动适配 | 完整安全链和停止 watchdog | 未批准 |
| 相机/定位比赛感知 | 替换 Gazebo 真值 | 未完成 |
| 六个真机赛段 | 分别物理验收 | 未开始 |
| 真机完整比赛 | 单次全程、规则、计时和终态 | 未开始 |

## 禁止把以下证据扩大解释

- 隔离话题里出现 servo data，不代表真实运动 ABI 已验收。
- `safe_to_lie_down=true` 不代表所在位置没有台阶、桥边或侧向障碍。
- 四脚接触不代表地面适合趴下。
- 黑布没有造成 ToF 失回波，因此不能替代落差。
- 用户观察“距离正确”不等于轨迹控制已标定；早期移动没有保存高精度里程计记录。
- supervisor 进入 `RUNNING` 不代表六赛段真机控制器存在。

## 每次合并前最低检查

```bash
git diff --check
python3 -m py_compile mi_dog_real/scripts/ground_tof_capture.py
python3 -m py_compile mi_dog_real/scripts/estop_guard_isolated_test.py
python3 -m py_compile mi_dog_real/scripts/estop_hid_input.py
python3 -m py_compile mi_dog_real/scripts/estop_hid_isolated_test.py
bash -n scripts/*.sh
```

修改 C++、配置、launch 或安全状态机后，还要在 ARM64 真机环境重新构建，并先使用
`/mi_dog_test/...` 隔离话题验证；正式服务最后必须回到无运动等待状态。
