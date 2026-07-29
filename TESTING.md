# 2026 小米杯仿真验收矩阵

验收原则：日志状态与 Gazebo 物理现象必须同时成立；`smoke_test.sh` 只证明基础设施，不替代赛道回归。

## 最终冷启动回归

- 日期：2026-07-26（Asia/Shanghai）
- 官方基础镜像：`cyberdog_sim:v2026`
- 方案镜像：`sha256:7287d179947e975e731bfc707fefadd3f5d2d1d50489090a083503d78822c94f`
- 容器：`ca95097df251...`，无开发跳段参数，无人工运动控制
- 结果：正常 `stage 6 -> 7: football out and physical lie-down complete`；无 `deadline`
- 计时：`stage 0 -> 1` 到正常 DONE 为 800.277 秒，早于 895 秒内部截止

| 赛段 | 冷跑证据 | 状态 |
|---|---|---|
| 石径探路 | 四块石板实体门控 `(1.124,-.005)`、`(1.624,.230)`、`(2.122,-.002)`、`(2.625,-.027)`；右侧合法开口 `x=2.928`；`stage 1 -> 2` 1785065795.387 | 通过 |
| 荒野寻珠 | `orange bump 1/4` 至 `4/4`；`stage 2 -> 3` 1785065971.137 | 通过 |
| 曲道冲锋 | 中心线路径完成；`stage 3 -> 4` 1785065993.182 | 通过 |
| 深隧寻珍 | 两根限高杆、可乐、借道、悬挂球和语音动作齐全；足球2 `(2.114,11.457)` 入门；`stage 4 -> 5` 1785066343.348 | 通过 |
| 孤梁稳渡 | 全足登桥、四足越线后跳下；`stage 5 -> 6` 1785066390.431 | 通过 |
| 撷金建功 | 足球3 `y=13.119` 判定越界；`z=0.180` 后 pure-damper；`stage 6 -> 7` 1785066562.805 | 通过 |
| 总体 | 单个冷容器、完整 `0→7`、800.277 秒、无 deadline | 通过 |

## 第一关几何验收

官方 STL 世界坐标：四块石板分别为 `x=.592..892`、`1.092..1.392`、`1.592..1.892`、`2.092..2.392`，共同位于 `y=-.519...481`。黄实线横跨 `x=-.627..2.773、y=.482...592`，合法开口在右侧。控制器要求机身中心越过每块末端并留后腿余量，第四块后到 `x>2.88` 才允许向北转弯。

旧镜像 `sha256:011fe01b...` 在 `(2.0,0.0)` 提前转向并跨实线，其完成结论已撤销。

## 最终物理终态

```text
robot: x=2.217 y=13.320 z=0.054（完成圈内稳定趴下）
football3 final: x=4.187 y=13.088（越过内场边界 y=13.12）
football2 scoring event: x=2.114 y=11.457
```

## 基础设施与复现

```bash
./scripts/smoke_test.sh
bash -n scripts/build_image.sh scripts/run_race.sh scripts/smoke_test.sh scripts/start_sim.sh
./scripts/build_image.sh
./scripts/run_race.sh
docker logs -f mi-dog-race
```

烟雾测试最终输出：`PASS: container, Gazebo, controller, autonomy, lidar, camera and audio assets`。正式验收必须删除并重建容器，不使用 `/reset_world`。
