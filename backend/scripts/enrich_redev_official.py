"""
서울시 정비사업 OpenAPI 기반 재건축 단계 매핑 (공식 데이터)
- CleanupBussinessProgress 30k+ 이벤트 → BIZ_NO별 최신 단계로 집약
- BIZ_NO 첫 5자리 = lawd_cd, TTL/DTL_CN에 정비구역명 포함
- 우리 DB 아파트와 (lawd_cd + 이름/구역명 토큰 매칭)으로 결합
- redev_stage / redev_detail / redev_updated 업데이트
- AI 추정으로 채운 단지는 공식 데이터로 덮어씀 (출처 우선)
"""
import os, re, sys, asyncio, sqlite3, json
from pathlib import Path
from datetime import datetime
from collections import defaultdict
from dotenv import dotenv_values
import httpx

ROOT = Path(__file__).parent.parent
_ENV = dotenv_values(ROOT / ".env")
sys.path.insert(0, str(ROOT))


def _cfg(k): return os.getenv(k) or _ENV.get(k) or ""


KEY = _cfg("SEOUL_API_KEY_PROGRESS")
DB = ROOT / "data" / "apartments.db"

# 단계 우선순위 (가장 진행된 단계가 우선)
STAGE_ORDER = {
    "안전진단":             1,
    "정비구역지정":         2,
    "추진위원회승인":       3,
    "추진위원회구성승인":   3,
    "조합설립인가":         4,
    "정비사업전문관리업자선정": 4,
    "시공자선정":           5,
    "시공사선정":           5,
    "사업시행인가":         6,
    "사업시행계획인가":     6,
    "관리처분계획인가":     7,
    "관리처분인가":         7,
    "이주":                 8,
    "철거":                 8,
    "착공":                 9,
    "준공":                 10,
}


def _normalize_stage(se_nm: str) -> tuple[str, int]:
    """SE_NM → (표준화된 단계명, 우선순위). 우선순위 0이면 무시"""
    if not se_nm:
        return ("", 0)
    for keyword, prio in STAGE_ORDER.items():
        if keyword in se_nm:
            # 표준 라벨 통일
            if "조합설립" in keyword: return ("조합설립인가", prio)
            if "시공" in keyword:     return ("시공사선정", prio)
            if "사업시행" in keyword: return ("사업시행인가", prio)
            if "관리처분" in keyword: return ("관리처분인가", prio)
            if "이주" in keyword or "철거" in keyword: return ("이주철거", prio)
            return (keyword, prio)
    return (se_nm, 0)


async def fetch_all_progress(client: httpx.AsyncClient) -> list[dict]:
    """CleanupBussinessProgress 전체 페이지 fetch (1000씩)"""
    url0 = f"http://openapi.seoul.go.kr:8088/{KEY}/json/CleanupBussinessProgress/1/1/"
    r0 = await client.get(url0)
    total = r0.json()["CleanupBussinessProgress"]["list_total_count"]
    print(f"총 {total}건")

    rows: list[dict] = []
    PAGE = 1000
    sem = asyncio.Semaphore(5)

    async def get_page(start: int):
        end = min(start + PAGE - 1, total)
        async with sem:
            for _ in range(3):
                try:
                    r = await client.get(
                        f"http://openapi.seoul.go.kr:8088/{KEY}/json/CleanupBussinessProgress/{start}/{end}/",
                        timeout=30,
                    )
                    return r.json().get("CleanupBussinessProgress", {}).get("row", [])
                except Exception:
                    await asyncio.sleep(1)
            return []

    tasks = [get_page(s) for s in range(1, total + 1, PAGE)]
    done = 0
    for fut in asyncio.as_completed(tasks):
        rows.extend(await fut)
        done += 1
        if done % 5 == 0:
            print(f"  페이지 {done}/{len(tasks)}")
    return rows


# 의미 있는 단지명 토큰 추출용
_STOPWORDS = {"구역", "지구", "정비", "재건축", "재개발", "도시환경", "주택",
              "공공", "단지", "일대", "주거환경", "개선사업", "정비사업",
              "사업", "시행", "관리"}


def extract_tokens(text: str) -> set[str]:
    """TTL/DTL_CN에서 단지명/구역명 토큰 추출 (3글자 이상 명사 후보)"""
    if not text:
        return set()
    # 한글 단어 추출
    words = re.findall(r"[가-힣]+", text)
    tokens = set()
    for w in words:
        if len(w) < 3:
            continue
        # 끝의 구역/사업 등 stop 단어 제거
        cleaned = w
        for sw in ["구역", "지구", "정비사업", "정비구역", "사업"]:
            if cleaned.endswith(sw):
                cleaned = cleaned[: -len(sw)]
        cleaned = cleaned.strip()
        if len(cleaned) >= 2 and cleaned not in _STOPWORDS:
            tokens.add(cleaned)
    return tokens


