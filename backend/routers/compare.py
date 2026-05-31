"""
최대 6개 단지·지역 비교 분석 — Claude Sonnet 4.6
- 호재 글 (뉴스/블로그/카페 각 30개)
- DB 시세 통계 (해당 동의 평균/중앙값)
- Kakao 인프라 카운트 (1km 반경 학교/병원/마트/지하철 등)
"""
import os, re, json, asyncio, difflib
from typing import List
import httpx
from dotenv import dotenv_values
from fastapi import APIRouter, Query, Request
from rate_limit import check_and_increment

import database as db_module
from routers.hojae import _naver_search, _interleave, KINDS, _anthropic


def _normalize_apt_query(q: str) -> str:
    """단지명 입력 정규화 — 띄어쓰기·끝의 차/단지/아파트 제거"""
    qn = (q or "").replace(" ", "").strip()
    return re.sub(r"(차|단지|아파트)+$", "", qn)

router = APIRouter()

# 정비사업 정보몽땅 캐시 로드 (gu+동(가 통합) → 사업장 목록)
import math
def _base_dong(d: str) -> str:
    """'양평동2가'→'양평동', '문래동3가'→'문래동' (일대 통합)"""
    if not d: return ""
    m = re.match(r"([가-힣]+동)", d)
    return m.group(1) if m else d
_CLEANUP_BY_DONG = {}
try:
    _cj = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "cleanup_projects.json")
    with open(_cj, encoding="utf-8") as f:
        for p in json.load(f):
            _CLEANUP_BY_DONG.setdefault((p["gu"], _base_dong(p["dong"])), []).append(p)
except Exception:
    pass

_DEAD_STAGES = {"조합해산", "조합청산", "청산 및 조합해산", "이전고시"}

def _haversine(la1, ln1, la2, ln2):
    R = 6371
    dlat = math.radians(la2 - la1); dlng = math.radians(ln2 - ln1)
    a = math.sin(dlat/2)**2 + math.cos(math.radians(la1))*math.cos(math.radians(la2))*math.sin(dlng/2)**2
    return R * 2 * math.asin(math.sqrt(a))

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
    match_type = None
    match_score = None

    # 1순위: 정확/부분 매칭
    row = conn.execute(
        "SELECT * FROM apartments WHERE geocoded=1 AND last_price>0 AND area_m2 BETWEEN 1 AND 90 "
        "AND (REPLACE(COALESCE(display_name,''), ' ', '') LIKE ? "
        "     OR REPLACE(name, ' ', '') LIKE ?) "
        "ORDER BY last_price DESC LIMIT 1",
        (f"%{qn}%", f"%{qn}%"),
    ).fetchone()
    if row:
        match_type = "exact"

    # 2순위: 퍼지 매칭 (오타·표기 차이 대응) — 후보 단지명이 의미있는 길이일 때만
    if not row:
        all_rows = conn.execute(
            "SELECT id, COALESCE(display_name, name) AS dn FROM apartments "
            "WHERE geocoded=1 AND last_price>0 AND area_m2 BETWEEN 1 AND 90"
        ).fetchall()
        scored = []
        for r in all_rows:
            cand = (r["dn"] or "").replace(" ", "")
            if len(cand) < 4:        # 짧은 후보(2~3자)는 substring 우연 매칭 방지
                continue
            score = difflib.SequenceMatcher(None, qn, cand).ratio()
            # substring 가중치는 양쪽 모두 4자 이상이고 후보가 입력의 60%+ 일 때만
            if (qn in cand or cand in qn) and len(cand) >= max(4, len(qn) * 0.6):
                score = max(score, 0.7)
            if score >= 0.6:         # 임계값 0.55 → 0.6 (더 엄격)
                scored.append((score, r["id"]))
        if scored:
            scored.sort(reverse=True)
            best_score, best_id = scored[0]
            row = conn.execute("SELECT * FROM apartments WHERE id=?", (best_id,)).fetchone()
            match_type = "fuzzy"
            match_score = round(best_score, 2)

    conn.close()
    if not row:
        return None
    apt = db_module.row_to_dict(row)
    dn = (apt.get("display_name") or apt.get("name") or "").replace(" ", "")
    if dn and len(qn) / max(len(dn), 1) < 0.5:
        if not (qn in dn or dn in qn):
            return None
    apt["_match_type"]  = match_type
    apt["_match_score"] = match_score
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

    s50 = _fmt(_q(50, 60))
    s80 = _fmt(_q(80, 90))
    conn.close()
    return {"s50": s50, "s80": s80}


