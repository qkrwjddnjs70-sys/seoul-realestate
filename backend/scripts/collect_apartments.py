"""
서울 아파트 실데이터 수집 스크립트
---------------------------------
사용법:
  cd backend
  python scripts/collect_apartments.py

필요한 환경변수 (.env):
  MOLIT_API_KEY  - 국토교통부 실거래가 API 키
  KAKAO_REST_KEY - 카카오 REST API 키 (지오코딩용)

수행 작업:
  1. 국토교통부 실거래가 API로 서울 25개 구 최근 3개월 거래 데이터 수집
  2. 고유 아파트 목록 추출 (단지명 + 법정동 기준 중복 제거)
  3. 카카오 주소 검색 API로 좌표 변환
  4. 인근 지하철역 및 도보 시간 자동 계산
  5. SQLite DB에 저장
"""

import os
import sys
import json
import time
import math
import asyncio
import sqlite3
import xml.etree.ElementTree as ET
from datetime import date, timedelta
from pathlib import Path

# .env 로드
sys.path.insert(0, str(Path(__file__).parent.parent))
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

import httpx

MOLIT_API_KEY  = os.getenv("MOLIT_API_KEY", "")
KAKAO_REST_KEY = os.getenv("KAKAO_REST_KEY", "")
MOLIT_URL      = "https://apis.data.go.kr/1613000/RTMSDataSvcAptTradeDev/getRTMSDataSvcAptTradeDev"
KAKAO_GEO_URL  = "https://dapi.kakao.com/v2/local/search/address.json"

DB_PATH = Path(__file__).parent.parent / "data" / "apartments.db"

# 서울 25개 구 법정동코드
SEOUL_DISTRICTS = {
    "11110": "종로구", "11140": "중구",    "11170": "용산구",
    "11200": "성동구", "11215": "광진구",  "11230": "동대문구",
    "11260": "중랑구", "11290": "성북구",  "11305": "강북구",
    "11320": "도봉구", "11350": "노원구",  "11380": "은평구",
    "11410": "서대문구","11440": "마포구", "11470": "양천구",
    "11500": "강서구", "11530": "구로구",  "11545": "금천구",
    "11560": "영등포구","11590": "동작구", "11620": "관악구",
    "11650": "서초구", "11680": "강남구",  "11710": "송파구",
    "11740": "강동구",
}

# ───────────────────────────── 지하철역 데이터 ─────────────────────────────
from data.subway_stations import SUBWAY_STATIONS


def _haversine_m(lat1, lng1, lat2, lng2) -> float:
    """두 좌표 사이 거리(미터)"""
    R = 6371000
    φ1, φ2 = math.radians(lat1), math.radians(lat2)
    dφ = math.radians(lat2 - lat1)
    dλ = math.radians(lng2 - lng1)
    a = math.sin(dφ/2)**2 + math.cos(φ1)*math.cos(φ2)*math.sin(dλ/2)**2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))


def nearest_subway(lat: float, lng: float):
    """인근 지하철역 이름, 호선, 도보 시간(분) 반환"""
    best_dist = float("inf")
    best_station = None
    for s in SUBWAY_STATIONS:
        d = _haversine_m(lat, lng, s["lat"], s["lng"])
        if d < best_dist:
            best_dist = d
            best_station = s
    walk_minutes = max(1, round(best_dist / 67))  # 도보 약 67m/분 기준
    return best_station["name"], best_station["line"], walk_minutes


# ───────────────────────────── MOLIT API ──────────────────────────────────

def _parse_molit_xml(xml_text: str) -> list[dict]:
    try:
        root = ET.fromstring(xml_text)
        result = []
        for item in root.findall(".//item"):
            name     = (item.findtext("aptNm") or "").strip()
            dong     = (item.findtext("umdNm") or "").strip()
            jibun    = (item.findtext("jibun") or "").strip()
            gu       = (item.findtext("estateAgentSggNm") or "").strip()
            price_s  = (item.findtext("dealAmount") or "").replace(",", "").strip()
            area_s   = (item.findtext("excluUseAr") or "0")
            year_s   = (item.findtext("buildYear") or "0")
            deal_y   = item.findtext("dealYear") or "0"
            deal_m   = item.findtext("dealMonth") or "0"
            deal_d   = item.findtext("dealDay") or "0"

            if not name or not price_s:
                continue
            result.append({
                "name":      name,
                "dong":      dong,
                "jibun":     jibun,
                "gu":        gu,
                "price":     int(price_s),
                "area_m2":   float(area_s),
                "built_year":int(year_s),
                "deal_date": f"{deal_y}-{int(deal_m):02d}-{int(deal_d):02d}",
            })
        return result
    except Exception as e:
        print(f"  XML parsing error: {e}")
        return []


