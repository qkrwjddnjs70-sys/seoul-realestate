"""
용적률(FAR) 보강 스크립트
-------------------------
1) ODCloud 공동주택 식별정보(AptIdInfoSvc) → 단지명 → PNU 매핑
2) PNU → 건축물대장 총괄표제부(getBrRecapTitleInfo) → vlRat(용적률)
   vlRat 이 0/없으면 vlRatEstmTotArea / platArea 로 직접 계산

사용법:
  cd backend
  python scripts/enrich_far.py
"""
import os, sys, asyncio, sqlite3
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

import httpx

API_KEY = os.getenv("MOLIT_API_KEY", "")
DB_PATH = Path(__file__).parent.parent / "data" / "apartments.db"

ODCLOUD_URL = "https://api.odcloud.kr/api/AptIdInfoSvc/v1/getAptInfo"
RECAP_URL   = "https://apis.data.go.kr/1613000/BldRgstHubService/getBrRecapTitleInfo"

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
    return (s or "").strip().replace(" ", "").replace("(", "").replace(")", "").replace("-", "")


async def fetch_gu_complexes(client: httpx.AsyncClient, gu_name: str) -> list[dict]:
    """구 단위 공동주택 식별정보 전체 조회"""
    all_items, page = [], 1
    while True:
        try:
            r = await client.get(ODCLOUD_URL, params={
                "serviceKey": API_KEY, "page": page, "perPage": 1000,
                "cond[ADRES::LIKE]": gu_name,
            }, timeout=30)
            if r.status_code != 200:
                break
            data = r.json()
            items = data.get("data") or []
            all_items.extend(items)
            if page * 1000 >= data.get("totalCount", 0):
                break
            page += 1
            await asyncio.sleep(0.1)
        except Exception as e:
            print(f"  ODCloud 오류: {e}")
            break
    return all_items


def build_pnu_map(items: list[dict]) -> dict[str, str]:
    """정규화 단지명 → PNU"""
    result = {}
    for item in items:
        pnu = item.get("PNU")
        if not pnu or len(str(pnu)) != 19:
            continue
        for field in ("COMPLEX_NM1", "COMPLEX_NM2", "COMPLEX_NM3"):
            nm = item.get(field)
            if nm:
                key = _norm(nm)
                if key and key not in result:
                    result[key] = str(pnu)
    return result


def match_pnu(db_name: str, pnu_map: dict[str, str]) -> str | None:
    norm = _norm(db_name)
    if norm in pnu_map:
        return pnu_map[norm]
    for api_name, pnu in pnu_map.items():
        if norm.startswith(api_name) or api_name.startswith(norm):
            if len(min(norm, api_name, key=len)) >= 4:
                return pnu
    return None


async def fetch_far(client: httpx.AsyncClient, pnu: str) -> float | None:
    """PNU → 건축물대장 총괄표제부 → 용적률"""
    sg, bj = pnu[:5], pnu[5:10]
    plat_gb = "0" if pnu[10] == "1" else "1"
    bun, ji = pnu[11:15], pnu[15:19]
    try:
        r = await client.get(RECAP_URL, params={
            "serviceKey": API_KEY, "sigunguCd": sg, "bjdongCd": bj,
            "platGbCd": plat_gb, "bun": bun, "ji": ji,
            "numOfRows": 10, "pageNo": 1, "_type": "json",
        }, timeout=30)
        if r.status_code != 200:
            return None
        items = r.json().get("response", {}).get("body", {}).get("items", {}).get("item")
        if not items:
            return None
        if isinstance(items, dict):
            items = [items]
        # 세대수 가장 큰 레코드 우선
        items.sort(key=lambda x: float(x.get("hhldCnt") or 0), reverse=True)
        for it in items:
            vl = float(it.get("vlRat") or 0)
            if vl > 0:
                return round(vl, 1)
            plat = float(it.get("platArea") or 0)
            est  = float(it.get("vlRatEstmTotArea") or 0)
            if plat > 0 and est > 0:
                return round(est / plat * 100, 1)
        return None
    except Exception:
        return None


async def main():
    if not API_KEY:
        print("[오류] MOLIT_API_KEY 없음")
        return

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    total = conn.execute("SELECT COUNT(*) FROM apartments WHERE geocoded=1").fetchone()[0]
    print(f"대상 아파트: {total}개")
    print("=" * 60)

    total_updated = 0
    async with httpx.AsyncClient(timeout=30) as client:
        for lawd_cd, gu_name in SEOUL_GU.items():
            rows = conn.execute(
                "SELECT id, name FROM apartments WHERE lawd_cd=? AND geocoded=1",
                (lawd_cd,)
            ).fetchall()
            if not rows:
                continue
            print(f"[{gu_name}] 단지정보 조회...", end=" ", flush=True)
            items = await fetch_gu_complexes(client, gu_name)
            pnu_map = build_pnu_map(items)

            updated = 0
            for row in rows:
                pnu = match_pnu(row["name"], pnu_map)
                if not pnu:
                    continue
                far = await fetch_far(client, pnu)
                if far and far > 0:
                    conn.execute("UPDATE apartments SET far=? WHERE id=?", (far, row["id"]))
                    updated += 1
                await asyncio.sleep(0.05)
            conn.commit()
            total_updated += updated
            print(f"PNU {len(pnu_map)}개 → 용적률 {updated}/{len(rows)}개")

    conn.close()
    print("=" * 60)
    print(f"[완료] 용적률 {total_updated}개 업데이트")

    c2 = sqlite3.connect(DB_PATH)
    ok = c2.execute("SELECT COUNT(*) FROM apartments WHERE far>0 AND geocoded=1").fetchone()[0]
    c2.close()
    print(f"결과: 용적률 보유 {ok}개")


if __name__ == "__main__":
    asyncio.run(main())