# 대형마트로 인정할 브랜드 (이마트 트레이더스/노브랜드는 별도 → 본점 이마트만)
MART_BRANDS = ("이마트", "홈플러스", "롯데마트", "코스트코")


async def _count_infra(client: httpx.AsyncClient, lat: float, lng: float, code: str, radius: int = 1000) -> int:
    """카카오 카테고리 검색으로 반경 내 시설 수
    - MT1(대형마트)는 이마트/홈플러스/롯데마트/코스트코 본점만 카운트
      (SSG·하나로마트·노브랜드·이마트에브리데이 등은 제외)
    """
    if not (lat and lng):
        return 0
    try:
        # 대형마트는 결과 페이지 직접 받아 브랜드 필터
        if code == "MT1":
            r = await client.get(
                "https://dapi.kakao.com/v2/local/search/category.json",
                headers=KAKAO_HEADERS,
                params={"category_group_code": code, "x": lng, "y": lat,
                        "radius": radius, "size": 15, "sort": "distance"},
                timeout=8,
            )
            if r.status_code != 200:
                return 0
            docs = r.json().get("documents", [])
            seen = set()
            n = 0
            for d in docs:
                name = d.get("place_name") or ""
                # 노브랜드·이마트에브리데이·이마트24 등 변종 제외
                if "노브랜드" in name or "에브리데이" in name or "이마트24" in name:
                    continue
                if not any(b in name for b in MART_BRANDS):
                    continue
                # 같은 점포 중복(주차장 등) 방지 — 이름 정규화로 dedup
                key = name.split()[0] if " " in name else name
                if key in seen:
                    continue
                seen.add(key)
                n += 1
            return n

        # 그 외 카테고리는 total_count 그대로
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

    # ─ 지역 개발성: 반경 700m 재건축 밀집 + 동 정비사업 목록 ─
    nearby_redev, dong_projects = _development_context(apt)
    dev_grade, dev_score = _dev_grade(apt, nearby_redev, dong_projects)

    return {
        "label":        label,
        "apt":          apt,
        "items":        items,
        "infra":        infra,
        "region":       region,
        "region_stats": region_stats,
        "nearby_redev": nearby_redev,
        "dong_projects": dong_projects,
        "dev_grade":    dev_grade,
        "dev_score":    dev_score,
        "match_type":   (apt or {}).get("_match_type"),
        "match_score":  (apt or {}).get("_match_score"),
    }


# 단계별 진행도 점수 (높을수록 진행됨)
_STAGE_WEIGHT = {
    "안전진단": 1, "정비구역지정": 1, "추진위원회승인": 2, "조합설립인가": 3,
    "시공사선정": 4, "사업시행인가": 5, "관리처분인가": 6, "이주철거": 6, "착공": 7, "준공": 2,
}

def _dev_grade(apt, nearby, projects):
    """지역 개발성 상/중/하 — 데이터 기반 점수
    ① 본 단지 재건축 진행도 ② 반경700m 재건축 밀집 ③ 동 재건축 사업 수
    """
    if not apt:
        return "-", 0
    score = 0.0
    # ① 본 단지 진행 단계 (정보몽땅/수동 우선, AI추정 절반)
    own = apt.get("redev_stage")
    if own:
        score += _STAGE_WEIGHT.get(own, 0) * 1.5
    elif apt.get("redev_ai_stage"):
        score += _STAGE_WEIGHT.get(apt.get("redev_ai_stage"), 0) * 0.7
    # ② 반경700m 재건축 밀집도 (공식 1.5 / 추정 0.7점, 최대 6점)
    near_pts = sum(1.5 if n.get("official") else 0.7 for n in (nearby or []))
    score += min(near_pts, 6)
    # ③ 동 재건축(아파트→아파트) 사업 수 — 주거가치 직결 (재개발은 0.3 가중)
    redev_cnt = sum(1 for p in (projects or []) if "재건축" in p.get("type", ""))
    redev_cnt2 = sum(0.3 for p in (projects or []) if "재건축" not in p.get("type", ""))
    score += min(redev_cnt * 0.8 + redev_cnt2, 5)

    if score >= 11:
        return "상", round(score, 1)
    if score >= 6:
        return "중", round(score, 1)
    return "하", round(score, 1)