async def fetch_district_months(client: httpx.AsyncClient, lawd_cd: str, months: int = 3) -> list[dict]:
    today = date.today()
    all_items = []
    for i in range(months):
        d = (today.replace(day=1) - timedelta(days=i * 30))
        ym = f"{d.year}{d.month:02d}"
        try:
            resp = await client.get(MOLIT_URL, params={
                "serviceKey": MOLIT_API_KEY,
                "LAWD_CD":    lawd_cd,
                "DEAL_YMD":   ym,
                "numOfRows":  1000,
                "pageNo":     1,
            })
            items = _parse_molit_xml(resp.text)
            all_items.extend(items)
            await asyncio.sleep(0.05)
        except Exception as e:
            print(f"  [{lawd_cd}] {ym} 오류: {e}")
    return all_items


# ───────────────────────────── Kakao 지오코딩 ─────────────────────────────

async def geocode(client: httpx.AsyncClient, address: str):
    """주소 → (lat, lng) | None"""
    if not KAKAO_REST_KEY:
        return None
    try:
        resp = await client.get(
            KAKAO_GEO_URL,
            headers={"Authorization": f"KakaoAK {KAKAO_REST_KEY}"},
            params={"query": address, "analyze_type": "exact"},
        )
        docs = resp.json().get("documents", [])
        if not docs:
            # 두 번째 시도: 덜 엄격한 검색
            resp = await client.get(
                KAKAO_GEO_URL,
                headers={"Authorization": f"KakaoAK {KAKAO_REST_KEY}"},
                params={"query": address},
            )
            docs = resp.json().get("documents", [])
        if docs:
            d = docs[0]
            return float(d["y"]), float(d["x"])
    except Exception as e:
        print(f"  지오코딩 오류 ({address}): {e}")
    return None


# ───────────────────────────── DB 초기화 ──────────────────────────────────

