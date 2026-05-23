"""
최대 3개 단지·지역 비교 분석 — Claude Sonnet 4.6
- 호재 글 (뉴스/블로그/카페 각 30개)
- DB 시세 통계 (해당 동의 평균/중앙값)
- Kakao 인프라 카운트 (1km 반경 학교/병원/마트/지하철 등)
"""
import os, re, json, asyncio, difflib
from typing import List
import httpx
from dotenv import dotenv_values
from fastapi import APIRouter, Query

import database as db_module
from routers.hojae import _naver_search, _interleave, KINDS, _anthropic


def _normalize_apt_query(q: str) -> str:
    """단지명 입력 정규화 — 띄어쓰기·끝의 차/단지/아파트 제거"""
    qn = (q or "").replace(" ", "").strip()
    return re.sub(r"(차|단지|아파트)+$", "", qn)

router = APIRouter()

# 카카오 키
_ENV = dotenv_values(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))
KAKAO_KEY = os.getenv("KAKAO_REST_KEY") or _ENV.get("KAKAO_REST_KEY") or ""
KAKAO_HEADERS = {"Authorization": f"KakaoAK {KAKAO_KEY}"}

# 구 이름 → lawd_cd (마포·강남 같은 구 단위 비교 시 사용)
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
    GU_BY_NAME[full[:-1]] = code   # "마포" → 11440


# 카카오 카테고리: 인프라 카운트용
INFRA_CODES = {
    "지하철역": "SW8",
    "학교":     "SC4",
    "병원":     "HP8",
    "대형마트": "MT1",
    "편의점":   "CS2",
    "카페":     "CE7",
    "음식점":   "FD6",
}


def _find_apartment(q: str) -> dict | None:
    """단지 매칭 — 짧은/모호한 입력(구·동 이름)은 매칭하지 않음"""
    if not db_module.db_exists() or not q:
        return None
    qn_raw = q.replace(" ", "").strip()
    if len(qn_raw) < 3:
        return None
    if qn_raw in GU_BY_NAME:
        return None
    qn = _normalize_apt_query(q)   # 끝의 차/단지/아파트 제거
    if len(qn) < 2:
        qn = qn_raw

    conn = db_module.get_db()
    # 1순위: 정확/부분 매칭
    row = conn.execute(
        "SELECT * FROM apartments WHERE geocoded=1 AND last_price>0 AND area_m2 BETWEEN 1 AND 85 "
        "AND (REPLACE(COALESCE(display_name,''), ' ', '') LIKE ? "
        "     OR REPLACE(name, ' ', '') LIKE ?) "
        "ORDER BY last_price DESC LIMIT 1",
        (f"%{qn}%", f"%{qn}%"),
    ).fetchone()

    # 2순위: 퍼지 매칭 (오타·표기 차이 대응)
    if not row:
        all_rows = conn.execute(
            "SELECT id, COALESCE(display_name, name) AS dn FROM apartments "
            "WHERE geocoded=1 AND last_price>0 AND area_m2 BETWEEN 1 AND 85"
        ).fetchall()
        scored = []
        for r in all_rows:
            cand = (r["dn"] or "").replace(" ", "")
            if len(cand) < 2:
                continue
            score = difflib.SequenceMatcher(None, qn, cand).ratio()
            # 입력이 후보의 부분일 때 가중치
            if qn in cand or cand in qn:
                score = max(score, 0.7)
            if score >= 0.55:
                scored.append((score, r["id"]))
        if scored:
            scored.sort(reverse=True)
            row = conn.execute("SELECT * FROM apartments WHERE id=?", (scored[0][1],)).fetchone()

    conn.close()
    if not row:
        return None
    apt = db_module.row_to_dict(row)
    # 입력이 단지명 절반 미만이면 region 의도 → 매칭 무효화
    dn = (apt.get("display_name") or apt.get("name") or "").replace(" ", "")
    if dn and len(qn) / max(len(dn), 1) < 0.5:
        # 단, 퍼지 매칭 점수가 높았으면 유지
        if not (qn in dn or dn in qn):
            return None
    return apt


