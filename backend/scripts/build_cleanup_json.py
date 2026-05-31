"""cleanup_seoul.xls → cleanup_projects.json (compare에서 빠르게 로드)"""
import sys, json, re
sys.stdout.reconfigure(encoding='utf-8')
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).parent.parent
df = pd.read_excel(ROOT/"data"/"cleanup_seoul.xls", header=1)
df.columns = ["no","gu","type","name","jibun","stage","o1","o2","c1","c2","c3"]

def dong_of(jibun):
    if not isinstance(jibun, str): return ""
    m = re.match(r"([가-힣0-9]+동(?:\d+가)?)", jibun.strip())
    return m.group(1) if m else ""

out = []
for _, r in df.iterrows():
    if not isinstance(r["gu"], str): continue
    out.append({
        "gu": r["gu"],
        "type": str(r["type"]),
        "name": re.sub(r"^\d+\.\s*", "", str(r["name"])).strip(),
        "dong": dong_of(r["jibun"]),
        "jibun": str(r["jibun"]),
        "stage": str(r["stage"]) if isinstance(r["stage"], str) else "",
    })
(ROOT/"data"/"cleanup_projects.json").write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
print(f"저장: {len(out)}건 → cleanup_projects.json")
