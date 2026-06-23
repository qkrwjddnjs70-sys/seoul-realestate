# -*- coding: utf-8 -*-
"""동별 노후도 계산 → 재개발 후보 예측 데이터.
건축물대장(국토부) API로 법정동별 모든 건물의 사용승인일·구조·용도를 받아
노후도(노후·불량 건축물 비율)를 계산한다. 서울 조례 기준:
  - 노후: 철근콘크리트/철골 30년+, 그 외(벽돌/조적/기타) 20년+
  - 재개발 요건: 노후도 60%+
사용: python enrich_building_age.py 11560   # 영등포구
"""
import sys, json, time
sys.stdout.reconfigure(encoding="utf-8")
import httpx
from pathlib import Path
from dotenv import dotenv_values

ROOT = Path(__file__).parent.parent
env = dotenv_values(ROOT / ".env")
KEY = env.get("PUBLIC_DATA_KEY_DECODED")
KAKAO = env.get("KAKAO_REST_KEY")
URL = "https://apis.data.go.kr/1613000/BldRgstHubService/getBrTitleInfo"
YEAR = 2026
SGG = sys.argv[1] if len(sys.argv) > 1 else "11560"  # 영등포구

def fetch_dong(sgg, bjd):
    out = []
    page = 1
    name = ""
    while True:
        try:
            r = httpx.get(URL, params={"serviceKey": KEY, "sigunguCd": sgg, "bjdongCd": bjd,
                "numOfRows": "100", "pageNo": str(page), "_type": "json"}, timeout=30)
            j = r.json()
            body = j["response"]["body"]
        except Exception:
            break
        total = int(body.get("totalCount", 0) or 0)
        if total == 0:
            return None, []
        items = body.get("items")
        it = items.get("item", []) if items else []
        if isinstance(it, dict):
            it = [it]
        for x in it:
            if not name:
                plc = x.get("platPlc", "")
                # "서울특별시 영등포구 문래동4가 ..." → 동명 추출
                parts = plc.split()
                if len(parts) >= 3:
                    name = parts[2]
        out += it
        if page * 100 >= total:
            break
        page += 1
    return name, out

def analyze(items):
    n = old = 0
    ages = []
    purpose = {}
    for it in items:
        d = (it.get("useAprDay") or "").strip()
        if len(d) < 4 or not d[:4].isdigit():
            continue
        yr = int(d[:4])
        if yr < 1900 or yr > YEAR:
            continue
        struct = it.get("strctCdNm") or ""
        purp = it.get("mainPurpsCdNm") or "기타"
        age = YEAR - yr
        thr = 30 if ("철근" in struct or "철골" in struct or "라멘" in struct) else 20
        n += 1
        ages.append(age)
        if age >= thr:
            old += 1
        # 용도 묶기
        if "단독" in purp: k = "단독주택"
        elif "공동" in purp or "아파트" in purp or "다세대" in purp or "연립" in purp: k = "공동주택"
        elif "근린" in purp: k = "근린생활"
        elif "공장" in purp: k = "공장"
        elif "업무" in purp: k = "업무"
        else: k = "기타"
        purpose[k] = purpose.get(k, 0) + 1
    ratio = round(old / n * 100, 1) if n else 0
    avg = round(sum(ages) / len(ages), 1) if ages else 0
    return n, old, ratio, avg, purpose

def geocode(name, sgg_name="영등포구"):
    try:
        r = httpx.get("https://dapi.kakao.com/v2/local/search/keyword.json",
            headers={"Authorization": f"KakaoAK {KAKAO}"},
            params={"query": f"서울 {sgg_name} {name}", "size": 1}, timeout=10)
        d = r.json().get("documents", [])
        if d:
            return float(d[0]["y"]), float(d[0]["x"])
    except Exception:
        pass
    return None, None

def main():
    # 이미 지정된 정비구역 동 (교차용)
    try:
        zones = json.loads((ROOT / "data" / "redev_points.json").read_text(encoding="utf-8"))
        zone_dongs = set(z.get("dong", "") for z in zones)
    except Exception:
        zone_dongs = set()

    results = []
    # 영등포 법정동코드 후보: 10100~14000 step 100 (신길·대림·양화 포함)
    for code in range(10100, 14100, 100):
        bjd = f"{code:05d}"
        name, items = fetch_dong(SGG, bjd)
        if not name:
            continue
        n, old, ratio, avg, purpose = analyze(items)
        if n < 10:
            continue
        lat, lng = geocode(name)
        # 재개발 vs 재건축 힌트
        kind = "재건축" if purpose.get("공동주택", 0) > n * 0.5 else "재개발"
        already = any(name in zd or zd in name for zd in zone_dongs if zd)
        verdict = "후보" if (ratio >= 60 and not already) else ("진행중" if already else ("경계" if ratio >= 45 else "신축위주"))
        row = {"dong": name, "bjdongCd": bjd, "buildings": n, "old": old,
               "nohu": ratio, "avg_age": avg, "kind": kind,
               "already_zone": already, "verdict": verdict,
               "purpose": purpose, "lat": lat, "lng": lng}
        results.append(row)
        print(f"  {name:<10} 건물{n:>5} 노후도{ratio:>5}% 평균{avg:>5}년 {kind} {verdict}")

    out = {"sigunguCd": SGG, "year": YEAR, "count": len(results), "dongs": results}
    fp = ROOT / "data" / "building_age.json"
    fp.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    print(f"\n저장: {fp} ({len(results)}개 동)")

if __name__ == "__main__":
    main()