def _development_context(apt: dict | None):
    """단지 주변 개발성 데이터 — 반경 700m 재건축 진행단지 + 동 정비사업"""
    nearby = []
    dong_projects = []
    if not apt:
        return nearby, dong_projects
    # 반경 700m 내 재건축/추정 진행 단지 (DB)
    if apt.get("lat") and apt.get("lng"):
        try:
            conn = db_module.get_db()
            rows = conn.execute(
                "SELECT display_name, name, lat, lng, redev_stage, redev_ai_stage, built_year "
                "FROM apartments WHERE lawd_cd=? AND geocoded=1 "
                "AND (redev_stage IS NOT NULL AND redev_stage!='' "
                "  OR redev_ai_stage IS NOT NULL AND redev_ai_stage!='')",
                (apt.get("lawd_cd"),)
            ).fetchall()
            conn.close()
            for r in rows:
                if not r["lat"] or not r["lng"]:
                    continue
                d = _haversine(apt["lat"], apt["lng"], r["lat"], r["lng"])
                if 0 < d <= 0.7:
                    stage = r["redev_stage"] or r["redev_ai_stage"]
                    official = bool(r["redev_stage"])
                    nearby.append({
                        "name": r["display_name"] or r["name"],
                        "dist_m": int(d * 1000),
                        "stage": stage,
                        "official": official,
                    })
            nearby.sort(key=lambda x: x["dist_m"])
            nearby = nearby[:10]
        except Exception:
            pass
    # 동 정비사업 (정보몽땅) — 주소에서 동 파싱(dong 컬럼 오류 대비), 가 통합
    gu_name = next((g for g, code in GU_BY_NAME.items() if code == apt.get("lawd_cd") and g.endswith("구")), None)
    addr = apt.get("address") or ""
    m = re.search(r"([가-힣]+동)(?!구)(?:\d+가)?", addr)
    base_dong = m.group(1) if m else _base_dong(apt.get("dong") or "")
    if gu_name and base_dong:
        seen_names = set()
        for p in _CLEANUP_BY_DONG.get((gu_name, base_dong), []):
            if p["stage"] in _DEAD_STAGES:
                continue
            if p["name"] in seen_names:    # 중복 사업장 제거
                continue
            seen_names.add(p["name"])
            dong_projects.append({"name": p["name"][:30], "type": p["type"][:10], "stage": p["stage"]})
    return nearby, dong_projects


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
  ※ 입력 데이터의 **★재건축단계** 필드가 최우선 근거다. 공식(정비사업 정보몽땅) 값이 있으면 그것을 단계로 단정 서술하라.
    뉴스로 임의 추측하지 말 것. "정보 없음"으로 표시된 단지는 "공식 확인 안 됨"으로 서술. AI추정만 있으면 "(추정)"을 붙여라.
■ **교통**: 노선명·역명·시점 구체화 ("대장홍대선 2026.12 착공, 2031 개통 예정, ○○역 도보 N분")
■ **상업·인프라**: 구체 브랜드 — 스타필드, 신세계백화점, 현대백화점, IFC, 이마트, 코스트코, 트레이더스 등
■ **시세**: 50대·80대 분리 + 매매호가·전세호가 추세까지 ("80대 매매호가 18~22억 형성, 전세 9~11억")
■ **카페·블로그 소문도 추출** — "○○ 사업자 선정 소문 (출처: ××카페, 2025.12)" 식으로 출처·시점 명시
  단, 미확정 소문은 **rumors 필드**에 분리 (categories엔 확정된 사실만)
