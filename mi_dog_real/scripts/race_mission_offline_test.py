#!/usr/bin/env python3
import importlib.util, pathlib
p=pathlib.Path(__file__).with_name("race_mission.py")
s=importlib.util.spec_from_file_location("race_mission",p); m=importlib.util.module_from_spec(s); s.loader.exec_module(m)
now=100.; core=m.MissionCore(False)
obs={"schema":m.OBSERVATION_SCHEMA,"monotonic_stamp":now,"localization_confidence":.9,"front_clearance_m":2.,"heading_error_rad":.1,"course_pose":[.5,.5,0.],"facts":{}}
assert core.step(obs,True,now).state=="COURSE_UNCALIBRATED"
core=m.MissionCore(True)
configured=m.MissionCore(True,stage_speeds=(.4,.08,.09,.08,.06,.12))
assert configured.step(obs,True,now).linear==.4
assert core.step(None,True,now).state=="PERCEPTION_MISSING"
assert core.step(dict(obs,monotonic_stamp=90.),True,now).state=="PERCEPTION_STALE"
assert core.step(dict(obs,localization_confidence=.2),True,now).state=="LOCALIZATION_UNCERTAIN"
assert core.step(dict(obs,front_clearance_m=.2),True,now).linear==0
core.select_stage(2)
turning=core.step(dict(obs,front_clearance_m=.2),True,now)
assert turning.state=="RUNNING" and turning.linear==0 and turning.yaw>0
aligned_pose=[3.7,1.3,2.2753]
assert core.step(dict(obs,front_clearance_m=.2,course_pose=aligned_pose),True,now).linear > 0
assert core.step(dict(obs,front_clearance_m=.1),True,now).linear == 0
assert core.step(dict(obs,facts={"unknown":True}),True,now).state=="PERCEPTION_INVALID"
assert core.step(dict(obs,facts={"stones_passed":"4"}),True,now).state=="PERCEPTION_INVALID"
facts_by_stage={
1:{"stones_passed":4,"exit_crossed":True},
2:{"exit_crossed":True},
3:{"lane_valid":True,"exit_crossed":True},
4:{"coke_down":True,"stage4_orange_touched":True,"football_scored":True,"lowbars_passed":2,"obstacle_bypassed":True,"bridge_contact":True},
5:{"bridge_aligned":True,"all_feet_on_bridge":True,"all_feet_past_line":True,"landed":True},
6:{"football_out":True,"feet_in_finish":4,"stopped":True,"lie_down_complete":True}}
for stage in range(1,7):
 core.select_stage(stage)
 stage_obs=dict(obs,course_pose=aligned_pose) if stage==2 else obs
 running=core.step(stage_obs,True,now); assert running.state=="RUNNING" and running.linear>0
 completed=core.step(dict(obs,facts=facts_by_stage[stage]),True,now); assert completed.complete and completed.linear==0
 assert not core.step(dict(obs,facts=facts_by_stage[stage]),True,now).complete
t=m.CourseTransform(1.,2.,0.,True); assert t.to_odom(3.,4.)==(4.,6.)
try: m.CourseTransform().to_odom(0,0); raise AssertionError("invalid transform accepted")
except ValueError: pass
try: m.parse_observation('{"schema":"wrong","facts":{}}'); raise AssertionError("bad schema accepted")
except ValueError: pass
print("race_mission_six_stage=PASS")
print("race_mission_fail_closed=PASS")
print("race_mission_checkpoint=PASS")
