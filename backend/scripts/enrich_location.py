# -*- coding: utf-8 -*-
"""building_age.json 각 동에 역거리(직선·도보추정)·평균경사 추가.
- 역 좌표: frontend/src/data/subwayLines.js 에서 추출
- 경사: backend/data/apartments.db 의 slope 동별 평균
"""
import sys, re, json, math, sqlite3
sys.stdout.reconfigure(encoding="utf-8")
from pathlib import Path

ROOT = Path(__file__).parent.parent
FRONT = ROOT.parent / "frontend" / "src" / "data" / "subwayLines.js"

GU2SGG = {
    "종로구":"11110","중구":"11140","용산구":"11170","성동구":"11200","광진구":"11215",
    "동대문구":"11230","중랑구":"11260","성북구":"11290","강북구":"11305","도봉구":"11320",
    "노원구":"11350","은평구":"11380","서대문구":"11410","마포구":"11440","양천구":"11470",
    "강서구":"11500","구로구":"11530","금천구":"11545","영등포구":"11560","동작구":"11590",
    "관악구":"11620","서초구":"11650","강남구":"11680","송파구":"11710","강동구":"11740",
}

# 1) 역 좌표 추출 ([37.x, 126.x, '이름'])
txt = FRONT.read_text(encoding="utf-8")
stations = [(float(la), float(ln)) for la, ln in
            re.findall(r"\[\s*(3[0-9]\.\d+)\s*,\s*(12[0-9]\.\d+)\s*,", txt)]
print("추출된 역 좌표:", len(stations))

def haversine(a, b):
    R = 6371000
    dla = math.radians(b[0]-a[0]); dln = math.radians(b[1]-a[1])
    h = math.sin(dla/2)**2 + math.cos(math.radians(a[0]))*math.cos(math.radians(b[0]))*math.sin(dln/2)**2
    return int(R*2*math.asin(math.sqrt(h)))

def nearest_station(lat, lng):
    return min(haversine((lat, lng), s) for s in stations)

# 2) 동별 평균 경사 (apartments.db)
con = sqlite3.connect(ROOT / "data" / "apartments.db")
slope_map = {}
for lawd, dong, avg in con.execute(
        "SELECT lawd_cd, dong, AVG(slope) FROM apartments WHERE slope IS NOT NULL AND slope>0 GROUP BY lawd_cd, dong"):
    slope_map[(str(lawd), dong)] = round(avg, 1)
con.close()
print("경사 데이터 동수:", len(slope_map))

# 3) building_age.json 보강
fp = ROOT / "data" / "building_age.json"
data = json.loads(fp.read_text(encoding="utf-8"))
nfill = sfill = 0
for d in data["dongs"]:
    if d.get("lat") and d.get("lng"):
        dist = nearest_station(d["lat"], d["lng"])
        d["station_dist"] = dist                       # 직선 m
        d["walk_min"] = round(dist * 1.3 / 80)         # 도보 분(보정 1.3배, 분당 80m)
        nfill += 1
    sgg = GU2SGG.get(d.get("gu"))
    sl = slope_map.get((sgg, d.get("dong")))
    if sl is not None:
        d["avg_slope"] = sl; sfill += 1
    else:
        d["avg_slope"] = None

fp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
print(f"역거리 채움 {nfill} / 경사 채움 {sfill} / 전체 {len(data['dongs'])}")
# 샘플
for gu, dong in [("영등포구","문래동4가"),("용산구","남영동"),("서대문구","봉원동")]:
    x = [a for a in data["dongs"] if a["gu"]==gu and a["dong"]==dong]
    if x: x=x[0]; print(f"  {gu} {dong}: 역 {x['station_dist']}m(도보 {x['walk_min']}분) 경사 {x['avg_slope']}")