■ **일반론·교과서적 설명 금지** — "교통이 편리하다" (X) → "9호선 등촌역 도보 5분 + 5호선 우장산 도보 12분 더블역세권" (O)

출력 형식:
- categories[8~12개]: 재건축 진행단계, **지역 개발성·상승여력**, 교통 인프라, 상업·인프라 호재, 학군·교육, 시세 및 가격경쟁력, 거주 분위기, 미래가치 등
  evaluations[i].summary는 구체 사실 + 시점 + 단계 + 고유명사 포함, 100자 이상 권장
  tier는 "상"/"중"/"하" — 그 항목에서 i번째 대상의 상대적 우위

■ **카테고리별 tier 산정 기준 (반드시 준수)**:
  • **교통 인프라**: 단순 "1km 내 역 N개" 카운트가 아니라 다음 가중치로 평가
    1) 가장 가까운 역까지 도보 시간 (도보 3분 이내 ★★★ / 5분 이내 ★★ / 10분 이내 ★ / 그 외 ✗)
    2) 환승 가능 노선 수 (더블·트리플 역세권 우대)
    3) 버스 노선의 직결 목적지 다양성 — 한 번 환승 없이 갈 수 있는 핵심지(강남·여의도·광화문·홍대·용산) 개수
    4) 신규 노선·GTX 등 미래 교통 호재
    5) **★미래교통호재** 필드(GTX-B·GTX-C·신안산선·동북선 등 예정/착공 노선) — 도보권이면 강력 가산. 특히 GTX는 광역접근성 게임체인저.
    역 개수만 많아도 멀거나 잡 노선뿐이면 "중/하". 도보 3분 이내 + 다중 환승 + GTX/신안산선 도보권 + 강남·홍대 직통 버스면 "상".
    summary에 미래교통호재가 있으면 반드시 명시 (예: "GTX-B 신도림역 도보5분 착공 → 여의도·서울역·청량리 급행 직결").
  • **재건축 가치**: 다음 3가지 종합 평가
    1) 대지지분 (㎡): 높을수록 환급 평수 큼 — 25㎡ 이상 ★★★ / 18~25㎡ ★★ / 12~18㎡ ★ / 12㎡ 미만 ✗
    2) 용적률: 낮을수록 재건축 사업성 큼 — 180% 이하 ★★★ / 200% 이하 ★★ / 250% 이하 ★ / 그 외 ✗
    3) 현재 단계: 안전진단·정비구역지정·조합설립·시공사선정·사업시행인가·관리처분·이주철거·착공·준공
    셋 종합으로 "상/중/하". 대지지분 25㎡ + 용적률 180% + 사업시행인가 이상이면 "상".
    summary에 반드시 대지지분 수치(예: "대지지분 28㎡, 용적률 178%, 조합설립 단계")와 단계 명시.
  • **시세 및 가격경쟁력**: 평당가가 낮을수록 "상" (저평가/매수기회 관점).
    - 평당가 = (실거래가 × 3.3) / 면적㎡. 같은 평형대(50대 또는 80대) 내에서 평당가 비교.
    - 가장 낮은 평당가 = "상" (가격경쟁력 우위 / 추가 상승 여력)
    - 중간 = "중"
    - 가장 높은 평당가 = "하" (이미 프리미엄 반영)
    - summary에 반드시 평당가 수치(예: "평당 6,750만원") 명시.
    - 단, 동일 입지에서 신축이라 비싼 경우는 별도 코멘트.
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
    # 평당가 계산 — (실거래가 만원 × 3.3) / 면적㎡ → 평당 만원
    pyeong = ""
    if a.get("last_price") and a.get("area_m2"):
        try:
            ppy = round(a["last_price"] * 3.3 / a["area_m2"])
            pyeong = f" | 평당 {ppy:,}만원"
        except Exception:
            pass
    # 버스 노선 — 우리 DB에 있는 것 일부 (실제 직결 목적지는 AI가 노선번호 보고 추론)
    buses = a.get("bus_routes") or []
    if isinstance(buses, str):
        try:
            import json as _j
            buses = _j.loads(buses)
        except Exception:
            buses = []
    bus_str = f" | 버스 {', '.join(buses[:6])}" if buses else ""
    # 대지지분 (이론): 공급면적(전용/0.75) / (용적률/100) = area_m2 × 133.3 / far
    land_str = ""
    if a.get("far") and a["far"] > 0 and a.get("area_m2"):
        ls = round(a["area_m2"] * 133.3 / a["far"], 1)
        land_str = f" | 대지지분 {ls}㎡ ({ls*0.3025:.1f}평, {a['area_m2']:.0f}㎡·용적률{a['far']}% 기준)"
    builder_str = f" | 시공사 {a['builder']}" if a.get("builder") else ""
    # 재건축 단계 — DB 권위(정보몽땅/수동) 우선, AI추정은 참고로 별도 명시
    redev_str = ""
    off = a.get("redev_stage")
    ai = a.get("redev_ai_stage")
    if off:
        redev_str = f"\n  ★재건축단계(정비사업 정보몽땅·공식): {off}"
        if a.get("redev_detail"):
            redev_str += f" [{a['redev_detail']}]"
        if ai and ai != off:
            redev_str += f"\n  (참고: AI추정은 '{ai}'로 공식과 다름 — 공식 기준으로 서술하되 최신 변동 가능성 언급)"
    elif ai:
        redev_str = f"\n  ★재건축단계(AI추정·미확인): {ai}"
        if a.get("redev_ai_detail"):
            redev_str += f" [{a['redev_ai_detail']}]"
    else:
        redev_str = "\n  ★재건축단계: 우리 DB에 진행 정보 없음 (뉴스로 추정 금지, '확인 안 됨'으로 서술)"
    return (f"단지명: {a.get('display_name') or a['name']} | 주소: {a['address']}\n"
            f"  실거래가 {a['last_price']/10000:.1f}억 ({a['area_m2']}㎡, {a.get('last_deal_date') or '-'}){pyeong}\n"
            f"  세대수 {a.get('units') or '-'} | 연식 {a.get('built_year') or '-'}년 | "
            f"용적률 {a.get('far') or '-'}%{land_str}{builder_str}\n"
            f"  가까운역 {a.get('nearest_subway') or '-'} {a.get('subway_line') or ''} 도보 {a.get('walk_minutes') or '-'}분{bus_str}"
            f"{redev_str}"
            f"{_future_transit_str(a)}")


