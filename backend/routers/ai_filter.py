"""
종합 AI 분석 — 사용자가 자연어로 조건 입력
- Claude Haiku가 자연어 → 구조화 필터 JSON 파싱
- DB에서 후보 필터링
- 점수 계산 (가격, 도보, 세대수, 평지, 성장률, 인프라) → Top 30 반환
"""
import os, json, sqlite3
from fastapi import APIRouter, Body
from dotenv import dotenv_values
import anthropic

import database as db_module

router = APIRouter()

_ENV = dotenv_values(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))
def _cfg(k): return os.getenv(k) or _ENV.get(k) or ""
_KEY = _cfg("ANTHROPIC_API_KEY")
_anthropic = anthropic.AsyncAnthropic(api_key=_KEY) if _KEY else None


PARSE_SYSTEM = """당신은 한국 부동산 검색 조건 파서입니다.
사용자가 자연어로 입력한 매물 조건을 JSON으로 정확히 변환합니다.

규칙:
- 가격 단위는 만원입니다 (12억 → 120000)
- 도보 분은 정수
- 세대수는 정수 (수백세대 → 300, 대단지 → 500)
- area_bands: 평형 언급 없으면 빈 리스트, "소형/원룸/투룸/50대" → ["50"], "중형/30평/80대" → ["80"], "전부" → ["50","80"]
- prefer_growth, prefer_livability: 0~1 가중치 (언급 강도에 따라)
- prefer_flat: true면 평지 선호 (slope 작은 곳 가산)
- min_land_share: 대지지분 최소값(㎡) — "대지지분 20㎡ 이상", "재건축 메리트", "땅 지분 큰 곳" 등의 표현에 반응
- regions: 구·동 이름 (예: ["마포구", "영등포구"])
- 명시 안 된 필드는 null

응답은 반드시 JSON 한 개만, 다른 설명 금지."""


PARSE_SCHEMA = {
    "type": "object",
    "properties": {
        "max_price":         {"type": ["integer", "null"]},
        "min_price":         {"type": ["integer", "null"]},
        "max_walk_minutes":  {"type": ["integer", "null"]},
        "min_units":         {"type": ["integer", "null"]},
        "max_built_year":    {"type": ["integer", "null"]},
        "min_built_year":    {"type": ["integer", "null"]},
        "min_land_share":    {"type": ["number", "null"]},
        "area_bands":        {"type": "array",  "items": {"type": "string"}},
        "prefer_flat":       {"type": "boolean"},
        "prefer_growth":     {"type": "number"},
        "prefer_livability": {"type": "number"},
        "regions":           {"type": "array",  "items": {"type": "string"}},
        "interpretation":    {"type": "string", "description": "사용자 조건 한 줄 요약"},
    },
    "required": ["interpretation"],
}


GU_BY_NAME = {}
for full, code in [
    ("종로구","11110"),("중구","11140"),("용산구","11170"),("성동구","11200"),
    ("광진구","11215"),("동대문구","11230"),("중랑구","11260"),("성북구","11290"),
    ("강북구","11305"),("도봉구","11320"),("노원구","11350"),("은평구","11380"),
    ("서대문구","11410"),("마포구","11440"),("양천구","11470"),("강서구","11500"),
    ("구로구","11530"),("금천구","11545"),("영등포구","11560"),("동작구","11590"),
    ("관악구","11620"),("서초구","11650"),("강남구","11680"),("송파구","11710"),
    ("강동구","11740"),
]:
    GU_BY_NAME[full] = code
    GU_BY_NAME[full[:-1]] = code


async def _parse_query(query: str) -> dict:
    """자연어 → 구조화 조건"""
    if not _anthropic:
        return {"interpretation": "AI 키 없음", "max_price": None}
    msg = await _anthropic.messages.create(
        model="claude-haiku-4-5",
        max_tokens=600,
        system=PARSE_SYSTEM,
        tools=[{"name": "set_criteria", "description": "조건", "input_schema": PARSE_SCHEMA}],
        tool_choice={"type": "tool", "name": "set_criteria"},
        messages=[{"role": "user", "content": query}],
    )
    for block in msg.content:
        if block.type == "tool_use":
            return block.input
    return {"interpretation": "파싱 실패"}


