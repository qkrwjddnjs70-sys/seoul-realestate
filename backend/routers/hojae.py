"""
네이버 뉴스/블로그/카페 API로 지역 호재 검색 + Claude Haiku 요약
"""
import os, re, json, asyncio
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
import httpx
import anthropic
from dotenv import dotenv_values
from fastapi import APIRouter, Query

router = APIRouter()

# .env 파일에서 직접 읽기 (시스템 환경변수가 빈 값으로 덮어쓰는 경우 대비)
_ENV = dotenv_values(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))


def _cfg(key: str) -> str:
    return os.getenv(key) or _ENV.get(key) or ""


NAVER_CLIENT_ID     = _cfg("NAVER_CLIENT_ID")
NAVER_CLIENT_SECRET = _cfg("NAVER_CLIENT_SECRET")
NAVER_HEADERS = {
    "X-Naver-Client-Id":     NAVER_CLIENT_ID,
    "X-Naver-Client-Secret": NAVER_CLIENT_SECRET,
}

# Anthropic 클라이언트
_ANTHROPIC_KEY = _cfg("ANTHROPIC_API_KEY")
_anthropic = anthropic.AsyncAnthropic(api_key=_ANTHROPIC_KEY) if _ANTHROPIC_KEY else None

# 요약 시스템 프롬프트 — 호재 검색마다 동일하므로 캐시 대상
SUMMARY_SYSTEM = """당신은 한국 부동산 호재 분석 전문가입니다.
사용자가 특정 동네에 대해 수집한 뉴스·블로그·카페 글 목록을 받으면,
그 지역의 실제 부동산 호재를 분석해 투자자가 한눈에 파악할 수 있게 정리합니다.

원칙:
- 광고성·홍보성 글, 단순 매물 광고는 호재 분석에서 **반드시** 제외한다.
  (입력 단계에서 1차 필터링이 되어 있으나, 잔여 광고가 보이면 분석에서 빼라)
- 우리가 원하는 정보 종류:
  1) 임장 후기·방문 후기·둘러본 글 (단지·동네 분위기, 장단점, 사진 위주)
  2) 아파트 설명 (세대수·연식·구조·평형·관리비·커뮤니티 등 객관 정보)
  3) 호재 설명 (재건축·재개발 진행단계, 교통·상업·학군·인프라 호재)
  4) 시세·전망 분석 (실거래 추이, 매물 분포, 호가 흐름)
  5) 실거주자 평판 (소음·치안·층간소음·학군·생활편의)
- 위 5개 카테고리에 속하지 않는 글(부동산 사무소 광고, 단순 매물 리스팅, 대출 광고 등)은 무시한다.
- 재건축·재개발·교통 호재를 빠짐없이 본다. 교통 호재에는
  GTX, 신규 지하철 노선(예: 대장홍대선), 광역철도, 역 신설·착공이 모두 포함된다.
- 글 제목·내용에 노선 착공/개통 같은 교통 호재가 있으면 반드시 별도 항목으로 정리한다.
- 카페·블로그의 실거주 후기·분위기·평판 정보가 있으면 "🏘️ 거주 분위기/평판"이라는 카테고리로
  별도로 정리한다 (장단점·소음·치안·학군 분위기·생활 편의 등).
  단, 단순 광고나 매물 홍보는 제외한다.
- 입력 데이터는 최근 1년 이내의 글이다. 현재 진행 상황을 기준으로 분석한다.
- 확정된 사실과 추진 중·소문 단계를 명확히 구분해서 서술한다.
  (예: "착공했다"와 "추진 예정이다"를 섞지 않는다)
- 과장하지 않고, 근거가 약하면 약하다고 말한다.
- 모든 출력은 한국어로 작성한다."""

# 구조화 출력 스키마
SUMMARY_SCHEMA = {
    "type": "object",
    "properties": {
        "headline": {"type": "string"},
        "key_points": {"type": "array", "items": {"type": "string"}},
        "categories": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "label":  {"type": "string"},
                    "detail": {"type": "string"},
                },
                "required": ["label", "detail"],
                "additionalProperties": False,
            },
        },
        "outlook": {"type": "string"},
    },
    "required": ["headline", "key_points", "categories", "outlook"],
    "additionalProperties": False,
}


