import json, glob, sys

seed = sys.argv[1] if len(sys.argv) > 1 else "7"   # python Summarize.py <seed>
paths = sorted(glob.glob(f"cache/seed{seed}_tick_*.json"), key=lambda p: int(p.split("_")[-1][:-5]))
for p in paths:
    with open(p, encoding="utf-8") as f:
        log = json.load(f)
    acts = [f'{a["tool"]}({", ".join(map(str, a["input"].values()))})'
            for a in log["actions"] if not a["tool"].startswith("get_")]
    print(log["tick"], acts or "no action", "|", log["explanation"][:150])