def aggregate_by_biz(rows: list[dict]) -> dict[str, dict]:
    """BIZ_NO별로 집약: 최신 단계, 모든 TTL 토큰, lawd_cd"""
    biz: dict[str, dict] = {}
    for r in rows:
        bn = r.get("BIZ_NO") or ""
        if not bn or "-" not in bn:
            continue
        lawd = bn.split("-")[0][:5]
        se_nm = r.get("SE_NM") or ""
        day = r.get("DAY") or ""
        ttl = r.get("TTL") or ""
        dtl_cn = r.get("DTL_CN") or ""

        std_stage, prio = _normalize_stage(se_nm)
        if prio == 0:
            continue

        if bn not in biz:
            biz[bn] = {
                "lawd": lawd,
                "best_prio": 0,
                "best_stage": "",
                "best_date": "",
                "tokens": set(),
                "titles": [],
            }
        b = biz[bn]
        b["tokens"] |= extract_tokens(ttl) | extract_tokens(dtl_cn)
        if ttl:
            b["titles"].append(ttl)
        # 더 진행된 단계 우선, 같으면 최신 날짜
        if prio > b["best_prio"] or (prio == b["best_prio"] and day > b["best_date"]):
            b["best_prio"] = prio
            b["best_stage"] = std_stage
            b["best_date"] = day
    return biz


def match_apartments(biz: dict[str, dict], conn: sqlite3.Connection) -> list[tuple[int, str, str]]:
    """각 아파트에 매칭되는 BIZ_NO 찾기 → (apt_id, stage, detail) 리스트"""
    # 재건축 후보만 대상: 2005년 이전 준공 단지 (신축은 재건축 대상 아님)
    rows = conn.execute(
        "SELECT id, name, display_name, dong, lawd_cd, address, built_year "
        "FROM apartments WHERE geocoded=1 AND last_price>0 "
        "AND built_year BETWEEN 1 AND 2004 "
        "AND (redev_manual IS NULL OR redev_manual=0)"
    ).fetchall()

    # lawd_cd별 BIZ 인덱싱
    by_lawd: dict[str, list[tuple[str, dict]]] = defaultdict(list)
    for bn, b in biz.items():
        by_lawd[b["lawd"]].append((bn, b))

    updates = []
    for r in rows:
        lawd = r["lawd_cd"] or ""
        if not lawd or lawd not in by_lawd:
            continue
        apt_name = (r["display_name"] or r["name"] or "").replace(" ", "")
        apt_dong = (r["dong"] or "").replace("동", "")

        best_match = None
        best_score = 0
        for bn, b in by_lawd[lawd]:
            score = 0
            # 토큰 매칭: 단지명 안에 정비구역 토큰이 포함되거나 그 반대
            for tok in b["tokens"]:
                if len(tok) < 3:           # 2글자 토큰은 너무 흔해서 제외
                    continue
                if tok in apt_name:
                    score += 5 if len(tok) >= 4 else 3
                elif apt_name in tok and len(apt_name) >= 4:
                    score += 4
            if score > best_score:
                best_score = score
                best_match = (bn, b)

        # 임계값: 단지명과 정비구역명 토큰이 실제로 겹쳐야 인정
        if best_match and best_score >= 4:
            bn, b = best_match
            stage = b["best_stage"]
            date = b["best_date"]
            date_fmt = f"{date[:4]}.{date[4:6]}" if len(date) >= 6 else date
            # 정비구역명 추정 (가장 긴 title 첫 단어)
            zone = ""
            if b["titles"]:
                t = max(b["titles"], key=len)
                m = re.match(r"([가-힣A-Za-z0-9\-]+(?:구역|지구|단지)?)", t)
                if m:
                    zone = m.group(1)
            detail_parts = [stage]
            if date_fmt: detail_parts.append(date_fmt)
            if zone: detail_parts.append(zone)
            detail = " / ".join(detail_parts) + " (서울시 공식)"
            updates.append((r["id"], stage, detail))

    return updates


async def main():
    if not KEY:
        print("[중단] SEOUL_API_KEY_PROGRESS 없음")
        return
    print("=== 서울시 정비사업 추진경과 일괄 수집 ===")
    async with httpx.AsyncClient(timeout=30) as c:
        rows = await fetch_all_progress(c)
    print(f"받은 이벤트 {len(rows)}건")

    biz = aggregate_by_biz(rows)
    print(f"BIZ_NO 집약 {len(biz)}개 (단계 우선순위 0인 행 제외)")

    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    updates = match_apartments(biz, conn)
    print(f"매칭된 아파트 {len(updates)}개")

    today = datetime.now().strftime("%Y-%m-%d")
    for apt_id, stage, detail in updates:
        conn.execute(
            "UPDATE apartments SET redev_stage=?, redev_detail=?, redev_updated=? WHERE id=?",
            (stage, detail, today, apt_id),
        )
    conn.commit()

    # 통계
    stats = dict(conn.execute(
        "SELECT redev_stage, COUNT(*) FROM apartments WHERE redev_stage IS NOT NULL "
        "AND redev_stage != '' GROUP BY redev_stage"
    ).fetchall())
    conn.close()

    print("\n=== 단계별 분포 ===")
    for s, n in sorted(stats.items(), key=lambda x: -x[1]):
        print(f"  {s}: {n}개")


if __name__ == "__main__":
    asyncio.run(main())