def strip_html(text: str) -> str:
    return re.sub(r"<[^>]+>", "", text or "").replace("&quot;", '"').replace("&amp;", "&").strip()


# 최근 1년 이내 데이터만 사용 (과거 호재가 현재 호재처럼 보이는 혼동 방지)
RECENT_DAYS = 365


def _is_recent(item: dict) -> bool:
    """뉴스 pubDate / 블로그 postdate 를 파싱해 1년 이내인지 판단"""
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=RECENT_DAYS)
    # 뉴스: RFC822 형식 pubDate
    pub = item.get("pubDate", "")
    if pub:
        try:
            dt = parsedate_to_datetime(pub)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt >= cutoff
        except Exception:
            return True
    # 블로그: YYYYMMDD 형식 postdate
    post = item.get("postdate", "")
    if post:
        try:
            dt = datetime.strptime(post[:8], "%Y%m%d").replace(tzinfo=timezone.utc)
            return dt >= cutoff
        except Exception:
            return True
    # 날짜 정보 없음(카페) → sort=date 최신순이므로 통과
    return True


# ─── 홍보·광고 필터 ───────────────────────────────────────────────
# 강제 제외 — 이 단어 하나라도 들어가면 광고/홍보로 판단
_AD_BLOCKERS = [
    # 부동산 사무소·중개사 직접 광고
    "공인중개사", "부동산공인", "부동산사무소", "직거래", "급매물",
    "급전세", "급월세", "급매로", "초급매", "초급전세",
    # 매물 광고 패턴
    "매매환영", "전세환영", "월세환영", "문의환영", "문의주세요",
    "연락주세요", "전화주세요", "방문환영", "상담환영", "친절상담",
    # 분양·청약·마케팅
    "선착순분양", "분양상담", "분양문의", "모델하우스", "사전예약",
    "주말이벤트", "오픈이벤트", "특별분양", "한정세대",
    # 대출
    "대출상담", "대출문의", "신용대출", "주담대상담",
    # 광고성 부동산 키워드
    "급처분", "급처", "초특가", "최저가매물",
]

# 가산점 — 양질 콘텐츠 신호 (있을수록 우선)
_QUALITY_SIGNALS = [
    "임장", "임장기", "임장후기", "방문후기", "둘러보", "가봤",
    "직접가본", "직접본", "다녀온", "탐방",
    "거주후기", "실거주", "살아본", "살고있", "거주중",
    "분위기", "동네", "주변환경", "생활편의", "교육환경",
    "재건축", "재개발", "정비사업", "조합", "안전진단",
    "호재", "개발계획", "개발호재", "개발예정", "착공",
    "교통호재", "노선", "GTX", "개통", "역세권",
    "비교분석", "분석", "시세분석", "전망", "리포트",
    "장단점", "솔직후기", "솔직한", "리뷰", "후기",
    "학군", "초등학교", "중학교", "고등학교", "학원가",
]

# 전화번호 패턴 (010-, 02-, 031- 등)
_PHONE_RE = re.compile(r"01[0-9][\-\s]?\d{3,4}[\-\s]?\d{4}|0[2-6][0-9]?[\-\s]?\d{3,4}[\-\s]?\d{4}")
# "○○억 ○○호" 같은 매물 표기
_LISTING_RE = re.compile(r"\d+\s*억\s*\d*\s*(매매|전세|월세|호|동)")


def _ad_score(item: dict) -> int:
    """광고 점수 — 클수록 광고. 음수면 양질 콘텐츠"""
    text = f"{item.get('title','')} {item.get('description','')}".replace(" ", "")
    score = 0
    # 강제 차단 키워드
    for kw in _AD_BLOCKERS:
        if kw in text:
            score += 100  # 1개라도 있으면 컷
    # 전화번호 = 광고 강한 신호
    raw = f"{item.get('title','')} {item.get('description','')}"
    if _PHONE_RE.search(raw):
        score += 50
    # "OO억 매매/전세/호" 매물 표기 다수
    listings = len(_LISTING_RE.findall(raw))
    score += listings * 15
    # 양질 신호
    for sig in _QUALITY_SIGNALS:
        if sig in text:
            score -= 10
    return score


