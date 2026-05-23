"""
세대수 보강 스크립트
--------------------
한국부동산원 공동주택 단지 식별정보 API (ODCloud AptIdInfoSvc) 활용
  - UNIT_CNT (세대수), COMPLEX_NM1/2/3 (단지명) 제공
  - 기존 MOLIT API 키 그대로 사용 가능

사용법:
  cd backend
  python scripts/enrich_units.py
"""

import os
import sys
import asyncio
import sqlite3
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

import httpx

MOLIT_API_KEY = os.getenv("MOLIT_API_KEY", "")
DB_PATH = Path(__file__).parent.parent / "data" / "apartments.db"

BASE_URL = "https://api.odcloud.kr/api/AptIdInfoSvc/v1/getAptInfo"

SEOUL_GU = {
    "11110": "종로구",  "11140": "중구",     "11170": "용산구",
    "11200": "성동구",  "11215": "광진구",   "11230": "동대문구",
    "11260": "중랑구",  "11290": "성북구",   "11305": "강북구",
    "11320": "도봉구",  "11350": "노원구",   "11380": "은평구",
    "11410": "서대문구","11440": "마포구",   "11470": "양천구",
    "11500": "강서구",  "11530": "구로구",   "11545": "금천구",
    "11560": "영등포구","11590": "동작구",   "11620": "관악구",
    "11650": "서초구",  "11680": "강남구",   "11710": "송파구",
    "11740": "강동구",
}


def _norm(s: str) -> str:
    """이름 정규화: 공백·괄호·특수문자 제거"""
    return s.strip().replace(" ", "").replace("(", "").replace(")", "").replace("-", "")


async def fetch_gu_complexes(client: httpx.AsyncClient, gu_name: str) -> list[dict]:
    """구 이름으로 공동주택 단지 전체 목록 조회"""
    all_items = []
    page = 1
    per_page = 1000

    while True:
        try:
            r = await client.get(BASE_URL, params={
                "serviceKey": MOLIT_API_KEY,
                "page": page,
                "perPage": per_page,
                "cond[ADRES::LIKE]": gu_name,
            }, timeout=30)

            if r.status_code != 200:
                break

            data = r.json()
            items = data.get("data") or []
            all_items.extend(items)

            total = data.get("totalCount", 0)
            if page * per_page >= total:
                break
            page += 1
            await asyncio.sleep(0.1)

        except Exception as e:
            print(f"  오류: {e}")
            break

    return all_items


def build_name_map(items: list[dict]) -> dict[str, int]:
    """name(정규화) -> UNIT_CNT 맵 생성 (NM1, NM2, NM3 모두 등록)"""
    result = {}
    for item in items:
        units = item.get("UNIT_CNT") or 0
        if not units:
            continue
        for field in ("COMPLEX_NM1", "COMPLEX_NM2", "COMPLEX_NM3"):
            nm = item.get(field)
            if nm:
                key = _norm(nm)
                if key and key not in result:
                    result[key] = units
    return result


def match_units(db_name: str, name_map: dict[str, int]) -> int | None:
    """DB 단지명과 API 단지명 매칭 (정규화 + 부분일치)"""
    norm = _norm(db_name)

    # 1. 정확히 일치
    if norm in name_map:
        return name_map[norm]

    # 2. DB명이 API명으로 시작하거나 API명이 DB명으로 시작
    for api_name, units in name_map.items():
        if norm.startswith(api_name) or api_name.startswith(norm):
            if len(min(norm, api_name, key=len)) >= 4:  # 너무 짧은 이름 제외
                return units

    return None


async def main():
    if not MOLIT_API_KEY:
        print("[오류] MOLIT_API_KEY 가 .env에 없습니다.")
        return

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    zero_cnt = conn.execute(
        "SELECT COUNT(*) FROM apartments WHERE units=0 AND geocoded=1"
    ).fetchone()[0]
    total_cnt = conn.execute(
        "SELECT COUNT(*) FROM apartments WHERE geocoded=1"
    ).fetchone()[0]
    print(f"현재: 전체 {total_cnt}개 중 세대수 미확보 {zero_cnt}개")
    print("=" * 60)

    total_updated = 0

    async with httpx.AsyncClient(timeout=30) as client:
        for lawd_cd, gu_name in SEOUL_GU.items():
            print(f"[{gu_name}] 단지정보 조회 중...", end=" ", flush=True)

            items = await fetch_gu_complexes(client, gu_name)
            if not items:
                print("데이터 없음")
                continue

            name_map = build_name_map(items)

            rows = conn.execute(
                "SELECT id, name FROM apartments WHERE lawd_cd=? AND geocoded=1",
                (lawd_cd,)
            ).fetchall()

            updated = 0
            for row in rows:
                units = match_units(row["name"], name_map)
                if units and units > 0:
                    conn.execute(
                        "UPDATE apartments SET units=? WHERE id=?",
                        (units, row["id"])
                    )
                    updated += 1
                    total_updated += 1

            conn.commit()
            print(f"API {len(items)}개 -> DB {updated}/{len(rows)}개 업데이트")
            await asyncio.sleep(0.3)

    conn.close()
    print("=" * 60)
    print(f"[완료] 총 {total_updated}개 세대수 업데이트")

    conn2 = sqlite3.connect(DB_PATH)
    ok   = conn2.execute("SELECT COUNT(*) FROM apartments WHERE units>0 AND geocoded=1").fetchone()[0]
    zero = conn2.execute("SELECT COUNT(*) FROM apartments WHERE units=0 AND geocoded=1").fetchone()[0]
    conn2.close()
    print(f"결과: 세대수 있음 {ok}개 / 없음 {zero}개")


if __name__ == "__main__":
    asyncio.run(main())
