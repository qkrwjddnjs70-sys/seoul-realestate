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
- 광고성·홍보성 글, 단순 매물 광고는 호재 분석에서 제외한다.
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


async def _naver_search(client: httpx.AsyncClient, kind: str, query: str, display: int = 40):
    """단일 검색 — 날짜필터 적용한 결과 리스트 반환"""
    try:
        r = await client.get(
            f"https://openapi.naver.com/v1/search/{kind}.json",
            headers=NAVER_HEADERS,
            params={"query": query, "display": display, "sort": "date"},
        )
        if r.status_code != 200:
            return []
        type_label = {"news": "news", "blog": "blog", "cafearticle": "cafe"}[kind]
        out = []
        for item in r.json().get("items", []):
            if not _is_recent(item):
                continue
            out.append({
                "type": type_label,
                "title": strip_html(item.get("title", "")),
                "description": strip_html(item.get("description", "")),
                "link": item.get("originallink") or item.get("link", ""),
                "date": (item.get("pubDate", "") or item.get("postdate", ""))[:16],
            })
        return out
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
            max_tokens=2560,
            system=[{
                "type": "text",
                "text": SUMMARY_SYSTEM,
                "cache_control": {"type": "ephemeral"},
            }],
            messages=[{"role": "user", "content": user_msg}],
            output_config={"format": {"type": "json_schema", "schema": SUMMARY_SCHEMA}},
        )
        text = next((b.text for b in resp.content if b.type == "text"), "")
        return json.loads(text)
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

    # 테마별 쿼리 — 재개발/재건축 한쪽으로 치우치지 않게 교통·신규노선도 별도 검색
    queries = []
    if region:
        queries = [
            f"{region} 재개발 재건축",
            f"{region} 교통 지하철 노선 광역철도 착공",   # 대장홍대선·GTX 등
            f"{region} 개발 호재",
            f"{region} 실거주 후기 분위기 살기",          # 호갱노노 토론방 대안 — 카페 거주 후기
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