def _filter_useful(items: list[dict], kind: str) -> list[dict]:
    """광고 컷 + 양질 우선 정렬"""
    scored = [(_ad_score(it), it) for it in items]
    # 카페·블로그는 광고 판정 엄격(점수≥30 컷), 뉴스는 느슨(≥80)
    cutoff = 80 if kind == "news" else 30
    kept = [(s, it) for s, it in scored if s < cutoff]
    kept.sort(key=lambda x: x[0])   # 점수 낮은(=양질) 순
    return [it for _, it in kept]


async def _naver_search(client: httpx.AsyncClient, kind: str, query: str, display: int = 40):
    """단일 검색 — 날짜필터 + 광고·홍보 필터 + 양질 우선 정렬"""
    try:
        # 광고 컷으로 절반 가까이 잘릴 수 있으니 더 많이 받음
        fetch_n = min(100, display * 2)
        r = await client.get(
            f"https://openapi.naver.com/v1/search/{kind}.json",
            headers=NAVER_HEADERS,
            params={"query": query, "display": fetch_n, "sort": "date"},
        )
        if r.status_code != 200:
            return []
        type_label = {"news": "news", "blog": "blog", "cafearticle": "cafe"}[kind]
        raw = []
        for item in r.json().get("items", []):
            if not _is_recent(item):
                continue
            raw.append({
                "type": type_label,
                "title": strip_html(item.get("title", "")),
                "description": strip_html(item.get("description", "")),
                "link": item.get("originallink") or item.get("link", ""),
                "date": (item.get("pubDate", "") or item.get("postdate", ""))[:16],
            })
        return _filter_useful(raw, kind)
    except Exception:
        return []


def _interleave(lists: list[list], limit: int, seen: set) -> list:
    """여러 검색결과를 번갈아 뽑아 한쪽 테마가 독식하지 않게 한다"""
    out, idx = [], 0
    while len(out) < limit and any(idx < len(l) for l in lists):
        for l in lists:
            if idx < len(l):
                it = l[idx]
                if it["link"] and it["link"] not in seen:
                    seen.add(it["link"])
                    out.append(it)
                    if len(out) >= limit:
                        break
        idx += 1
    return out


async def _summarize(loc: str, items: list[dict]) -> dict | None:
    """수집한 글들을 Claude Haiku로 요약"""
    if not _anthropic or not items:
        return None

    # 글 목록을 번호 매겨 텍스트로 구성
    lines = []
    for i, it in enumerate(items, 1):
        lines.append(f"[{i}] ({it['type']}) {it['title']}\n    {it['description']}")
    articles_text = "\n".join(lines)

    user_msg = (
        f"다음은 '{loc}' 지역 부동산 관련 글 {len(items)}개입니다. "
        f"이 지역의 호재를 분석해 정리해 주세요.\n\n{articles_text}"
    )

    try:
        resp = await _anthropic.messages.create(
            model="claude-haiku-4-5",
            max_tokens=6000,           # 2560 → 6000 (강화된 프롬프트로 응답 길이 증가)
            system=[{
                "type": "text",
                "text": SUMMARY_SYSTEM,
                "cache_control": {"type": "ephemeral"},
            }],
            messages=[{"role": "user", "content": user_msg}],
            output_config={"format": {"type": "json_schema", "schema": SUMMARY_SCHEMA}},
        )
        text = next((b.text for b in resp.content if b.type == "text"), "")
        try:
            return json.loads(text)
        except json.JSONDecodeError as je:
            # 출력이 잘렸을 가능성 — 마지막 완전한 카테고리까지만 살려서 복구 시도
            print(f"[hojae] JSON 파싱 1차 실패 ({je}). 부분 복구 시도...")
            # 마지막 } 까지만 자르고 닫기
            last_brace = text.rfind('}')
            if last_brace > 0:
                # 끝까지 균형 잡힌 } 찾기
                for end in range(len(text), last_brace, -1):
                    candidate = text[:end]
                    try:
                        return json.loads(candidate)
                    except Exception:
                        continue
            # 그래도 실패 시 headline만 추출해서 최소 응답
            import re as _re
            m = _re.search(r'"headline"\s*:\s*"([^"]+)"', text)
            if m:
                return {"headline": m.group(1), "key_points": [], "categories": [], "outlook": "(요약 일부만 복구됨)"}
            return None
    except Exception as e:
        print(f"[hojae] 요약 실패: {e}")
        return None