def _region_stats(region: str) -> dict:
    """region 시세 통계 — 50㎡대(50~59) + 80㎡대(80~89) 각각 집계.
    소형(40대 이하)·중형(60~79) 평수는 제외해 표준 평형(20평/30평대) 비교 일관성 확보."""
    if not region or not db_module.db_exists():
        return {}
    region_n = region.replace(" ", "").strip()
    conn = db_module.get_db()
    base_sql = ("SELECT COUNT(*), AVG(last_price), AVG(area_m2), "
                "AVG(NULLIF(units,0)), AVG(NULLIF(built_year,0)), AVG(NULLIF(far,0)), "
                "MIN(last_price), MAX(last_price) "
                "FROM apartments WHERE geocoded=1 AND last_price>0 "
                "AND area_m2 BETWEEN ? AND ? AND ")
    where, where_params = ("lawd_cd=?", (GU_BY_NAME[region_n],)) if region_n in GU_BY_NAME \
        else ("dong LIKE ?", (f"%{region}%",))

    def _q(lo, hi):
        return conn.execute(base_sql + where, (lo, hi, *where_params)).fetchone()

    def _fmt(r):
        if not r or r[0] == 0:
            return None
        return {
            "count":      r[0],
            "avg_price":  round((r[1] or 0) / 10000, 1),
            "avg_area":   round(r[2] or 0, 1),
            "avg_units":  int(r[3] or 0),
            "avg_built":  int(r[4] or 0),
            "avg_far":    round(r[5] or 0, 1),
            "min_price":  round((r[6] or 0) / 10000, 1),
            "max_price":  round((r[7] or 0) / 10000, 1),
        }

    s50 = _fmt(_q(50, 59.99))
    s80 = _fmt(_q(80, 89.99))
    conn.close()
    return {"s50": s50, "s80": s80}


async def _count_infra(client: httpx.AsyncClient, lat: float, lng: float, code: str, radius: int = 1000) -> int:
    """카카오 카테고리 검색으로 반경 내 시설 수"""
    if not (lat and lng):
        return 0
    try:
        r = await client.get(
            "https://dapi.kakao.com/v2/local/search/category.json",
            headers=KAKAO_HEADERS,
            params={"category_group_code": code, "x": lng, "y": lat, "radius": radius, "size": 1},
            timeout=8,
        )
        if r.status_code != 200:
            return 0
        return r.json().get("meta", {}).get("total_count", 0)
    except Exception:
        return 0


async def _collect_for(target: str) -> dict:
    """대상별 데이터 수집 — 글·통계·인프라"""
    apt = _find_apartment(target)

    # 라벨은 항상 사용자 입력 (UI 일관성)
    label = target
    # region keyword (호재 검색·통계용)
    region = target if not apt else apt["dong"]
    # 검색 쿼리 — 인사이더 디테일까지 추출하기 위한 6+개 테마
    queries = [
        f"{target} 재개발 재건축 정비사업",
        f"{target} 시공사 선정 사업시행인가 안전진단 조합설립 관리처분",   # 진행 단계
        f"{target} 교통 지하철 신규노선 광역철도 착공 개통 GTX",
        f"{target} 스타필드 신세계 백화점 쇼핑몰 IFC 현대 입점 개발",     # 상업 호재
        f"{target} 실거주 후기 분위기 학군 학원 살기",
        f"{target} 호가 매매 전세 시세 거래 추세",
    ]
    if apt:
        queries.append(apt["name"])
        queries.append(f"{apt['name']} 실거주 후기 재건축 시공사")

    async with httpx.AsyncClient(timeout=10) as client:
        # 네이버 글 수집
        naver_tasks = [_naver_search(client, kind, q, 40) for kind in KINDS for q in queries]
        # 인프라 좌표: 단지 좌표 우선, 없으면 region/구 대표 좌표
        infra_lat, infra_lng = None, None
        if apt and apt.get("lat") and apt.get("lng"):
            infra_lat, infra_lng = apt["lat"], apt["lng"]
        else:
            # region이 구 이름이면 lawd_cd, 아니면 dong LIKE 로 첫 단지 좌표
            target_n = target.replace(" ", "").strip()
            conn = db_module.get_db()
            if target_n in GU_BY_NAME:
                r = conn.execute(
                    "SELECT lat, lng FROM apartments WHERE lawd_cd=? AND geocoded=1 "
                    "ORDER BY last_price DESC LIMIT 1",
                    (GU_BY_NAME[target_n],)
                ).fetchone()
            else:
                r = conn.execute(
                    "SELECT lat, lng FROM apartments WHERE dong LIKE ? AND geocoded=1 LIMIT 1",
                    (f"%{target}%",)
                ).fetchone()
            conn.close()
            if r:
                infra_lat, infra_lng = r["lat"], r["lng"]

        infra_tasks = []
        if infra_lat and infra_lng:
            infra_tasks = [
                _count_infra(client, infra_lat, infra_lng, code)
                for code in INFRA_CODES.values()
            ]

        results = await asyncio.gather(*naver_tasks, *infra_tasks)
        n_naver = len(naver_tasks)
        flat = results[:n_naver]
        infra_counts = results[n_naver:]

    # 글 인터리브 — 종류별 30개씩
    nq = len(queries)
    seen: set = set()
    items: list = []
    for ki, kind in enumerate(KINDS):
        theme_lists = [flat[ki * nq + j] for j in range(nq)]
        items.extend(_interleave(theme_lists, 30, seen))

    infra = dict(zip(INFRA_CODES.keys(), infra_counts)) if infra_counts else {}
    region_stats = _region_stats(target)

    return {
        "label":        label,
        "apt":          apt,
        "items":        items,
        "infra":        infra,
        "region":       region,
        "region_stats": region_stats,
    }


