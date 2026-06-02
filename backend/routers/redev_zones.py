"""정비사업 구역 검색 — 대표지점 좌표 (정보몽땅 기반)"""
import os, json
from fastapi import APIRouter, Query
from pathlib import Path

router = APIRouter()

_DATA = Path(__file__).parent.parent / "data" / "redev_points.json"
_ZONES = []
try:
    _ZONES = json.loads(_DATA.read_text(encoding="utf-8"))
except Exception:
    _ZONES = []


@router.get("/search")
def search_zones(q: str = Query("", description="검색어 (동·구역명·사업유형)")):
    """검색어로 정비사업 구역 필터 → 지도 마커용 좌표 리스트"""
    qn = (q or "").replace(" ", "").strip()
    if not qn:
        return {"count": 0, "zones": []}
    out = []
    for z in _ZONES:
        hay = (z.get("name", "") + z.get("gu", "") + z.get("dong", "") +
               z.get("jibun", "") + z.get("type", "")).replace(" ", "")
        if qn in hay:
            out.append(z)
    return {"count": len(out), "zones": out[:200]}


@router.get("/all")
def all_zones(gu: str = Query(""), type: str = Query("")):
    """구/유형 필터 (전체 마커 표시용)"""
    out = _ZONES
    if gu:
        out = [z for z in out if gu in z.get("gu", "")]
    if type:
        out = [z for z in out if type in z.get("type", "")]
    return {"count": len(out), "zones": out[:1000]}
