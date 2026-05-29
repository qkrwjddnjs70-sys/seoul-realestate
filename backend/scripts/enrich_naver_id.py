"""
네이버 부동산 단지 ID(hscpNo) 일괄 매핑
- 각 아파트 좌표 주변에서 m.land.naver.com cluster API 호출
- 단지명·세대수·준공연도가 가장 잘 맞는 hscpNo 선택
- DB naver_id 컬럼에 저장
"""
import os, sys, re, asyncio, sqlite3
from pathlib import Path
from difflib import SequenceMatcher
import httpx

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

DB = ROOT / "data" / "apartments.db"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; SeoulRE/1.0)"}
URL = "https://m.land.naver.com/cluster/ajax/complexList"


def _norm(s: str) -> str:
    return re.sub(r"\s+", "", (s or "")).lower()


async def lookup(c: httpx.AsyncClient, apt: dict) -> str | None:
    lat, lng = apt["lat"], apt["lng"]
    if not lat or not lng:
        return None
    # 좌표 주변 약 300m bbox
    delta = 0.004
    params = {
        "itemId": "", "mapKey": "", "lgeo": "", "showR0": "",
        "rletTpCd": "APT", "tradTpCd": "",
        "z": 17, "lat": lat, "lon": lng,
        "btm": lat - delta, "lft": lng - delta,
        "top": lat + delta, "rgt": lng + delta,
    }
    for _ in range(2):
        try:
            r = await c.get(URL, params=params, headers=HEADERS, timeout=10)
            if r.status_code != 200:
                return None
            results = r.json().get("result") or []
            if not results:
                return None

            target_name = _norm(apt.get("display_name") or apt.get("name"))
            target_units = apt.get("units") or 0
            target_year = apt.get("built_year") or 0

            best = None
            best_score = 0.0
            for item in results:
                cand = _norm(item.get("hscpNm"))
                # 이름 유사도
                name_sim = SequenceMatcher(None, cand, target_name).ratio()
                if cand in target_name or target_name in cand:
                    name_sim = max(name_sim, 0.9)
                score = name_sim * 100
                # 세대수 보정 (큰 차이는 감점)
                cand_units = item.get("totHsehCnt") or 0
                if target_units and cand_units:
                    diff = abs(cand_units - target_units) / max(target_units, cand_units)
                    score -= diff * 30
                # 준공연도 보정
                cand_year_str = (item.get("useAprvYmd") or "")[:4]
                if cand_year_str.isdigit() and target_year:
                    score -= abs(int(cand_year_str) - target_year) * 0.8
                if score > best_score:
                    best_score = score
                    best = item

            # 최소 임계값 (이름 유사도 너무 낮으면 거부)
            if best and best_score >= 55:
                return best.get("hscpNo")
            return None
        except Exception:
            await asyncio.sleep(0.5)
    return None


async def main():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT id, name, display_name, lat, lng, units, built_year "
        "FROM apartments WHERE geocoded=1 AND last_price>0 AND naver_id IS NULL"
    ).fetchall()
    conn.close()
    print(f"매핑 대상 {len(rows)}개")

    sem = asyncio.Semaphore(8)

    async def worker(r):
        async with sem:
            nid = await lookup(c, dict(r))
            return r["id"], r["name"], nid

    async with httpx.AsyncClient() as c:
        tasks = [worker(r) for r in rows]
        results = []
        done = 0
        for fut in asyncio.as_completed(tasks):
            res = await fut
            results.append(res)
            done += 1
            if res[2]:
                if done % 50 == 0:
                    print(f"  [{done}/{len(rows)}] {res[1]} → hscpNo={res[2]}")
            if done % 100 == 0:
                hit = sum(1 for _, _, n in results if n)
                print(f"  진행 {done}/{len(rows)} (매칭 {hit})")

    # DB 일괄 저장
    conn = sqlite3.connect(DB)
    n_hit = 0
    for aid, _, nid in results:
        if nid:
            conn.execute("UPDATE apartments SET naver_id=? WHERE id=?", (nid, aid))
            n_hit += 1
    conn.commit()
    conn.close()
    print(f"\n저장: {n_hit}/{len(results)} 매핑 완료")


if __name__ == "__main__":
    asyncio.run(main())
