"""
K-apt(한국부동산원) 공동주택 기본정보로 대지지분·시공사 매핑
- AptListService3.getSigunguAptList3로 구별 단지목록 한 번에 수집
- 이름·동(as3) 기반으로 우리 DB와 매칭하여 kaptCode 확정
- AptBasisInfoServiceV4.getAphusBassInfoV4로 단지별 대지면적·세대수·시공사 받음
- 평균 대지지분 = kaptTarea / kaptdaCnt (㎡), 평수 환산
"""
import os, sys, asyncio, sqlite3, re
from pathlib import Path
from difflib import SequenceMatcher
from collections import defaultdict
from dotenv import dotenv_values
import httpx

ROOT = Path(__file__).parent.parent
_ENV = dotenv_values(ROOT / ".env")
sys.path.insert(0, str(ROOT))

def _cfg(k): return os.getenv(k) or _ENV.get(k) or ""

# 인코딩된 키 그대로 URL에 박음 (data.go.kr 권장)
KEY = _cfg("PUBLIC_DATA_KEY_ENCODED")
DB = ROOT / "data" / "apartments.db"

SEOUL_GU = ["11680","11740","11305","11500","11620","11215","11530","11545",
            "11350","11320","11230","11590","11440","11410","11650","11200",
            "11290","11710","11470","11560","11170","11380","11140","11110","11260"]

LIST_URL  = "https://apis.data.go.kr/1613000/AptListService3/getSigunguAptList3"
BASIS_URL = "https://apis.data.go.kr/1613000/AptBasisInfoServiceV4/getAphusBassInfoV4"


def _norm(s: str) -> str:
    s = (s or "").replace(" ", "").lower()
    s = re.sub(r"(아파트|단지|차)+$", "", s)
    return s


async def fetch_sigungu_list(c: httpx.AsyncClient, sigungu_code: str) -> list[dict]:
    items = []
    page = 1
    while True:
        url = f"{LIST_URL}?serviceKey={KEY}&sigunguCode={sigungu_code}&pageNo={page}&numOfRows=999&_type=json"
        try:
            r = await c.get(url, timeout=30)
            data = r.json().get("response", {}).get("body", {})
            chunk = data.get("items") or []
            items.extend(chunk)
            total = data.get("totalCount", 0)
            if len(items) >= total or not chunk:
                break
            page += 1
        except Exception as e:
            print(f"  [list {sigungu_code} err] {e}")
            break
    return items


async def fetch_basis(c: httpx.AsyncClient, kapt_code: str) -> dict | None:
    url = f"{BASIS_URL}?serviceKey={KEY}&kaptCode={kapt_code}&_type=json"
    try:
        r = await c.get(url, timeout=15)
        item = r.json().get("response", {}).get("body", {}).get("item")
        return item
    except Exception:
        return None


def match_apt(apt: dict, candidates: list[dict]) -> dict | None:
    """우리 DB 단지 → 같은 구 K-apt 단지목록에서 최적 매칭"""
    apt_name = _norm(apt.get("display_name") or apt.get("name"))
    apt_dong = (apt.get("dong") or "").replace("동", "")
    best, best_score = None, 0.0
    for c in candidates:
        cand_name = _norm(c.get("kaptName"))
        sim = SequenceMatcher(None, cand_name, apt_name).ratio() * 100
        if cand_name in apt_name or apt_name in cand_name:
            sim = max(sim, 90)
        # 동 일치 가산점
        cand_dong = (c.get("as3") or "").replace("동", "")
        if apt_dong and cand_dong and (apt_dong in cand_dong or cand_dong in apt_dong):
            sim += 10
        if sim > best_score:
            best_score = sim
            best = c
    return best if best_score >= 70 else None


async def main():
    if not KEY:
        print("[중단] PUBLIC_DATA_KEY_ENCODED 없음")
        return

    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    apts = conn.execute(
        "SELECT id, name, display_name, dong, lawd_cd, units, built_year "
        "FROM apartments WHERE geocoded=1 AND last_price>0 AND kapt_code IS NULL"
    ).fetchall()
    print(f"매핑 대상 {len(apts)}개 단지")

    # 구별로 그룹화 후 한 번씩만 list API 호출
    by_gu = defaultdict(list)
    for a in apts:
        by_gu[a["lawd_cd"]].append(dict(a))

    async with httpx.AsyncClient() as c:
        # 1단계: 25개 구 단지목록 일괄 수집
        print("\n[1/2] 구별 K-apt 단지목록 수집...")
        sigungu_lists: dict[str, list[dict]] = {}
        sem_list = asyncio.Semaphore(5)
        async def load_gu(gu):
            async with sem_list:
                lst = await fetch_sigungu_list(c, gu)
                sigungu_lists[gu] = lst
                print(f"  {gu}: {len(lst)}개")
        await asyncio.gather(*[load_gu(g) for g in by_gu.keys()])

        # 2단계: 매칭 + 기본정보 fetch
        print("\n[2/2] 매칭 + 단지 기본정보 fetch...")
        sem_basis = asyncio.Semaphore(8)
        results = []

        async def process(apt: dict):
            cands = sigungu_lists.get(apt["lawd_cd"], [])
            matched = match_apt(apt, cands)
            if not matched:
                return apt["id"], None
            kc = matched["kaptCode"]
            async with sem_basis:
                basis = await fetch_basis(c, kc)
            if not basis:
                return apt["id"], None
            try:
                tarea = float(basis.get("kaptTarea") or 0)          # 단지 총 부지면적
                priv  = float(basis.get("privArea") or 0)            # 단지 총 전용면적합
                hh    = float(basis.get("kaptdaCnt") or basis.get("hoCnt") or 0)
                # 정확한 대지지분 = (이 평형 전용면적 / 단지 총 전용면적) × 단지 부지면적
                my_area = float(apt.get("area_m2") or 0)
                if priv > 0 and my_area > 0:
                    share = round((my_area / priv) * tarea, 1)
                elif hh > 0:
                    # priv_area 없으면 단순 평균 fallback
                    share = round(tarea / hh, 1)
                else:
                    share = 0
            except Exception:
                tarea, priv, share = 0, 0, 0
            return apt["id"], {
                "kapt_code": kc,
                "lot_area": tarea,
                "priv_area": priv,
                "land_share": share,
                "builder": basis.get("kaptBcompany") or "",
            }

        tasks = [process(dict(a)) for a in apts]
        done = 0
        for fut in asyncio.as_completed(tasks):
            res = await fut
            results.append(res)
            done += 1
            if done % 200 == 0:
                hit = sum(1 for _, v in results if v)
                print(f"  진행 {done}/{len(tasks)} (매칭 {hit})")

    # DB 일괄 업데이트
    conn2 = sqlite3.connect(DB)
    n_ok = 0
    for aid, v in results:
        if v:
            conn2.execute(
                "UPDATE apartments SET kapt_code=?, lot_area=?, priv_area=?, land_share=?, builder=? WHERE id=?",
                (v["kapt_code"], v["lot_area"], v["priv_area"], v["land_share"], v["builder"], aid),
            )
            n_ok += 1
    conn2.commit()
    conn2.close()
    print(f"\n저장: {n_ok}/{len(results)} 매핑 완료")


if __name__ == "__main__":
    asyncio.run(main())
