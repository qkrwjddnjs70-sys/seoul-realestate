# -*- coding: utf-8 -*-
"""핀셋(블록 정밀) 캐시 생성: 한 법정동 건물 지오코딩 → 100m 격자 노후도.
결과를 backend/data/pinset_cache/{sgg}_{bjd}.json 에 저장 (엔드포인트가 읽음).
사용: python gen_pinset.py 11560 12200 영등포구 문래동4가
"""
import sys, time, json
sys.stdout.reconfigure(encoding="utf-8")
import httpx
from pathlib import Path
from dotenv import dotenv_values

ROOT = Path(__file__).parent.parent
env = dotenv_values(ROOT / ".env")
KEY = env.get("PUBLIC_DATA_KEY_DECODED"); KAKAO = env.get("KAKAO_REST_KEY")
YEAR = 2026
BLD = "https://apis.data.go.kr/1613000/BldRgstHubService/getBrTitleInfo"
LATG, LNGG = 0.0009, 0.00114   # ~100m @37.5N
cli = httpx.Client(timeout=30)

def run(sgg, bjd, gu, dong):
    items, page = [], 1
    while True:
        r = cli.get(BLD, params={"serviceKey": KEY, "sigunguCd": sgg, "bjdongCd": bjd,
            "numOfRows": "100", "pageNo": str(page), "_type": "json"})
        body = r.json()["response"]["body"]; total = int(body.get("totalCount", 0))
        it = body.get("items", {}).get("item", []); it = [it] if isinstance(it, dict) else it
        items += it
        if page * 100 >= total or not it: break
        page += 1

    def isold(it):
        d = (it.get("useAprDay") or "").strip()
        if len(d) < 4 or not d[:4].isdigit(): return None
        yr = int(d[:4])
        if yr < 1900 or yr > YEAR: return None
        st = it.get("strctCdNm") or ""; thr = 30 if ("철근" in st or "철골" in st or "라멘" in st) else 20
        return (YEAR - yr) >= thr

    def kgeo(addr):
        for path in ("address", "keyword"):
            try:
                r = cli.get(f"https://dapi.kakao.com/v2/local/search/{path}.json",
                    headers={"Authorization": f"KakaoAK {KAKAO}"}, params={"query": addr, "size": 1})
                d = r.json().get("documents", [])
                if d: return float(d[0]["y"]), float(d[0]["x"])
            except Exception:
                pass
        return None

    cache, pts, n = {}, [], 0
    for it in items:
        o = isold(it)
        if o is None: continue
        plc = it.get("platPlc", "").strip()
        if not plc: continue
        if plc not in cache:
            cache[plc] = kgeo(plc); time.sleep(0.02)
        c = cache[plc]
        if c: pts.append((c[0], c[1], o)); n += 1

    grid = {}
    for lat, lng, o in pts:
        k = (round(lat / LATG), round(lng / LNGG))
        g = grid.setdefault(k, [0, 0]); g[0] += 1; g[1] += 1 if o else 0
    cells = [{"lat": round(gy * LATG, 6), "lng": round(gx * LNGG, 6),
              "total": t, "old": old, "ratio": round(old / t * 100)}
             for (gy, gx), (t, old) in grid.items() if t >= 3]
    cells.sort(key=lambda c: -c["ratio"])

    out = {"gu": gu, "dong": dong, "sgg": sgg, "bjd": bjd,
           "buildings": len(items), "geocoded": n, "cells": cells}
    cdir = ROOT / "data" / "pinset_cache"; cdir.mkdir(exist_ok=True)
    fp = cdir / f"{sgg}_{bjd}.json"
    fp.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    print(f"저장: {fp} | 건물{len(items)} 지오코딩{n} 격자{len(cells)}")
    for c in cells[:8]:
        print(f"  노후{c['ratio']}% ({c['old']}/{c['total']}) @{c['lat']},{c['lng']}")

if __name__ == "__main__":
    a = sys.argv
    run(a[1], a[2], a[3], a[4])
