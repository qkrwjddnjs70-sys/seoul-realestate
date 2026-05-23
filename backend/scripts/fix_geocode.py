"""
geocoded=0 단지들의 좌표를 Kakao 주소→좌표 API로 재시도.
지저분한 주소("서울시 동작구, 서울 영등포구 신길동 4518")는 정리 후 조회.
"""
import os, sys, re, time
from pathlib import Path
import sqlite3
import httpx
sys.path.insert(0, str(Path(__file__).parent.parent))
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

KAKAO = os.getenv("KAKAO_REST_KEY", "")
HEADERS = {"Authorization": f"KakaoAK {KAKAO}"}
DB = Path(__file__).parent.parent / "data" / "apartments.db"

ADDR_URL = "https://dapi.kakao.com/v2/local/search/address.json"
KEY_URL  = "https://dapi.kakao.com/v2/local/search/keyword.json"


def clean_addr(addr: str) -> str:
    """ '서울시 동작구, 서울 영등포구 신길동 4518' → '서울 영등포구 신길동 4518' """
    if not addr:
        return ""
    s = addr.strip()
    # 콤마 분리되어 있으면 마지막 토큰(가장 자세한 주소) 사용
    if "," in s:
        parts = [p.strip() for p in s.split(",") if p.strip()]
        s = parts[-1]
    # '서울시' → '서울'
    s = re.sub(r"^서울특별시\s*", "서울 ", s)
    s = re.sub(r"^서울시\s*", "서울 ", s)
    return s.strip()


def geocode(client, addr, name):
    cleaned = clean_addr(addr)
    if not cleaned:
        return None
    # 1) 주소 검색
    try:
        r = client.get(ADDR_URL, headers=HEADERS, params={"query": cleaned}, timeout=10)
        if r.status_code == 200:
            docs = r.json().get("documents", [])
            if docs:
                d = docs[0]
                return float(d["y"]), float(d["x"])
    except Exception:
        pass
    # 2) 키워드 검색 (단지명 + 동)
    dong_match = re.search(r"(\S+동)\s+\d", cleaned)
    dong = dong_match.group(1) if dong_match else ""
    try:
        q = f"{dong} {name}".strip() if dong else f"{name} {cleaned}"
        r = client.get(KEY_URL, headers=HEADERS, params={"query": q, "size": 3}, timeout=10)
        if r.status_code == 200:
            docs = r.json().get("documents", [])
            if docs:
                d = docs[0]
                return float(d["y"]), float(d["x"])
    except Exception:
        pass
    return None


def main():
    if not KAKAO:
        print("[오류] KAKAO_REST_KEY 없음")
        return
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT id, name, address FROM apartments WHERE geocoded=0 AND last_price>0"
    ).fetchall()
    print(f"대상 {len(rows)}개")
    print("=" * 60)

    fixed, miss = 0, []
    with httpx.Client(timeout=10) as client:
        for i, row in enumerate(rows, 1):
            res = geocode(client, row["address"], row["name"])
            if res:
                lat, lng = res
                conn.execute("UPDATE apartments SET lat=?, lng=?, geocoded=1 WHERE id=?",
                             (lat, lng, row["id"]))
                fixed += 1
                if i % 20 == 0:
                    conn.commit()
                    print(f"  ... {i}/{len(rows)} (성공 {fixed})")
            else:
                miss.append((row["id"], row["name"], row["address"]))
            time.sleep(0.03)
    conn.commit()
    conn.close()
    print(f"\n복구: {fixed}/{len(rows)}")
    if miss[:10]:
        print("\n실패 샘플:")
        for m in miss[:10]:
            print(f"  id={m[0]} '{m[1]}' addr='{m[2]}'")


if __name__ == "__main__":
    main()
