import os
from fastapi import APIRouter, HTTPException
import database as db_module
from data.mock_properties import PROPERTIES
from services.molit_api import fetch_transactions, fetch_trend

router = APIRouter()


def _find_property(property_id: int):
    # 실 DB 우선 조회
    try:
        if db_module.db_exists():
            row = db_module.get_apartment_by_id(property_id)
            if row:
                return {
                    "id":      row["id"],
                    "name":    row["name"],
                    "lawd_cd": row["lawd_cd"],
                    "price":   row["last_price"],
                }
    except Exception:
        pass
    # mock 폴백
    for p in PROPERTIES:
        if p["id"] == property_id:
            return p
    return None


@router.get("/{property_id}/transactions")
async def get_transactions(property_id: int):
    p = _find_property(property_id)
    if not p:
        raise HTTPException(status_code=404, detail="매물을 찾을 수 없습니다")
    items = await fetch_transactions(p["lawd_cd"], p["name"], p["price"])
    return {"property_id": property_id, "name": p["name"], "items": items, "is_mock": not bool(os.getenv("MOLIT_API_KEY"))}


@router.get("/{property_id}/trend")
async def get_trend(property_id: int):
    p = _find_property(property_id)
    if not p:
        raise HTTPException(status_code=404, detail="매물을 찾을 수 없습니다")
    trend = await fetch_trend(p["lawd_cd"], p["name"], p["price"])
    return {"property_id": property_id, "name": p["name"], "trend": trend, "is_mock": not bool(os.getenv("MOLIT_API_KEY"))}
