"""핀셋(블록 정밀) — 한 법정동의 100m 격자 노후도. 캐시된 것만 서빙(PoC)."""
import json
from fastapi import APIRouter, Query
from pathlib import Path

router = APIRouter()
_DIR = Path(__file__).parent.parent / "data" / "pinset_cache"


@router.get("")
def pinset(sgg: str = Query(...), bjd: str = Query(...)):
    fp = _DIR / f"{sgg}_{bjd}.json"
    if not fp.exists():
        return {"ready": False, "cells": []}
    data = json.loads(fp.read_text(encoding="utf-8"))
    data["ready"] = True
    return data
