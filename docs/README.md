# 文档导航

本目录是项目交接入口。首次接手请按下面顺序阅读，避免把 Gazebo 方案直接部署到真机，
或把尚未验收的候选阈值当作运动许可。

1. [项目交接总览](PROJECT_HANDOFF.md)：目标、当前状态、已完成内容、阻塞项和接手步骤。
2. [架构与文件地图](ARCHITECTURE_AND_FILE_MAP.md)：数据流、节点职责、接口和每个文件的位置。
3. [真机操作手册](REAL_ROBOT_RUNBOOK.md)：联网、开机检查、电脑启动/暂停/重启、日志和关机。
4. [比赛控制 UI](COMPETITION_UI.md)：默认比赛模式、一键操作、维护控制安全门和 XTerminal/SSH。
5. [组委会确认单](ORGANIZER_CONFIRMATION.md)：电脑操作、端口、离线架构及待确认恢复细节的记录。
6. [比赛日流程](COMPETITION_DAY_CHECKLIST.md)：规则操作边界、一键启动结论和待填官方日程。
7. [待完成真机测试清单](PENDING_REAL_ROBOT_TESTS.md)：需要补测、尚未实现和现场确认的可勾选任务。
8. [真机测试数据](REAL_ROBOT_TEST_DATA.md)：全部保留下来的测量值、测试条件和证据等级。
9. [真机验收矩阵](REAL_ROBOT_ACCEPTANCE.md)：已经通过、部分通过和禁止执行的测试门。
10. [工作记录](WORKLOG.md)：从仿真到真机的时间线、关键决策和 Git 提交。
11. [路线图](ROADMAP.md)：最终目标、下一步、完成条件和安全顺序。

现有专题文档：

- [仿真验收矩阵](../TESTING.md)
- [真机一键只读审计](../scripts/robot_read_only_audit.sh)
- [真机部署检查点](../REAL_ROBOT_DEPLOYMENT.md)
- [比赛暂停与恢复设计](../RACE_RECOVERY_DESIGN.md)
- [真机 ROS 2 包说明](../mi_dog_real/README.md)
- [赛事题目与规则解析](../extracted/)

## 文档事实规则

- “通过”必须有日志、话题或物理现象证据；操作者主观观察单独标注。
- “候选阈值”不等于已经接入运动链。
- 当前维护/比赛适配器为 motion-enabled，但 Supervisor 默认保持 `DOWN_WAITING/false`；比赛
  控制器额外以 `course_calibrated=false` 默认闭锁。sensor-only launch 仍是失能回滚路径。
- 未在本仓库保存原始日志的数据会明确写为“未留存”，不补造精度或统计量。
- 变更代码、配置或真机部署后，必须同时更新交接总览、验收矩阵和工作记录。
