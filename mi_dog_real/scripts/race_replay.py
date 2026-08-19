#!/usr/bin/env python3
"""Replay JSONL observations without ROS or robot access."""
import argparse, json, pathlib
from race_mission import MissionCore, parse_observation
def main():
 ap=argparse.ArgumentParser(); ap.add_argument("input",type=pathlib.Path); ap.add_argument("--calibrated",action="store_true"); args=ap.parse_args()
 core=MissionCore(args.calibrated)
 for number,line in enumerate(args.input.read_text(encoding="utf-8").splitlines(),1):
  if not line.strip(): continue
  obs=parse_observation(line); stage=int(obs.get("stage",core.stage)); core.select_stage(stage)
  decision=core.step(obs,bool(obs.get("allowed",False)),obs.get("replay_now",obs.get("monotonic_stamp")))
  print(json.dumps({"line":number,"stage":stage,"state":decision.state,"intent":decision.intent,"linear":decision.linear,"yaw":decision.yaw,"complete":decision.complete},sort_keys=True,separators=(",",":")))
if __name__=="__main__": main()
