#!/usr/bin/env python3
"""Dependency-free real-course mission, localization and replay contracts."""
import json, math, time
from collections import namedtuple

Decision = namedtuple("Decision", "linear yaw complete state intent")
STAGE_NAMES = ("stone", "balls", "curve", "search", "bridge", "finish")
REQUIRED = {
  1: ("stones_passed:4", "exit_crossed"),
  2: ("orange_touched:4", "exit_crossed"),
  3: ("lane_valid", "exit_crossed"),
  4: ("coke_down", "stage4_orange_touched", "football_scored", "lowbars_passed:2",
      "obstacle_bypassed", "bridge_contact"),
  5: ("bridge_aligned", "all_feet_on_bridge", "all_feet_past_line", "landed"),
  6: ("football_out", "feet_in_finish:4", "stopped", "lie_down_complete"),
}
OBSERVATION_SCHEMA = "mi_dog_course_observation_v1"
COUNT_FACTS = {"stones_passed", "orange_touched", "lowbars_passed", "feet_in_finish"}
BOOL_FACTS = {
  "exit_crossed", "lane_valid", "coke_down", "stage4_orange_touched", "football_scored",
  "obstacle_bypassed", "bridge_contact", "bridge_aligned",
  "all_feet_on_bridge", "all_feet_past_line", "landed", "football_out",
  "stopped", "lie_down_complete",
}

def finite(value): return isinstance(value, (int, float)) and math.isfinite(value)

class CourseTransform:
    def __init__(self, ox=0.0, oy=0.0, yaw=0.0, valid=False):
        if not all(finite(v) for v in (ox, oy, yaw)): raise ValueError("non-finite transform")
        self.ox, self.oy, self.yaw, self.valid = ox, oy, yaw, bool(valid)
    def to_odom(self, x, y):
        if not self.valid: raise ValueError("site transform not calibrated")
        c, s = math.cos(self.yaw), math.sin(self.yaw)
        return self.ox + c*x-s*y, self.oy+s*x+c*y

class MissionCore:
    def __init__(self, course_calibrated=False, timeout=0.6, min_localization=0.65):
        self.course_calibrated=bool(course_calibrated); self.timeout=float(timeout)
        self.min_localization=float(min_localization); self.stage=1; self.completed=set()
        self.checkpoint={"stage":1,"facts":{},"updated":0.0}
    def select_stage(self, stage):
        if stage not in range(1,7): raise ValueError("stage must be 1..6")
        self.stage=stage; self.checkpoint["stage"]=stage
    @staticmethod
    def _satisfied(facts, requirement):
        if ":" in requirement:
            key, count=requirement.split(":",1); return int(facts.get(key,0)) >= int(count)
        return facts.get(requirement) is True
    def step(self, observation, allowed=True, now=None):
        now=time.monotonic() if now is None else now
        if not self.course_calibrated: return Decision(0.,0.,False,"COURSE_UNCALIBRATED","STOP")
        if not allowed: return Decision(0.,0.,False,"INHIBITED","STOP")
        if not isinstance(observation,dict): return Decision(0.,0.,False,"PERCEPTION_MISSING","STOP")
        stamp=observation.get("monotonic_stamp")
        if not finite(stamp) or now-stamp < -0.05 or now-stamp > self.timeout:
            return Decision(0.,0.,False,"PERCEPTION_STALE","STOP")
        confidence=observation.get("localization_confidence",0.)
        if not finite(confidence) or confidence < self.min_localization:
            return Decision(0.,0.,False,"LOCALIZATION_UNCERTAIN","STOP")
        facts=observation.get("facts",{})
        if not isinstance(facts,dict): return Decision(0.,0.,False,"PERCEPTION_INVALID","STOP")
        for key,value in facts.items():
            if key in COUNT_FACTS:
                if isinstance(value,bool) or not isinstance(value,int) or value < 0:
                    return Decision(0.,0.,False,"PERCEPTION_INVALID","STOP")
            elif key in BOOL_FACTS:
                if not isinstance(value,bool):
                    return Decision(0.,0.,False,"PERCEPTION_INVALID","STOP")
            else:
                return Decision(0.,0.,False,"PERCEPTION_INVALID","STOP")
        self.checkpoint={"stage":self.stage,"facts":dict(facts),"updated":now}
        done=all(self._satisfied(facts,r) for r in REQUIRED[self.stage])
        if done:
            first=self.stage not in self.completed; self.completed.add(self.stage)
            return Decision(0.,0.,first,"STAGE_COMPLETE","STOP")
        front=observation.get("front_clearance_m")
        if not finite(front) or front <= 0.35: return Decision(0.,0.,False,"BLOCKED","AVOID")
        heading=observation.get("heading_error_rad",0.)
        if not finite(heading): return Decision(0.,0.,False,"PERCEPTION_INVALID","STOP")
        intent=("FOLLOW_STONES","SEARCH_ORANGE","FOLLOW_LANE","SEARCH_OBJECTS",
                "CROSS_BRIDGE","FINISH_TASKS")[self.stage-1]
        speed=(.08,.06,.07,.05,.04,.06)[self.stage-1]
        return Decision(speed,max(-.20,min(.20,heading*.7)),False,"RUNNING",intent)
    def snapshot(self): return json.dumps(self.checkpoint,sort_keys=True,separators=(",",":"))

def parse_observation(line):
    value=json.loads(line)
    if not isinstance(value,dict): raise ValueError("observation must be object")
    if value.get("schema") != OBSERVATION_SCHEMA: raise ValueError("observation schema mismatch")
    return value
