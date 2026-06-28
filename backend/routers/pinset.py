"""핀셋(블록 정밀) — 한 법정동의 100m 격자 노후도.
캐시 있으면 즉시, 없으면 온디맨드 계산(지번 지오코딩, 시간 제한 위해 고유지번 캡).
"""
import os, json, time, math
from fastapi import APIRouter, Query
from pathlib import Path
import httpx

router = APIRouter()
_DIR = Path(__file__).parent.parent / "data" / "pinset_cache"
KEY = os.getenv("PUBLIC_DATA_KEY_DECODED") or os.getenv("PUBLIC_DATA_KEY_ENCODED")
KAKAO = os.getenv("KAKAO_REST_KEY")
BLD = "https://apis.data.go.kr/1613000/BldRgstHubService/getBrTitleInfo"
YEAR = 2026
LATG, LNGG = 0.0009, 0.00114       # ~100m @37.5N
MAX_GEOCODE = 280                  # 고유지번 지오코딩 상한(응답시간 보호)


def _compute(sgg, bjd):
    cli = httpx.Client(timeout=25)
    items, page = [], 1
    while True:
        try:
            r = cli.get(BLD, params={"serviceKey": KEY, "sigunguCd": sgg, "bjdongCd": bjd,
                "numOfRows": "100", "pageNo": str(page), "_type": "json"})
            body = r.json()["response"]["body"]
        except Exception:
            break
        total = int(body.get("totalCount", 0) or 0)
        it = body.get("items", {}).get("item", []) if body.get("items") else []
        it = [it] if isinstance(it, dict) else it
        items += it
        if page * 100 >= total or not it:
            break
        page += 1
    if not items:
        return {"ready": False, "cells": []}

    def isold(x):
        d = (x.get("useAprDay") or "").strip()
        if len(d) < 4 or not d[:4].isdigit(): return None
        yr = int(d[:4])
        if yr < 1900 or yr > YEAR: return None
        st = x.get("strctCdNm") or ""
        thr = 30 if ("철근" in st or "철골" in st or "라멘" in st) else 20
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

    # 고유 지번 모으기 (캡 적용 — 너무 큰 동은 샘플)
    valid = [(x, isold(x)) for x in items if isold(x) is not None and (x.get("platPlc") or "").strip()]
    uniq = {}
    for x, o in valid:
        uniq.setdefault(x.get("platPlc").strip(), [])
    plcs = list(uniq.keys())
    capped = plcs[:: max(1, math.ceil(len(plcs) / MAX_GEOCODE))]  # 균등 샘플
    coords = {}
    for plc in capped:
        coords[plc] = kgeo(plc); time.sleep(0.01)

    grid = {}
    n = 0
    for x, o in valid:
        c = coords.get(x.get("platPlc").strip())
        if not c: continue
        k = (round(c[0] / LATG), round(c[1] / LNGG))
        g = grid.setdefault(k, [0, 0]); g[0] += 1; g[1] += 1 if o else 0; n += 1
    cells = [{"lat": round(gy * LATG, 6), "lng": round(gx * LNGG, 6),
              "total": t, "old": old, "ratio": round(old / t * 100)}
             for (gy, gx), (t, old) in grid.items() if t >= 3]
    cells.sort(key=lambda c: -c["ratio"])
    out = {"sgg": sgg, "bjd": bjd, "buildings": len(items), "geocoded": n,
           "sampled_addr": len(capped), "cells": cells, "ready": True}
    _DIR.mkdir(exist_ok=True)
    (_DIR / f"{sgg}_{bjd}.json").write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    return out


@router.get("")
def pinset(sgg: str = Query(...), bjd: str = Query(...)):
    fp = _DIR / f"{sgg}_{bjd}.json"
    if fp.exists():
        data = json.loads(fp.read_text(encoding="utf-8"))
        data["ready"] = True
        return data
    # 온디맨드 계산 (10~30초 소요 가능)
    return _compute(sgg, bjd)
