#!/usr/bin/env python3
"""ContractGraph CI client. Exits 2 when a high-risk change is found."""
import argparse, json, sys, urllib.request

parser = argparse.ArgumentParser()
parser.add_argument("baseline_id"); parser.add_argument("candidate_id")
parser.add_argument("--url", default="http://localhost:8000")
args = parser.parse_args()
request = urllib.request.Request(args.url + "/v1/comparisons",
    data=json.dumps({"baseline_id":args.baseline_id,"candidate_id":args.candidate_id}).encode(),
    headers={"Content-Type":"application/json"})
with urllib.request.urlopen(request) as response:
    report = json.load(response)
print(json.dumps(report, indent=2))
sys.exit(2 if report["risk"] == "high" else 0)