def _future_transit_list(a):
    if not a:
        return []
    ft = a.get("future_transit")
    if isinstance(ft, str):
        try:
            ft = json.loads(ft)
        except Exception:
            ft = []
    return ft or []


def _future_transit_str(a: dict) -> str:
    """미래 교통호재 (GTX-B 등 예정/착공 노선)"""
    ft = a.get("future_transit")
    if isinstance(ft, str):
        try:
            ft = json.loads(ft)
        except Exception:
            ft = []
    if not ft:
        return ""
    items = [f"{h['line']} {h['station']}역 도보{h['walk_min']}분({h['status']})" for h in ft]
    return "\n  ★미래교통호재: " + ", ".join(items)


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


def _dev_text(d: dict) -> str:
    """지역 개발성 — 반경 700m 재건축 밀집 + 동 정비사업 (정보몽땅 공식)"""
    nearby = d.get("nearby_redev") or []
    projects = d.get("dong_projects") or []
    lines = ["[지역 개발성 — 정비사업 정보몽땅 공식]"]
    if nearby:
        items = [f"{n['name']}({n['dist_m']}m·{n['stage']}{'·공식' if n['official'] else '·추정'})" for n in nearby[:8]]
        lines.append(f"  ▸ 반경700m 재건축 진행단지 {len(nearby)}개: " + ", ".join(items))
    else:
        lines.append("  ▸ 반경700m 재건축 진행단지: 없음")
    if projects:
        from collections import Counter
        types = Counter(p["type"] for p in projects)
        type_str = ", ".join(f"{t} {ct}건" for t, ct in types.items())
        items = [f"{p['name']}({p['type']}·{p['stage']})" for p in projects[:10]]
        lines.append(f"  ▸ 해당 동 정비사업 {len(projects)}건 [{type_str}]: " + "; ".join(items))
    else:
        lines.append("  ▸ 해당 동 정비사업: 없음")
    return "\n".join(lines)


