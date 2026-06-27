# -*- coding: utf-8 -*-
"""동별 노후도 계산 → 재개발 후보 예측 데이터 (서울 25개 구).
건축물대장(국토부) API로 법정동별 건물의 사용승인일·구조·용도를 받아
노후도(노후·불량 건축물 비율)를 계산. 서울 조례:
  - 노후: 철근콘크리트/철골 30년+, 그 외(벽돌/조적) 20년+
  - 재개발 요건: 노후도 60%+
대형 동은 분산 샘플링(최대 6페이지=600채, 전체에 고르게)으로 추정 → 호출 절감·편향 최소.
사용: python enrich_building_age.py            # 서울 전체
      python enrich_building_age.py 11560      # 특정 구만
"""
import sys, json, math
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
MAX_PAGES = 6   # 동당 최대 샘플 페이지(=600채)

SEOUL_GU = {
    "11110": "종로구", "11140": "중구", "11170": "용산구", "11200": "성동구",
    "11215": "광진구", "11230": "동대문구", "11260": "중랑구", "11290": "성북구",
    "11305": "강북구", "11320": "도봉구", "11350": "노원구", "11380": "은평구",
    "11410": "서대문구", "11440": "마포구", "11470": "양천구", "11500": "강서구",
    "11530": "구로구", "11545": "금천구", "11560": "영등포구", "11590": "동작구",
    "11620": "관악구", "11650": "서초구", "11680": "강남구", "11710": "송파구",
    "11740": "강동구",
}

cli = httpx.Client(timeout=40)

def _page(sgg, bjd, page):
    try:
        r = cli.get(URL, params={"serviceKey": KEY, "sigunguCd": sgg, "bjdongCd": bjd,
            "numOfRows": "100", "pageNo": str(page), "_type": "json"})
        body = r.json()["response"]["body"]
        items = body.get("items")
        it = items.get("item", []) if items else []
        if isinstance(it, dict): it = [it]
        return int(body.get("totalCount", 0) or 0), it
    except Exception:
        return 0, []

def fetch_dong(sgg, bjd):
    total, first = _page(sgg, bjd, 1)
    if total == 0:
        return None, []
    name = ""
    for x in first:
        plc = x.get("platPlc", "")
        parts = plc.split()
        if len(parts) >= 3:
            name = parts[2]; break
    items = list(first)
    total_pages = math.ceil(total / 100)
    if total_pages > 1:
        if total_pages <= MAX_PAGES:
            pages = range(2, total_pages + 1)
        else:
            # 2~끝페이지를 고르게 분산 샘플 (MAX_PAGES-1개)
            step = total_pages / MAX_PAGES
            pages = sorted(set(int(round(step * k)) for k in range(1, MAX_PAGES)))
            pages = [p for p in pages if 2 <= p <= total_pages]
        for p in pages:
            _, it = _page(sgg, bjd, p)
            items += it
    return name, (items, total)

def _f(v):
    try: return float(v)
    except (TypeError, ValueError): return 0.0

def analyze(items):
    n = old = 0; ages = []; purpose = {}
    floors = []; low = 0           # 지상층수 / 저층(≤4층) 수
    sum_tot = sum_plat = 0.0       # 연면적·대지면적 합(추정 용적률용)
    for it in items:
        d = (it.get("useAprDay") or "").strip()
        if len(d) < 4 or not d[:4].isdigit(): continue
        yr = int(d[:4])
        if yr < 1900 or yr > YEAR: continue
        struct = it.get("strctCdNm") or ""
        purp = it.get("mainPurpsCdNm") or "기타"
        age = YEAR - yr
        thr = 30 if ("철근" in struct or "철골" in struct or "라멘" in struct) else 20
        n += 1; ages.append(age)
        if age >= thr: old += 1
        fl = _f(it.get("grndFlrCnt"))
        if fl > 0:
            floors.append(fl)
            if fl <= 4: low += 1
        tot = _f(it.get("totArea")); plat = _f(it.get("platArea"))
        if tot > 0 and plat > 0:
            sum_tot += tot; sum_plat += plat
        if "단독" in purp: k = "단독주택"
        elif "공동" in purp or "아파트" in purp or "다세대" in purp or "연립" in purp: k = "공동주택"
        elif "근린" in purp: k = "근린생활"
        elif "공장" in purp: k = "공장"
        elif "업무" in purp: k = "업무"
        else: k = "기타"
        purpose[k] = purpose.get(k, 0) + 1
    ratio = round(old / n * 100, 1) if n else 0
    avg = round(sum(ages) / len(ages), 1) if ages else 0
    avg_floor = round(sum(floors) / len(floors), 1) if floors else 0
    lowrise = round(low / len(floors) * 100, 1) if floors else 0   # 저층 비율(%)
    est_far = round(sum_tot / sum_plat * 100, 0) if sum_plat > 0 else None  # 추정 현재 용적률
    return n, old, ratio, avg, purpose, avg_floor, lowrise, est_far

def geocode(gu, name):
    try:
        r = cli.get("https://dapi.kakao.com/v2/local/search/keyword.json",
            headers={"Authorization": f"KakaoAK {KAKAO}"},
            params={"query": f"서울 {gu} {name}", "size": 1})
        d = r.json().get("documents", [])
        if d: return float(d[0]["y"]), float(d[0]["x"])
    except Exception:
        pass
    return None, None

def main():
    try:
        zones = json.loads((ROOT / "data" / "redev_points.json").read_text(encoding="utf-8"))
        zone_dongs = set((z.get("gu", ""), z.get("dong", "")) for z in zones)
    except Exception:
        zone_dongs = set()

    targets = {sys.argv[1]: SEOUL_GU.get(sys.argv[1], "")} if len(sys.argv) > 1 else SEOUL_GU
    results = []
    for sgg, guname in targets.items():
        gucount = 0
        for code in range(10100, 14100, 100):
            bjd = f"{code:05d}"
            name, res = fetch_dong(sgg, bjd)
            if not name: continue
            items, total = res
            n, old, ratio, avg, purpose, avg_floor, lowrise, est_far = analyze(items)
            if n < 10: continue
            lat, lng = geocode(guname, name)
            kind = "재건축" if purpose.get("공동주택", 0) > n * 0.5 else "재개발"
            already = (guname, name) in zone_dongs
            verdict = "후보" if (ratio >= 60 and not already) else ("진행중" if already else ("경계" if ratio >= 45 else "신축위주"))
            results.append({"gu": guname, "dong": name, "bjdongCd": bjd,
                "buildings": total, "sampled": n, "old": old, "nohu": ratio, "avg_age": avg,
                "avg_floor": avg_floor, "lowrise": lowrise, "est_far": est_far,
                "kind": kind, "already_zone": already, "verdict": verdict,
                "purpose": purpose, "lat": lat, "lng": lng})
            gucount += 1
        print(f"[{guname}] {gucount}개 동 완료  (누적 {len(results)})", flush=True)

    out = {"year": YEAR, "count": len(results), "dongs": results}
    fp = ROOT / "data" / "building_age.json"
    fp.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    print(f"\n저장: {fp} ({len(results)}개 동, {len(targets)}개 구)")

if __name__ == "__main__":
    main()
