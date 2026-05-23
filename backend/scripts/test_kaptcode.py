"""aptSeq -> kaptCode 변환 형식 테스트"""
import os, sys, asyncio, sqlite3
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")
import httpx

MOLIT_API_KEY = os.getenv("MOLIT_API_KEY", "")
DB_PATH = Path(__file__).parent.parent / "data" / "apartments.db"
APT_BASS_URL = "https://apis.data.go.kr/1613000/AptBasisInfoService1/getAphusBassInfo"

def apt_seq_to_kaptcodes(apt_seq: str) -> list[str]:
    """11680-78 -> 여러 가능한 kaptCode 형식 생성"""
    try:
        lawd, seq = apt_seq.split("-")
        seq_n = int(seq)
        return [
            apt_seq,                          # 11680-78 (원본)
            f"A{lawd}{seq_n:06d}",            # A11680000078
            f"{lawd}{seq_n:06d}",             # 11680000078
            f"A{lawd}{seq_n:05d}",            # A1168000078
            f"{lawd}{seq_n:05d}",             # 1168000078
        ]
    except Exception:
        return [apt_seq]

async def main():
    conn = sqlite3.connect(DB_PATH)
    # 샘플 5개 추출
    rows = conn.execute(
        "SELECT name, apt_seq, lawd_cd FROM apartments WHERE apt_seq != '' LIMIT 5"
    ).fetchall()
    conn.close()

    async with httpx.AsyncClient(timeout=15) as c:
        for row in rows:
            name, apt_seq, lawd_cd = row
            print(f"\n[{name}] apt_seq={apt_seq}")
            codes = apt_seq_to_kaptcodes(apt_seq)
            for code in codes:
                r = await c.get(APT_BASS_URL, params={
                    "serviceKey": MOLIT_API_KEY,
                    "kaptCode": code,
                    "numOfRows": 1,
                })
                preview = r.text[:120].replace("\n", " ")
                print(f"  kaptCode={code:20s} -> {r.status_code} | {preview}")
                if r.status_code == 200 and "<item>" in r.text:
                    print("  *** 성공! ***")
                    break

asyncio.run(main())
