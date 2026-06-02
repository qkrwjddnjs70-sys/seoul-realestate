"""
정비사업 정보몽땅 1112개 사업장 → 대표지번 좌표 변환 (Kakao Local)
- cleanup_projects.json (gu, type, name, dong, jibun, stage)
- "영등포구 문래동4가 23-6" 식 주소를 Kakao 주소검색 → lat/lng
- 결과: data/redev_points.json [{name,type,stage,gu,dong,jibun,lat,lng}]
"""
import sys, json, time, os
sys.stdout.reconfigure(encoding='utf-8')
from pathlib import Path
from dotenv import dotenv_values
import httpx

ROOT = Path(__file__).parent.parent
_ENV = dotenv_values(ROOT / ".env")
KAKAO = os.getenv("KAKAO_REST_KEY") or _ENV.get("KAKAO_REST_KEY") or ""
HDR = {"Authorization": f"KakaoAK {KAKAO}"}
ADDR_URL = "https://dapi.kakao.com/v2/local/search/address.json"

proj = json.loads((ROOT / "data" / "cleanup_projects.json").read_text(encoding="utf-8"))
DEAD = {"조합해산", "조합청산", "청산 및 조합해산", "이전고시"}

def geocode(client, gu, jibun):
    # "문래동4가 23-6" → "서울 영등포구 문래동4가 23-6"
    q = f"서울 {gu} {jibun}".strip()
    for query in (q, f"서울특별시 {gu} {jibun}"):
        try:
            r = client.get(ADDR_URL, headers=HDR, params={"query": query, "size": 1})
            docs = r.json().get("documents", [])
            if docs:
                d = docs[0]
                return float(d["y"]), float(d["x"])
        except Exception:
            pass
    return None

def main():
    if not KAKAO:
        print("[중단] KAKAO_REST_KEY 없음"); return
    out = []
    seen = set()
    with httpx.Client(timeout=10) as c:
        done = 0
        for p in proj:
            done += 1
            if p["stage"] in DEAD:
                continue
            if not p.get("jibun") or p["jibun"] == "nan":
                continue
            key = (p["gu"], p["jibun"], p["name"])
            if key in seen:
                continue
            seen.add(key)
            coord = geocode(c, p["gu"], p["jibun"])
            if coord:
                out.append({
                    "name": p["name"][:40], "type": p["type"][:14], "stage": p["stage"],
                    "gu": p["gu"], "dong": p.get("dong", ""), "jibun": p["jibun"],
                    "lat": coord[0], "lng": coord[1],
                })
            if done % 100 == 0:
                print(f"  {done}/{len(proj)} (변환 {len(out)})")
            time.sleep(0.03)
    (ROOT / "data" / "redev_points.json").write_text(
        json.dumps(out, ensure_ascii=False), encoding="utf-8")
    print(f"\n저장: redev_points.json ({len(out)}개 좌표 변환 / 전체 {len(proj)})")

if __name__ == "__main__":
    main()
