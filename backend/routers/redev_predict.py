"""동별 노후도 기반 재개발 후보 예측."""
import json
from fastapi import APIRouter, Query
from pathlib import Path

router = APIRouter()

_DATA = Path(__file__).parent.parent / "data" / "building_age.json"
try:
    _CACHE = json.loads(_DATA.read_text(encoding="utf-8"))
except Exception:
    _CACHE = {"dongs": []}


@router.get("")
def predict(min_nohu: float = Query(0), only_candidates: bool = Query(False)):
    """동별 노후도 + 재개발 후보 판정.
    min_nohu: 최소 노후도(%) 필터
    only_candidates: True면 '후보'(노후도 60%+ & 미지정)만
    """
    dongs = [d for d in _CACHE.get("dongs", [])
             if d.get("lat") and d.get("nohu", 0) >= min_nohu
             and (not only_candidates or d.get("verdict") == "후보")]
    return {"count": len(dongs), "year": _CACHE.get("year"), "dongs": dongs}
