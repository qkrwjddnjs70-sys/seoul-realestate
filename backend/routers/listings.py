"""
네이버 부동산 현재 매물 요약 (단지별 매매·전세·월세 매물 수 + 가격 범위)
- m.land.naver.com cluster API 사용 (인증 불필요)
- 좌표 주변 fetch → naver_id 일치 항목 골라 반환
"""
import os, re
from difflib import SequenceMatcher
from fastapi import APIRouter, HTTPException
import httpx

import database as db_module

router = APIRouter()

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; SeoulRE/1.0)"}
URL = "https://m.land.naver.com/cluster/ajax/complexList"


def _strip_html(s: str | None) -> str:
    if not s:
        return ""
    return re.sub(r"<[^>]+>", "", s).replace(" ", "").strip()


@router.get("/{property_id}")
async def get_listings(property_id: int):
    conn = db_module.get_db()
    row = conn.execute(
        "SELECT id, name, display_name, lat, lng, naver_id "
        "FROM apartments WHERE id=?", (property_id,)
    ).fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="아파트 없음")
    lat, lng = row["lat"], row["lng"]
    naver_id = row["naver_id"] or ""
    if not lat or not lng:
        return {"available": False, "reason": "좌표 없음"}

    delta = 0.004
    params = {
        "itemId": "", "mapKey": "", "lgeo": "", "showR0": "",
        "rletTpCd": "APT", "tradTpCd": "",
        "z": 17, "lat": lat, "lon": lng,
        "btm": lat - delta, "lft": lng - delta,
        "top": lat + delta, "rgt": lng + delta,
    }

    async with httpx.AsyncClient(timeout=10) as c:
        try:
            r = await c.get(URL, params=params, headers=HEADERS)
            if r.status_code != 200:
                return {"available": False, "reason": f"네이버 API {r.status_code}"}
            results = r.json().get("result") or []
        except Exception as e:
            return {"available": False, "reason": str(e)}

    target = None
    if naver_id:
        target = next((x for x in results if str(x.get("hscpNo")) == str(naver_id)), None)
    if not target and results:
        # 유사도 기반 fallback (이름 + 세대수 + 준공연도)
        conn2 = db_module.get_db()
        full = conn2.execute(
            "SELECT name, display_name, units, built_year FROM apartments WHERE id=?",
            (property_id,)
        ).fetchone()
        conn2.close()
        norm = ((full["display_name"] or full["name"] or "")).replace(" ", "")
        u, y = full["units"] or 0, full["built_year"] or 0
        best, best_score = None, 0.0
        for x in results:
            cand = (x.get("hscpNm") or "").replace(" ", "")
            sim = SequenceMatcher(None, cand, norm).ratio() * 100
            if cand in norm or norm in cand:
                sim = max(sim, 85)
            cu = x.get("totHsehCnt") or 0
            if u and cu:
                sim -= abs(cu - u) / max(u, cu) * 20
            cy = (x.get("useAprvYmd") or "")[:4]
            if cy.isdigit() and y:
                sim -= abs(int(cy) - y) * 0.5
            if sim > best_score:
                best_score = sim
                best = x
        if best_score >= 45:
            target = best

    if not target:
        return {"available": False, "reason": "네이버 단지 매칭 실패"}

    out = {
        "available":    True,
        "hscpNo":       target.get("hscpNo"),
        "hscpNm":       target.get("hscpNm"),
        "useAprvYmd":   target.get("useAprvYmd"),
        "totHsehCnt":   target.get("totHsehCnt"),
        "minSpc":       target.get("minSpc"),
        "maxSpc":       target.get("maxSpc"),
        "totalAtclCnt": target.get("totalAtclCnt"),
        "deal": {
            "count":   target.get("dealCnt") or 0,
            "minPrc":  _strip_html(target.get("dealPrcMin")),
            "maxPrc":  _strip_html(target.get("dealPrcMax")),
        },
        "lease": {
            "count":   target.get("leaseCnt") or 0,
            "minPrc":  _strip_html(target.get("leasePrcMin")),
            "maxPrc":  _strip_html(target.get("leasePrcMax")),
        },
        "rent": {
            "count":   target.get("rentCnt") or 0,
            "minPrc":  _strip_html(target.get("rentPrcMin")),
            "maxPrc":  _strip_html(target.get("rentPrcMax")),
        },
        "link": f"https://new.land.naver.com/complexes/{target.get('hscpNo')}?ms={lat},{lng},17&a=APT&e=RETAIL",
    }
    return out