def _score(row: dict, c: dict) -> tuple[float, list[str]]:
    """후보 단지 점수 + 추천 이유"""
    score = 50.0
    reasons = []

    # 가격 — 예산 대비
    price = row.get("last_price") or 0
    if c.get("max_price") and price > 0:
        ratio = price / c["max_price"]
        if ratio <= 0.85:
            score += 12; reasons.append(f"예산 여유 ({price//10000}억)")
        elif ratio <= 1.0:
            score += 5

    # 도보
    walk = row.get("walk_minutes") or 99
    max_walk = c.get("max_walk_minutes") or 10
    if walk <= 5:
        score += 18; reasons.append(f"{row.get('nearest_subway','')}역 도보 {walk}분")
    elif walk <= max_walk:
        score += 10; reasons.append(f"{row.get('nearest_subway','')}역 도보 {walk}분")
    else:
        score -= 5

    # 세대수
    units = row.get("units") or 0
    min_units = c.get("min_units") or 0
    if min_units and units >= min_units * 1.5:
        score += 15; reasons.append(f"대단지 {units}세대")
    elif min_units and units >= min_units:
        score += 8; reasons.append(f"{units}세대")
    elif units >= 500:
        score += 6; reasons.append(f"{units}세대")

    # 대지지분 (이론): 공급면적 / 용적률 = (area / 0.75) × 100 / far
    ar = row.get("area_m2") or 0
    fa = row.get("far") or 0
    ls = round(ar * 133.3 / fa, 1) if (ar and fa > 0) else 0
    if ls > 0:
        if ls >= 25:
            score += 14; reasons.append(f"대지지분 {ls:.1f}㎡(큼)")
        elif ls >= 18:
            score += 8; reasons.append(f"대지지분 {ls:.1f}㎡")
        elif ls >= 12:
            score += 3

    # 평지
    slope = row.get("slope") or 0
    if c.get("prefer_flat"):
        if slope < 10:
            score += 12; reasons.append("평지")
        elif slope < 25:
            score += 4
        else:
            score -= 6; reasons.append(f"경사 {int(slope)}m")

    # 성장성 — 가격 상승률은 trend 필요, 여기서는 신축 + 대단지 + 호재 키 가산
    growth = c.get("prefer_growth") or 0
    if growth > 0:
        by = row.get("built_year") or 0
        if by >= 2015:
            score += 8 * growth; reasons.append(f"{by}년 준공(신축)")
        elif by >= 2005:
            score += 4 * growth
        far = row.get("far") or 0
        if 0 < far < 200:
            score += 6 * growth; reasons.append("재건축 여지(저용적률)")

    # 실거주 — 평지·도보·대단지가 이미 가산되므로 가벼운 보너스만
    liv = c.get("prefer_livability") or 0
    if liv > 0 and units >= 300 and walk <= 10:
        score += 4 * liv

    return score, reasons


@router.post("")
async def ai_filter(payload: dict = Body(...)):
    query = (payload or {}).get("query", "").strip()
    if not query:
        return {"error": "조건을 입력해주세요"}

    criteria = await _parse_query(query)

    # SQL 1차 필터
    where = ["geocoded=1", "last_price > 0", "area_m2 BETWEEN 1 AND 90"]
    params: list = []
    if criteria.get("max_price"):
        where.append("last_price <= ?"); params.append(int(criteria["max_price"]))
    if criteria.get("min_price"):
        where.append("last_price >= ?"); params.append(int(criteria["min_price"]))
    if criteria.get("max_walk_minutes"):
        where.append("walk_minutes > 0 AND walk_minutes <= ?"); params.append(int(criteria["max_walk_minutes"]))
    if criteria.get("min_units"):
        where.append("units >= ?"); params.append(int(criteria["min_units"]))
    # min_land_share 조건은 Python 단에서 (용적률 역산이라 SQL로 직접 불가)
    if criteria.get("max_built_year"):
        where.append("built_year <= ?"); params.append(int(criteria["max_built_year"]))
    if criteria.get("min_built_year"):
        where.append("built_year >= ?"); params.append(int(criteria["min_built_year"]))
    regions = criteria.get("regions") or []
    lawd_codes = [GU_BY_NAME[r.replace(" ", "")] for r in regions if r.replace(" ", "") in GU_BY_NAME]
    if lawd_codes:
        where.append(f"lawd_cd IN ({','.join('?'*len(lawd_codes))})")
        params.extend(lawd_codes)

    sql = f"SELECT * FROM apartments WHERE {' AND '.join(where)} LIMIT 600"
    conn = db_module.get_db()
    rows = [dict(r) for r in conn.execute(sql, params).fetchall()]
    conn.close()

    # 평형 필터 (Python 단)
    bands = criteria.get("area_bands") or []
    if bands:
        kept = []
        for r in rows:
            best_p, best_a, best_d = 0, 0, ""
            for b in bands:
                p = r.get(f"price_{b}") or 0
                if p > 0:
                    d = r.get(f"date_{b}") or ""
                    if not best_d or d > best_d:
                        best_p, best_a, best_d = p, r.get(f"area_{b}") or 0, d
            if best_p > 0:
                # 평형 가격으로 last_price 덮어쓰기 (예산 필터 다시)
                if criteria.get("max_price") and best_p > criteria["max_price"]:
                    continue
                r["last_price"] = best_p
                r["area_m2"] = best_a
                r["last_deal_date"] = best_d
                kept.append(r)
        rows = kept

    # 대지지분 최소 조건 — 이론값(공급/용적률) 기준 Python 필터
    min_ls = criteria.get("min_land_share") or 0
    if min_ls > 0:
        rows = [r for r in rows
                if r.get("far") and r["far"] > 0 and r.get("area_m2")
                and (r["area_m2"] * 133.3 / r["far"]) >= min_ls]

    # 점수 계산
    scored = []
    for r in rows:
        sc, rs = _score(r, criteria)
        scored.append((sc, rs, r))
    scored.sort(key=lambda x: -x[0])

    top = scored[:30]
    result = []
    for sc, rs, r in top:
        result.append({
            "id":             r["id"],
            "name":           r.get("display_name") or r["name"],
            "address":        r["address"],
            "lat":            r["lat"],
            "lng":            r["lng"],
            "last_price":     r["last_price"],
            "area_m2":        r["area_m2"],
            "last_deal_date": r["last_deal_date"],
            "units":          r["units"],
            "built_year":     r["built_year"],
            "nearest_subway": r["nearest_subway"],
            "walk_minutes":   r["walk_minutes"],
            "slope":          r["slope"],
            "land_share":     (
                round(r["area_m2"] * 133.3 / r["far"], 1)
                if (r.get("far") and r["far"] > 0 and r.get("area_m2")) else 0
            ),
            "score":          round(sc, 1),
            "reasons":        rs,
        })

    return {
        "criteria":       criteria,
        "interpretation": criteria.get("interpretation", ""),
        "total_matched":  len(rows),
        "results":        result,
    }
