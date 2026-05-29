"""
가격 기준 통일 — 면적 85㎡ 이하 최근 거래만 사용.
- 25개 구 × 최근 12개월 MOLIT 실거래 수집
- area ≤ 85 만 필터링
- aptSeq 단위로 가장 최근 거래 선택
- apartments 테이블의 last_price / area_m2 / last_deal_date 업데이트
"""
import os, sys, asyncio, sqlite3
import xml.etree.ElementTree as ET
from pathlib import Path
from datetime import date, timedelta

sys.path.insert(0, str(Path(__file__).parent.parent))
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")
import httpx

API_KEY = os.getenv("MOLIT_API_KEY", "")
DB = Path(__file__).parent.parent / "data" / "apartments.db"
URL = "https://apis.data.go.kr/1613000/RTMSDataSvcAptTradeDev/getRTMSDataSvcAptTradeDev"

SEOUL_GU = [
    "11110","11140","11170","11200","11215","11230","11260","11290","11305","11320",
    "11350","11380","11410","11440","11470","11500","11530","11545","11560","11590",
    "11620","11650","11680","11710","11740",
]

MONTHS = 36
MAX_AREA = 90.0


async def fetch_ym(client, lawd_cd, ym):
    """한 구의 한 달치 거래 전부 (페이지네이션)"""
    items, page = [], 1
    while True:
        try:
            r = await client.get(URL, params={
                "serviceKey": API_KEY, "LAWD_CD": lawd_cd, "DEAL_YMD": ym,
                "numOfRows": 1000, "pageNo": page,
            }, timeout=30)
            if r.status_code != 200:
                return items
            root = ET.fromstring(r.text)
            recs = root.findall(".//item")
            for it in recs:
                try:
                    area = float(it.findtext("excluUseAr") or 0)
                except ValueError:
                    continue
                if not (0 < area <= MAX_AREA):
                    continue
                price_str = (it.findtext("dealAmount") or "").replace(",", "").strip()
                if not price_str:
                    continue
                try:
                    price = int(price_str)
                except ValueError:
                    continue
                y = it.findtext("dealYear") or ""
                m = (it.findtext("dealMonth") or "").zfill(2)
                d = (it.findtext("dealDay") or "").zfill(2)
                items.append({
                    "aptSeq": (it.findtext("aptSeq") or "").strip(),
                    "name":   (it.findtext("aptNm") or "").strip(),
                    "price":  price,
                    "area":   area,
                    "date":   f"{y}-{m}-{d}",
                    "lawd":   lawd_cd,
                })
            total = int(root.findtext(".//totalCount") or "0")
            if page * 1000 >= total:
                return items
            page += 1
            await asyncio.sleep(0.05)
        except Exception:
            return items


async def main():
    if not API_KEY:
        print("[오류] MOLIT_API_KEY 없음")
        return

    # 최근 12개월 YYYYMM 목록
    today = date.today()
    yms = []
    cur = today.replace(day=1)
    for _ in range(MONTHS):
        yms.append(f"{cur.year}{cur.month:02d}")
        cur = (cur - timedelta(days=1)).replace(day=1)

    # 단지별 가장 최근 ≤85 거래
    latest: dict[str, dict] = {}   # key: aptSeq 또는 name+lawd

    async with httpx.AsyncClient(timeout=30) as client:
        for lawd_cd in SEOUL_GU:
            cnt = 0
            for ym in yms:
                items = await fetch_ym(client, lawd_cd, ym)
                cnt += len(items)
                for it in items:
                    key = it["aptSeq"] or f"{it['name']}|{it['lawd']}"
                    prev = latest.get(key)
                    if (not prev) or (it["date"] > prev["date"]):
                        latest[key] = it
            print(f"[{lawd_cd}] ≤85㎡ 거래 {cnt}건")

    # DB 업데이트
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    upd = 0
    for key, it in latest.items():
        # aptSeq 우선 매칭
        if it["aptSeq"]:
            row = conn.execute("SELECT id FROM apartments WHERE apt_seq=?",
                               (it["aptSeq"],)).fetchone()
        else:
            row = None
        if not row:
            # 이름+lawd 매칭
            row = conn.execute(
                "SELECT id FROM apartments WHERE name=? AND lawd_cd=?",
                (it["name"], it["lawd"])
            ).fetchone()
        if not row:
            continue
        conn.execute(
            "UPDATE apartments SET last_price=?, area_m2=?, last_deal_date=? WHERE id=?",
            (it["price"], it["area"], it["date"], row["id"])
        )
        upd += 1
    conn.commit()

    # 통계
    tot = conn.execute("SELECT COUNT(*) FROM apartments WHERE geocoded=1").fetchone()[0]
    small = conn.execute("SELECT COUNT(*) FROM apartments WHERE geocoded=1 AND area_m2 BETWEEN 1 AND 85 AND last_price>0").fetchone()[0]
    big = conn.execute("SELECT COUNT(*) FROM apartments WHERE geocoded=1 AND area_m2 > 85").fetchone()[0]
    conn.close()
    print(f"\n업데이트 {upd}개")
    print(f"통계: 전체 {tot} / ≤85㎡ {small} / >85㎡ {big}")


if __name__ == "__main__":
    asyncio.run(main())
