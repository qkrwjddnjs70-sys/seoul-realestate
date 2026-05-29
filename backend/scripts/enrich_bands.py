"""
각 단지의 50대(50~60㎡) / 80대(80~90㎡) 별로 가장 최근 거래를 따로 저장.
- MOLIT 25개 구 × 최근 12개월 거래 전체 수집
- aptSeq 기준 그룹핑, 면적대별 최신 1건 추출
- DB columns price_50/area_50/date_50, price_80/area_80/date_80 업데이트
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


def band_of(area):
    if 50 <= area <= 60:
        return "50"
    if 80 <= area <= 90:
        return "80"
    return None


async def fetch_ym(client, lawd_cd, ym):
    out, page = [], 1
    while True:
        try:
            r = await client.get(URL, params={
                "serviceKey": API_KEY, "LAWD_CD": lawd_cd, "DEAL_YMD": ym,
                "numOfRows": 1000, "pageNo": page,
            }, timeout=30)
            if r.status_code != 200:
                return out
            root = ET.fromstring(r.text)
            for it in root.findall(".//item"):
                try:
                    area = float(it.findtext("excluUseAr") or 0)
                except ValueError:
                    continue
                band = band_of(area)
                if not band:
                    continue
                price_s = (it.findtext("dealAmount") or "").replace(",", "").strip()
                if not price_s:
                    continue
                try:
                    price = int(price_s)
                except ValueError:
                    continue
                y = it.findtext("dealYear") or ""
                m = (it.findtext("dealMonth") or "").zfill(2)
                d = (it.findtext("dealDay") or "").zfill(2)
                out.append({
                    "aptSeq": (it.findtext("aptSeq") or "").strip(),
                    "name":   (it.findtext("aptNm") or "").strip(),
                    "umd":    (it.findtext("umdNm") or "").strip(),
                    "lawd":   lawd_cd,
                    "band":   band,
                    "price":  price,
                    "area":   area,
                    "date":   f"{y}-{m}-{d}",
                })
            total = int(root.findtext(".//totalCount") or "0")
            if page * 1000 >= total:
                return out
            page += 1
            await asyncio.sleep(0.05)
        except Exception:
            return out


async def main():
    if not API_KEY:
        print("MOLIT_API_KEY 없음"); return

    today = date.today()
    yms = []
    cur = today.replace(day=1)
    for _ in range(MONTHS):
        yms.append(f"{cur.year}{cur.month:02d}")
        cur = (cur - timedelta(days=1)).replace(day=1)

    # (aptSeq, band) → most recent deal
    latest: dict = {}
    async with httpx.AsyncClient(timeout=30) as client:
        for lawd_cd in SEOUL_GU:
            cnt = 0
            for ym in yms:
                items = await fetch_ym(client, lawd_cd, ym)
                cnt += len(items)
                for it in items:
                    key = (it["aptSeq"] or f"{it['name']}|{it['lawd']}", it["band"])
                    prev = latest.get(key)
                    if (not prev) or (it["date"] > prev["date"]):
                        latest[key] = it
            print(f"[{lawd_cd}] {cnt}건")

    # DB update
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    upd = 0
    seq_fix = 0
    for key, it in latest.items():
        seq_or_name, band = key
        if it["aptSeq"]:
            row = conn.execute("SELECT id FROM apartments WHERE apt_seq=?", (it["aptSeq"],)).fetchone()
        else:
            row = None
        # 1차 fallback — name + lawd + dong(umdNm) 까지 매칭 (다중 단지 동명이인 방지)
        if not row and it.get("umd"):
            row = conn.execute(
                "SELECT id FROM apartments WHERE name=? AND lawd_cd=? AND dong LIKE ?",
                (it["name"], it["lawd"], f"%{it['umd']}%")
            ).fetchone()
        # 2차 fallback — name + lawd, 단 결과가 정확히 1개일 때만 (모호하면 skip)
        if not row:
            cand = conn.execute(
                "SELECT id FROM apartments WHERE name=? AND lawd_cd=?",
                (it["name"], it["lawd"])
            ).fetchall()
            if len(cand) == 1:
                row = cand[0]
        # 양방향 substring fallback (apt_seq·name 정확 매칭 실패 시)
        if not row and it["aptSeq"]:
            norm_molit = (it["name"] or "").replace(" ", "")
            cands = conn.execute(
                "SELECT id, name, display_name FROM apartments "
                "WHERE lawd_cd=? AND (apt_seq IS NULL OR apt_seq='')",
                (it["lawd"],)
            ).fetchall()
            for cr in cands:
                for cand_name in (cr["name"], cr["display_name"]):
                    if not cand_name:
                        continue
                    norm_db = cand_name.replace(" ", "")
                    if len(norm_db) >= 2 and (norm_db in norm_molit or norm_molit in norm_db):
                        row = cr
                        conn.execute("UPDATE apartments SET apt_seq=? WHERE id=?",
                                     (it["aptSeq"], cr["id"]))
                        seq_fix += 1
                        break
                if row:
                    break
        if not row:
            continue
        # apt_seq 누락 단지면 같이 채워주기
        if it["aptSeq"]:
            current_seq = conn.execute("SELECT apt_seq FROM apartments WHERE id=?", (row["id"],)).fetchone()
            if not current_seq[0]:
                conn.execute("UPDATE apartments SET apt_seq=? WHERE id=?", (it["aptSeq"], row["id"]))
                seq_fix += 1
        col_p, col_a, col_d = f"price_{band}", f"area_{band}", f"date_{band}"
        conn.execute(f"UPDATE apartments SET {col_p}=?, {col_a}=?, {col_d}=? WHERE id=?",
                     (it["price"], it["area"], it["date"], row["id"]))
        upd += 1
    print(f"apt_seq 신규 채움: {seq_fix}개")
    conn.commit()
    print(f"\n업데이트 {upd}개")

    # 통계
    n50 = conn.execute("SELECT COUNT(*) FROM apartments WHERE price_50>0").fetchone()[0]
    n80 = conn.execute("SELECT COUNT(*) FROM apartments WHERE price_80>0").fetchone()[0]
    both = conn.execute("SELECT COUNT(*) FROM apartments WHERE price_50>0 AND price_80>0").fetchone()[0]
    conn.close()
    print(f"50대 보유 {n50} / 80대 보유 {n80} / 둘 다 {both}")


if __name__ == "__main__":
    asyncio.run(main())
