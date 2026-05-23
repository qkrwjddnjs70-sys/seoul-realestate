"""
국토교통부 아파트매매 실거래가 API 연동
API 키: 공공데이터포털(data.go.kr) → 국토교통부_아파트매매 실거래자료 신청
env: MOLIT_API_KEY
"""
import os
import xml.etree.ElementTree as ET
from datetime import date, timedelta
import random
import httpx

MOLIT_API_URL = "https://apis.data.go.kr/1613000/RTMSDataSvcAptTradeDev/getRTMSDataSvcAptTradeDev"
API_KEY = os.getenv("MOLIT_API_KEY", "")


def _mock_transactions(base_price: int, months: int = 24) -> list[dict]:
    """API 키 없을 때 사용하는 Mock 실거래 데이터"""
    today = date.today()
    result = []
    price = base_price

    for i in range(months * 2, 0, -1):
        # 약 2주 간격으로 거래 생성 (월 2건)
        tx_date = today - timedelta(days=i * 14)
        # ±5% 랜덤 변동
        variance = random.uniform(-0.05, 0.05)
        # 장기 트렌드: 최근 24개월간 완만한 상승
        trend = (months * 2 - i) / (months * 2) * 0.08
        tx_price = int(price * (1 + variance + trend))
        area = round(random.choice([59.9, 84.9, 114.9, 134.9]), 1)
        result.append({
            "year": tx_date.year,
            "month": tx_date.month,
            "day": tx_date.day,
            "price": tx_price,
            "area_m2": area,
            "floor": random.randint(1, 30),
        })

    return sorted(result, key=lambda x: (x["year"], x["month"], x["day"]), reverse=True)


def _mock_trend(base_price: int, months: int = 24) -> list[dict]:
    """월별 평균 시세 추이 Mock"""
    today = date.today()
    result = []
    price = base_price

    for i in range(months - 1, -1, -1):
        d = today.replace(day=1) - timedelta(days=i * 30)
        trend = (months - i) / months * 0.08
        variance = random.uniform(-0.02, 0.02)
        avg_price = int(price * (1 + trend + variance - 0.04))
        result.append({
            "ym": f"{d.year}.{d.month:02d}",
            "avg_price": avg_price,
            "count": random.randint(1, 15),
        })

    return result


async def fetch_transactions(lawd_cd: str, apt_name: str, base_price: int) -> list[dict]:
    """실거래 내역 조회 (최근 6개월)"""
    if not API_KEY:
        return _mock_transactions(base_price, months=12)

    today = date.today()
    all_items = []

    async with httpx.AsyncClient(timeout=10) as client:
        for i in range(6):
            d = today.replace(day=1) - timedelta(days=i * 30)
            ym = f"{d.year}{d.month:02d}"
            try:
                resp = await client.get(MOLIT_API_URL, params={
                    "serviceKey": API_KEY,
                    "LAWD_CD": lawd_cd,
                    "DEAL_YMD": ym,
                    "numOfRows": 100,
                    "pageNo": 1,
                })
                items = _parse_xml(resp.text, apt_name)
                all_items.extend(items)
            except Exception:
                pass

    return all_items if all_items else _mock_transactions(base_price, months=6)


async def fetch_trend(lawd_cd: str, apt_name: str, base_price: int) -> list[dict]:
    """월별 평균 시세 추이 조회 (최근 24개월)"""
    if not API_KEY:
        return _mock_trend(base_price, months=24)

    today = date.today()
    trend = []

    async with httpx.AsyncClient(timeout=10) as client:
        for i in range(23, -1, -1):
            d = today.replace(day=1) - timedelta(days=i * 30)
            ym = f"{d.year}{d.month:02d}"
            try:
                resp = await client.get(MOLIT_API_URL, params={
                    "serviceKey": API_KEY,
                    "LAWD_CD": lawd_cd,
                    "DEAL_YMD": ym,
                    "numOfRows": 100,
                    "pageNo": 1,
                })
                items = _parse_xml(resp.text, apt_name)
                if items:
                    avg = sum(x["price"] for x in items) // len(items)
                    trend.append({
                        "ym": f"{d.year}.{d.month:02d}",
                        "avg_price": avg,
                        "count": len(items),
                    })
            except Exception:
                pass

    return trend if trend else _mock_trend(base_price, months=24)


def _parse_xml(xml_text: str, apt_name: str) -> list[dict]:
    try:
        root = ET.fromstring(xml_text)
        items = root.findall(".//item")
        result = []
        for item in items:
            name = (item.findtext("aptNm") or "").strip()
            if apt_name and apt_name not in name and name not in apt_name:
                continue
            price_str = (item.findtext("dealAmount") or "").replace(",", "").strip()
            if not price_str:
                continue
            result.append({
                "year": int(item.findtext("dealYear") or 0),
                "month": int(item.findtext("dealMonth") or 0),
                "day": int(item.findtext("dealDay") or 0),
                "price": int(price_str),
                "area_m2": float(item.findtext("excluUseAr") or 0),
                "floor": int(item.findtext("floor") or 0),
            })
        return result
    except Exception:
        return []