KINDS = ("news", "blog", "cafearticle")


@router.get("")
async def search_hojae(
    dong: str = Query(""),
    gu:   str = Query(""),
    name: str = Query(""),
):
    loc = dong or gu or name
    region = dong or gu

    # 서울 동(洞)인데 경기도 동명 시·군과 헷갈리는 케이스 — 검색·필터 동시 보정
    # 양평동(영등포) vs 양평군(경기), 신촌동(서대문) vs 신촌(전국), 한강(중구) 등
    AMBIGUOUS = {
        "양평": "영등포",   # 영등포 양평동 vs 경기 양평
    }
    # region에서 핵심 토큰 추출 (양평동·양평동2가 → "양평")
    region_token = ""
    for amb in AMBIGUOUS:
        if amb in (region or ""):
            region_token = amb
            break
    seoul_prefix = AMBIGUOUS.get(region_token, "")   # 예: "영등포"

    def Q(base: str) -> str:
        """검색 쿼리에 서울 prefix 부착해 경기도 동명 결과 줄임"""
        return f"{seoul_prefix} {base}" if seoul_prefix else base

    # 테마별 쿼리 — 재개발/재건축 한쪽으로 치우치지 않게 교통·신규노선도 별도 검색
    queries = []
    if region:
        queries = [
            Q(f"{region} 재개발 재건축"),
            Q(f"{region} 교통 지하철 노선 광역철도 착공"),   # 대장홍대선·GTX 등
            Q(f"{region} 개발 호재"),
            Q(f"{region} 실거주 후기 분위기 살기"),          # 호갱노노 토론방 대안 — 카페 거주 후기
        ]
    if name:
        queries.append(f"{name}")               # 단지 자체 언급 글
        queries.append(f"{name} 실거주 후기")   # 단지 거주 후기
    if not queries:
        queries = [f"{loc} 부동산 호재"]

    # 모든 (kind × query) 조합을 병렬 검색
    async with httpx.AsyncClient(timeout=9.0) as client:
        tasks = [
            _naver_search(client, kind, q, 40)
            for kind in KINDS
            for q in queries
        ]
        flat = await asyncio.gather(*tasks)

    # 동명이지 시·군 negative filter — region이 양평일 때 경기도 양평 글 제거
    GYEONGGI_YANGPYEONG = [
        "양평군", "양평읍", "양수리", "두물머리", "용문면", "용문역",
        "양서면", "옥천면", "강상면", "강하면", "단월면", "지평면",
        "청운면", "양동면", "서종면", "양평전통시장", "양평5일장",
        "양평산", "남한강", "북한강", "경기 양평", "경기도 양평",
    ]
    def _is_gyeonggi_yangpyeong(it: dict) -> bool:
        text = f"{it.get('title','')} {it.get('description','')}"
        return any(kw in text for kw in GYEONGGI_YANGPYEONG)

    if region_token == "양평":
        flat = [[it for it in lst if not _is_gyeonggi_yangpyeong(it)] for lst in flat]

    # kind별로 테마 결과를 번갈아 뽑아 30개씩 (중복 link 제거)
    nq = len(queries)
    seen: set = set()
    items: list = []
    for ki, kind in enumerate(KINDS):
        theme_lists = [flat[ki * nq + j] for j in range(nq)]
        items.extend(_interleave(theme_lists, 30, seen))

    # Haiku 요약
    summary = await _summarize(loc, items)

    return {"query": " / ".join(queries), "summary": summary, "items": items}
