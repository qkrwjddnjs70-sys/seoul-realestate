"""
강서구·영등포구 학교 데이터 제공
"""
import os, json
from fastapi import APIRouter

router = APIRouter()

_DATA_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data", "schools.json"
)
_cache = None


@router.get("")
def get_schools():
    global _cache
    if _cache is None:
        try:
            with open(_DATA_PATH, encoding="utf-8") as f:
                _cache = json.load(f)
        except Exception:
            _cache = []
    return {"total": len(_cache), "schools": _cache}