def init_db(conn: sqlite3.Connection):
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS apartments (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            name         TEXT NOT NULL,
            address      TEXT NOT NULL,
            lat          REAL DEFAULT 0,
            lng          REAL DEFAULT 0,
            lawd_cd      TEXT,
            dong         TEXT,
            built_year   INTEGER DEFAULT 0,
            last_price   INTEGER DEFAULT 0,
            last_deal_date TEXT DEFAULT '',
            area_m2      REAL DEFAULT 0,
            nearest_subway TEXT DEFAULT '',
            subway_line  TEXT DEFAULT '',
            walk_minutes INTEGER DEFAULT 0,
            bus_routes   TEXT DEFAULT '[]',
            hojaes       TEXT DEFAULT '[]',
            units        INTEGER DEFAULT 0,
            floor        INTEGER DEFAULT 0,
            total_floors INTEGER DEFAULT 0,
            geocoded     INTEGER DEFAULT 0
        );
        CREATE UNIQUE INDEX IF NOT EXISTS idx_apt_key
            ON apartments(name, dong, lawd_cd);
    """)
    conn.commit()


# ───────────────────────────── 메인 ───────────────────────────────────────

async def main():
    if not MOLIT_API_KEY:
        print("[오류] MOLIT_API_KEY 가 .env에 없습니다.")
        return
    if not KAKAO_REST_KEY:
        print("[경고] KAKAO_REST_KEY 없음 -> 좌표 변환 불가 (geocoded=0 으로 저장)")

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    init_db(conn)

    print("─" * 60)
    print("1단계: 국토부 실거래가 API 수집 (서울 25개 구, 최근 3개월)")
    print("─" * 60)

    all_transactions: list[dict] = []
    async with httpx.AsyncClient(timeout=30) as client:
        for lawd_cd, gu_name in SEOUL_DISTRICTS.items():
            print(f"  {gu_name} ({lawd_cd}) 수집 중...", end=" ")
            items = await fetch_district_months(client, lawd_cd, months=3)
            # lawd_cd 붙여서 저장
            for it in items:
                it["lawd_cd"] = lawd_cd
            all_transactions.extend(items)
            print(f"{len(items)}건")
            await asyncio.sleep(0.2)

    print(f"\n총 거래 건수: {len(all_transactions):,}건")

    # ── 고유 아파트 추출 (name + dong + lawd_cd 기준, 최신 거래가 우선) ──
    apt_map: dict[tuple, dict] = {}
    for t in sorted(all_transactions, key=lambda x: x["deal_date"]):
        key = (t["name"], t["dong"], t["lawd_cd"])
        existing = apt_map.get(key)
        if existing is None or t["deal_date"] >= existing["last_deal_date"]:
            apt_map[key] = {
                "name":       t["name"],
                "dong":       t["dong"],
                "jibun":      t["jibun"],
                "gu":         t["gu"],
                "lawd_cd":    t["lawd_cd"],
                "last_price": t["price"],
                "last_deal_date": t["deal_date"],
                "built_year": t["built_year"],
                "area_m2":    t["area_m2"],
                "address":    f"{t['gu']} {t['dong']} {t['jibun']}".replace("서울 ", "서울시 ").strip(),
            }

    apartments = list(apt_map.values())
    print(f"고유 아파트 단지: {len(apartments):,}개")

    # ── 기존 DB에서 이미 geocode된 항목 스킵 ──
    already_done = set()
    for row in conn.execute("SELECT name, dong, lawd_cd FROM apartments WHERE geocoded=1"):
        already_done.add((row[0], row[1], row[2]))

    to_geocode = [a for a in apartments if (a["name"], a["dong"], a["lawd_cd"]) not in already_done]
    print(f"지오코딩 필요: {len(to_geocode):,}개 (기존 완료: {len(already_done):,}개)")

    print("\n─" * 60)
    print("2단계: 카카오 지오코딩 + 인근역 계산")
    print("─" * 60)

    geocoded_count = 0
    skipped_count  = 0

    async with httpx.AsyncClient(timeout=10) as client:
        for i, apt in enumerate(to_geocode, 1):
            coords = await geocode(client, apt["address"])

            if coords:
                lat, lng = coords
                stn_name, stn_line, walk_min = nearest_subway(lat, lng)
                geocoded_flag = 1
                geocoded_count += 1
            else:
                lat = lng = 0.0
                stn_name = stn_line = ""
                walk_min = 0
                geocoded_flag = 0
                skipped_count += 1

            try:
                conn.execute("""
                    INSERT INTO apartments
                        (name, address, lat, lng, lawd_cd, dong, built_year,
                         last_price, last_deal_date, area_m2,
                         nearest_subway, subway_line, walk_minutes, geocoded)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    ON CONFLICT(name, dong, lawd_cd) DO UPDATE SET
                        lat=excluded.lat, lng=excluded.lng,
                        last_price=excluded.last_price,
                        last_deal_date=excluded.last_deal_date,
                        area_m2=excluded.area_m2,
                        built_year=excluded.built_year,
                        nearest_subway=excluded.nearest_subway,
                        subway_line=excluded.subway_line,
                        walk_minutes=excluded.walk_minutes,
                        geocoded=excluded.geocoded
                """, (
                    apt["name"], apt["address"], lat, lng,
                    apt["lawd_cd"], apt["dong"], apt["built_year"],
                    apt["last_price"], apt["last_deal_date"], apt["area_m2"],
                    stn_name, stn_line, walk_min, geocoded_flag,
                ))
            except Exception as e:
                print(f"  DB 저장 오류: {e}")

            if i % 50 == 0:
                conn.commit()
                print(f"  {i:4d}/{len(to_geocode)} 처리 완료 (성공 {geocoded_count}, 실패 {skipped_count})")

            await asyncio.sleep(0.05)  # Kakao API rate limit 여유

    conn.commit()
    conn.close()

    total = conn.execute("SELECT COUNT(*) FROM apartments WHERE geocoded=1") if False else None
    print(f"\n[완료] 지오코딩 성공: {geocoded_count}개, 실패: {skipped_count}개")

    # 최종 카운트
    conn2 = sqlite3.connect(DB_PATH)
    cnt = conn2.execute("SELECT COUNT(*) FROM apartments WHERE geocoded=1").fetchone()[0]
    conn2.close()
    print(f"[DB] 저장된 유효 아파트: {cnt:,}개")


if __name__ == "__main__":
    asyncio.run(main())