def _articles_text(items: list) -> str:
    lines = []
    for i, it in enumerate(items, 1):
        lines.append(f"[{i}] ({it['type']}) {it['title']}\n    {it['description']}")
    return "\n".join(lines)


@router.get("")
async def compare(
    request: Request,
    targets: List[str] = Query(..., description="비교 대상 2~6개"),
):
    check_and_increment(request, "compare")
    if not _anthropic:
        return {"error": "ANTHROPIC_API_KEY 없음"}
    if len(targets) < 2:
        return {"error": "비교 대상 2개 이상 필요"}
    if len(targets) > 6:
        targets = targets[:6]

    # 모든 대상 데이터 병렬 수집
    data_list = await asyncio.gather(*[_collect_for(t) for t in targets])

    # 프롬프트 구성 — 대상이 많을수록 단지당 기사 수를 줄여 토큰 폭발 방지
    n = len(data_list)
    per_arts = 30 if n <= 3 else (18 if n == 4 else (14 if n == 5 else 10))
    sections = []
    for idx, d in enumerate(data_list):
        label_letter = chr(ord("A") + idx)
        arts = d["items"][:per_arts]
        sections.append(
            f"\n# 대상 {label_letter}: {d['label']}\n"
            f"{_meta(d)}\n"
            f"{_stats_text(d)}\n"
            f"{_infra_text(d)}\n"
            f"{_dev_text(d)}\n\n"
            f"## {label_letter} 관련 글 ({len(arts)}개)\n"
            f"{_articles_text(arts)}"
        )
    user_msg = (
        "\n---\n".join(sections)
        + f"\n\n---\n\n위 {len(data_list)}개 대상을 같은 기준으로 비교 분석해 주세요. "
        + "evaluations·pros·recommended_for 배열은 반드시 입력 순서(0,1,2)대로 채우세요."
    )

    try:
        resp = await _anthropic.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=16000,           # 6개 비교까지 대응 (대상 많을수록 응답 길어짐)
            system=[{"type": "text", "text": COMPARE_SYSTEM,
                     "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": user_msg}],
            output_config={"format": {"type": "json_schema", "schema": COMPARE_SCHEMA}},
        )
        text_block = next((blk.text for blk in resp.content if blk.type == "text"), "")
        try:
            result = json.loads(text_block)
        except json.JSONDecodeError as je:
            # 출력 잘림 → 끝에서부터 균형 잡힌 } 찾기
            print(f"[compare] JSON 파싱 1차 실패 ({je}). 부분 복구 시도...")
            result = None
            for end in range(len(text_block), 0, -50):
                try:
                    result = json.loads(text_block[:end])
                    break
                except Exception:
                    continue
            if not result:
                return {"error": f"AI 응답이 너무 길어 잘렸습니다. 다시 시도하거나 비교 대상을 2개로 줄여주세요. ({je})"}
    except Exception as e:
        return {"error": f"분석 실패: {e}"}

    return {
        "targets": [
            {
                "label":         d["label"],
                "apt":           d["apt"],
                "items_count":   len(d["items"]),
                "region_stats":  d["region_stats"],
                "infra":         d["infra"],
                "nearby_redev":  d.get("nearby_redev", []),
                "dong_projects": d.get("dong_projects", []),
                "dev_grade":     d.get("dev_grade", "-"),
                "future_transit": _future_transit_list(d.get("apt")),
                "match_type":    d["match_type"],
                "match_score":   d["match_score"],
            }
            for d in data_list
        ],
        "comparison": result,
    }
