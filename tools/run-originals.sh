#!/bin/sh
# Sends the three raw takes through the running service, one after another
cd "$(dirname "$0")/.." || exit 1
for f in IMG_7821 IMG_7824 IMG_7811; do
  start=$(date +%s)
  name=$(curl -s -X POST -T media/$f.MOV http://127.0.0.1:8787/api/new/$f.MOV | python3 -c 'import json,sys;print(json.load(sys.stdin)["project"])')
  while :; do sleep 5; s=$(curl -s http://127.0.0.1:8787/api/projects/$name); echo "$s" | python3 -c 'import json,sys;d=json.load(sys.stdin);sys.exit(0 if not d["busy"] and d["steps"] else 1)' && break; done
  echo "$s" | python3 -c 'import json,sys;d=json.load(sys.stdin);print(d["name"], [(s["step"],s["state"],s.get("seconds"),s.get("error")) for s in d["steps"]], "words",len(d.get("words",[])), "video s",d.get("seconds"), "beats",[b["kind"] for b in d.get("beats",[])], "needs",[n["what"] for n in d.get("needs",[])])'
  echo "$name total $(( $(date +%s) - start )) s"
done