COMPARE_SYSTEM = """당신은 시장 인사이더 수준의 부동산 깊이 분석가입니다.
누구나 검색으로 얻을 수 있는 표면적 정보가 아닌, 카페·블로그·뉴스에서 추출 가능한
구체적 단지명·번지·시점·진행단계·인물·브랜드·금액을 깊이 있게 정리하세요.

입력 데이터 (대상별):
1. 호재 글 (네이버 뉴스·블로그·카페) — 약 90개, 최근 1년
2. 단지 메타 정보 (가격·세대수·연식·용적률·역 도보) — ≤85㎡ 기준
3. 지역 시세 — 50㎡대(20평)·80㎡대(33평) 평균/범위만. 분리 서술 필수.
4. 인프라 카운트 (1km 반경 학교·병원·마트·역·카페·음식점)

분석 원칙 (필수 준수):
■ **디테일 우선** — 단순 "재건축 추진" (X) → "○○구역, 시공사 ○○건설 우선협상자 선정, 2026.06 사업시행인가 신청 예정" (O)
■ **진행단계 명시** — 안전진단·정비계획·조합설립·시공사선정·사업시행인가·관리처분·이주·철거·착공 중 정확히 어느 단계
■ **교통**: 노선명·역명·시점 구체화 ("대장홍대선 2026.12 착공, 2031 개통 예정, ○○역 도보 N분")
■ **상업·인프라**: 구체 브랜드 — 스타필드, 신세계백화점, 현대백화점, IFC, 이마트, 코스트코, 트레이더스 등
■ **시세**: 50대·80대 분리 + 매매호가·전세호가 추세까지 ("80대 매매호가 18~22억 형성, 전세 9~11억")
■ **카페·블로그 소문도 추출** — "○○ 사업자 선정 소문 (출처: ××카페, 2025.12)" 식으로 출처·시점 명시
  단, 미확정 소문은 **rumors 필드**에 분리 (categories엔 확정된 사실만)
■ **일반론·교과서적 설명 금지** — "교통이 편리하다" (X) → "9호선 등촌역 도보 5분 + 5호선 우장산 도보 12분 더블역세권" (O)

출력 형식:
- categories[8~12개]: 재건축 진행단계, 교통 호재, 상업·인프라 호재, 학군·교육, 시세(50대), 시세(80대), 거주 분위기, 미래가치 등
  evaluations[i].summary는 구체 사실 + 시점 + 단계 + 고유명사 포함, 100자 이상 권장
  tier는 "상"/"중"/"하" — 그 항목에서 i번째 대상의 상대적 우위
- pros[i]: 각 대상의 차별화 포인트 (수치·고유명사 포함, 3~6개)
- rumors[i]: 카페·블로그 미확정 소문 (없으면 빈 배열). 각 소문에 topic·detail·source 명시
- recommended_for[i]: 구체적 사용자 프로필·투자 전략
- summary: 시장 맥락에서의 종합 비교 (200자 이상)

모든 배열은 입력 순서(0=A, 1=B, 2=C)대로 채울 것."""


COMPARE_SCHEMA = {
    "type": "object",
    "properties": {
        "headline": {"type": "string"},
        "categories": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "evaluations": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "summary": {"type": "string"},
                                "tier":    {"type": "string", "enum": ["상", "중", "하"]},
                            },
                            "required": ["summary", "tier"],
                            "additionalProperties": False,
                        },
                    },
                },
                "required": ["name", "evaluations"],
                "additionalProperties": False,
            },
        },
        "pros": {
            "type": "array",
            "items": {"type": "array", "items": {"type": "string"}},
        },
        "rumors": {
            "type": "array",
            "items": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "topic":  {"type": "string"},
                        "detail": {"type": "string"},
                        "source": {"type": "string"},
                    },
                    "required": ["topic", "detail", "source"],
                    "additionalProperties": False,
                },
            },
        },
        "recommended_for": {
            "type": "array",
            "items": {"type": "string"},
        },
        "summary": {"type": "string"},
    },
    "required": ["headline", "categories", "pros", "rumors", "recommended_for", "summary"],
    "additionalProperties": False,
}


