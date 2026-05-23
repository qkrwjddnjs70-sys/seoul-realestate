"""apt_seq 컬럼 추가 + 거래 API에서 aptSeq 수집"""
import os, sys, asyncio, sqlite3, xml.etree.ElementTree as ET
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")
import httpx

MOLIT_API_KEY = os.getenv("MOLIT_API_KEY", "")
MOLIT_URL = "https://apis.data.go.kr/1613000/RTMSDataSvcAptTradeDev/getRTMSDataSvcAptTradeDev"
DB_PATH = Path(__file__).parent.parent / "data" / "apartments.db"

SEOUL_DISTRICTS = {
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

def add_column(conn):
    try:
        conn.execute("ALTER TABLE apartments ADD COLUMN apt_seq TEXT DEFAULT ''")
        conn.commit()
        print("apt_seq 컬럼 추가 완료")
    except Exception:
        print("apt_seq 컬럼 이미 존재")

async def fetch_apt_seqs(client, lawd_cd, months=3):
    """거래 API에서 aptNm -> aptSeq 매핑 수집"""
    today = date.today()
    name_to_seq = {}
    for i in range(months):
        d = today.replace(day=1) - timedelta(days=i * 30)
        ym = f"{d.year}{d.month:02d}"
        try:
            resp = await client.get(MOLIT_URL, params={
                "serviceKey": MOLIT_API_KEY,
                "LAWD_CD": lawd_cd,
                "DEAL_YMD": ym,
                "numOfRows": 1000,
                "pageNo": 1,
            })
            root = ET.fromstring(resp.text)
            for item in root.findall(".//item"):
                name = (item.findtext("aptNm") or "").strip()
                seq  = (item.findtext("aptSeq") or "").strip()
                dong = (item.findtext("umdNm") or "").strip()
                if name and seq:
                    name_to_seq[(name, dong)] = seq
        except Exception as e:
            print(f"  [{lawd_cd}] {ym} 오류: {e}")
    return name_to_seq

async def main():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    add_column(conn)

    total_updated = 0
    async with httpx.AsyncClient(timeout=30) as client:
        for lawd_cd, gu_name in SEOUL_DISTRICTS.items():
            print(f"[{gu_name}] aptSeq 수집 중...", end=" ", flush=True)
            name_to_seq = await fetch_apt_seqs(client, lawd_cd)

            rows = conn.execute(
                "SELECT id, name, dong FROM apartments WHERE lawd_cd=? AND geocoded=1",
                (lawd_cd,)
            ).fetchall()

            updated = 0
            for row in rows:
                seq = name_to_seq.get((row["name"], row["dong"]))
                if seq:
                    conn.execute("UPDATE apartments SET apt_seq=? WHERE id=?", (seq, row["id"]))
                    updated += 1
                    total_updated += 1

            conn.commit()
            print(f"{len(name_to_seq)}개 수집 -> {updated}/{len(rows)}개 매핑")
            await asyncio.sleep(0.2)

    conn.close()

    # 결과 확인
    conn2 = sqlite3.connect(DB_PATH)
    has_seq = conn2.execute("SELECT COUNT(*) FROM apartments WHERE apt_seq != '' AND geocoded=1").fetchone()[0]
    print(f"\n[완료] aptSeq 보유: {has_seq}개 / 전체 {conn2.execute('SELECT COUNT(*) FROM apartments WHERE geocoded=1').fetchone()[0]}개")
    conn2.close()

if __name__ == "__main__":
    asyncio.run(main())