def _meta(d: dict) -> str:
    a = d.get("apt")
    if not a:
        return f"단지 매칭 없음 — '{d['label']}' 지역 기반 분석"
    return (f"단지명: {a.get('display_name') or a['name']} | 주소: {a['address']}\n"
            f"  실거래가 {a['last_price']/10000:.1f}억 ({a['area_m2']}㎡, {a.get('last_deal_date') or '-'}) | "
            f"세대수 {a.get('units') or '-'} | 연식 {a.get('built_year') or '-'}년 | "
            f"용적률 {a.get('far') or '-'}% | "
            f"가까운역 {a.get('nearest_subway') or '-'} 도보 {a.get('walk_minutes') or '-'}분")


def _stats_text(d: dict) -> str:
    rs = d.get("region_stats") or {}
    s50, s80 = rs.get("s50"), rs.get("s80")
    if not s50 and not s80:
        return "지역 통계 없음 (50/80㎡대 단지 없음)"
    lines = [f"[{d['region']} 지역 시세 — 50㎡대·80㎡대 표준 평형 기준]"]
    if s50:
        lines.append(f"  ▸ 50㎡대 ({s50['count']}개): 평균 {s50['avg_price']}억 "
                     f"(범위 {s50['min_price']}~{s50['max_price']}억) | "
                     f"평균준공 {s50['avg_built']}년 | 평균용적률 {s50['avg_far']}%")
    else:
        lines.append("  ▸ 50㎡대: 거래 없음")
    if s80:
        lines.append(f"  ▸ 80㎡대 ({s80['count']}개): 평균 {s80['avg_price']}억 "
                     f"(범위 {s80['min_price']}~{s80['max_price']}억) | "
                     f"평균준공 {s80['avg_built']}년 | 평균용적률 {s80['avg_far']}%")
    else:
        lines.append("  ▸ 80㎡대: 거래 없음")
    return "\n".join(lines)


def _infra_text(d: dict) -> str:
    inf = d.get("infra") or {}
    if not inf:
        return "인프라 정보 없음"
    return "[반경 1km 인프라] " + " | ".join(f"{k} {v}개" for k, v in inf.items())


def _articles_text(items: list) -> str:
    lines = []
    for i, it in enumerate(items, 1):
        lines.append(f"[{i}] ({it['type']}) {it['title']}\n    {it['description']}")
    return "\n".join(lines)


@router.get("")
async def compare(
    targets: List[str] = Query(..., description="비교 대상 2~3개"),
):
    if not _anthropic:
        return {"error": "ANTHROPIC_API_KEY 없음"}
    if len(targets) < 2:
        return {"error": "비교 대상 2개 이상 필요"}
    if len(targets) > 3:
        targets = targets[:3]

    # 모든 대상 데이터 병렬 수집
    data_list = await asyncio.gather(*[_collect_for(t) for t in targets])

    # 프롬프트 구성
    sections = []
    for idx, d in enumerate(data_list):
        label_letter = chr(ord("A") + idx)
        sections.append(
            f"\n# 대상 {label_letter}: {d['label']}\n"
            f"{_meta(d)}\n"
            f"{_stats_text(d)}\n"
            f"{_infra_text(d)}\n\n"
            f"## {label_letter} 관련 글 ({len(d['items'])}개)\n"
            f"{_articles_text(d['items'])}"
        )
    user_msg = (
        "\n---\n".join(sections)
        + f"\n\n---\n\n위 {len(data_list)}개 대상을 같은 기준으로 비교 분석해 주세요. "
        + "evaluations·pros·recommended_for 배열은 반드시 입력 순서(0,1,2)대로 채우세요."
    )

    try:
        resp = await _anthropic.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=8192,
            system=[{"type": "text", "text": COMPARE_SYSTEM,
                     "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": user_msg}],
            output_config={"format": {"type": "json_schema", "schema": COMPARE_SCHEMA}},
        )
        text_block = next((blk.text for blk in resp.content if blk.type == "text"), "")
        result = json.loads(text_block)
    except Exception as e:
        return {"error": f"분석 실패: {e}"}

    return {
        "targets": [
            {
                "label":        d["label"],
                "apt":          d["apt"],
                "items_count":  len(d["items"]),
                "region_stats": d["region_stats"],
                "infra":        d["infra"],
            }
            for d in data_list
        ],
        "comparison": result,
    }
