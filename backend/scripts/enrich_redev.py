"""
재건축 진행 단계 자동 수집
- 후보: 1995년 이전 준공 + (FAR 미상 또는 < 250) 단지
- 옵션 1: 서울시 정비사업 OpenAPI (SEOUL_OPEN_API_KEY 있으면)
- 옵션 2: Naver 뉴스/카페 검색 → Claude Haiku로 단계 분류 (항상)
- DB redev_stage / redev_detail / redev_updated 업데이트
"""
import os, sys, json, asyncio, sqlite3
from datetime import datetime
from pathlib import Path
from dotenv import dotenv_values

ROOT = Path(__file__).parent.parent
_ENV = dotenv_values(ROOT / ".env")
sys.path.insert(0, str(ROOT))

import httpx, anthropic

def _cfg(k): return os.getenv(k) or _ENV.get(k) or ""

NAVER_ID  = _cfg("NAVER_CLIENT_ID")
NAVER_SEC = _cfg("NAVER_CLIENT_SECRET")
ANTH_KEY  = _cfg("ANTHROPIC_API_KEY")
SEOUL_KEY = _cfg("SEOUL_OPEN_API_KEY")

NAVER_HDR = {"X-Naver-Client-Id": NAVER_ID, "X-Naver-Client-Secret": NAVER_SEC}
client = anthropic.AsyncAnthropic(api_key=ANTH_KEY)

DB = ROOT / "data" / "apartments.db"

STAGES = [
    "안전진단",           # 0
    "정비구역지정",       # 1
    "조합설립인가",       # 2
    "시공사선정",         # 3
    "사업시행인가",       # 4
    "관리처분인가",       # 5
    "이주철거",           # 6
    "착공",               # 7
    "준공",               # 8
]

CLASSIFY_SYSTEM = """당신은 한국 재건축 정비사업 단계 분류기입니다.
입력: 특정 아파트 단지명 + 최근 뉴스/카페 글 제목·요약.
출력: 그 단지의 재건축 진행 단계를 아래 중 하나로 정확히 판단하거나 'none'을 반환.

가능한 단계 (반드시 이 문자열 중 하나):
- "안전진단"      (D등급/E등급 통과·진행)
- "정비구역지정"  (정비구역·정비예정구역 지정)
- "조합설립인가"  (추진위 → 조합설립)
- "시공사선정"    (시공사 선정 완료)
- "사업시행인가"  (사업시행계획 인가)
- "관리처분인가"  (관리처분계획 인가)
- "이주철거"      (이주·철거 진행)
- "착공"          (착공·신축 공사 진행)
- "none"          (재건축 관련 명확한 진행 정보 없음 / 다른 단지 얘기 / 단순 추정)

규칙:
- 글이 그 단지(또는 같은 정비구역) 얘기가 확실할 때만 단계 부여.
- 진행 중인 가장 최근·가장 진행된 단계 1개만.
- 추진 예정·논의·소문은 "none". 확정된 인가/통과만 인정.
- detail은 한 문장으로 "조합설립 2023.05" 같이 단계명+근거 시점.
- 다른 설명 없이 JSON만."""

CLASSIFY_SCHEMA = {
    "type": "object",
    "properties": {
        "stage":  {"type": "string", "enum": STAGES + ["none"]},
        "detail": {"type": "string"},
    },
    "required": ["stage", "detail"],
}


async def naver_search(c: httpx.AsyncClient, kind: str, query: str, n: int = 10):
    url = f"https://openapi.naver.com/v1/search/{kind}.json"
    try:
        r = await c.get(url, headers=NAVER_HDR, params={"query": query, "display": n, "sort": "date"})
        if r.status_code != 200:
            return []
        return r.json().get("items", [])
    except Exception:
        return []


def strip_html(s: str) -> str:
    import re
    return re.sub(r"<[^>]+>", "", s or "")


async def classify(name: str, dong: str, items: list) -> dict:
    """Naver 글 → 단계 분류"""
    if not items or not ANTH_KEY:
        return {"stage": "none", "detail": ""}
    bullets = []
    for it in items[:15]:
        title = strip_html(it.get("title", ""))
        desc  = strip_html(it.get("description", ""))
        bullets.append(f"- {title} :: {desc}")
    body = "\n".join(bullets)
    prompt = f"단지명: {name} ({dong})\n\n최근 글:\n{body}\n\n위 단지의 재건축 단계를 판단해줘."
    try:
        msg = await client.messages.create(
            model="claude-haiku-4-5",
            max_tokens=300,
            system=CLASSIFY_SYSTEM,
            tools=[{"name": "set", "description": "단계 결정", "input_schema": CLASSIFY_SCHEMA}],
            tool_choice={"type": "tool", "name": "set"},
            messages=[{"role": "user", "content": prompt}],
        )
        for b in msg.content:
            if b.type == "tool_use":
                return b.input
    except Exception as e:
        print(f"  [AI 오류] {e}")
    return {"stage": "none", "detail": ""}


async def process_apt(c: httpx.AsyncClient, sem: asyncio.Semaphore, apt: dict):
    async with sem:
        name = apt["display_name"] or apt["name"]
        dong = apt["dong"] or ""
        # 단지+재건축 키워드로 뉴스+카페 검색 (재건축 단계 정보가 가장 자주 나옴)
        qs = [f"{name} {dong} 재건축", f"{name} 조합설립"]
        items = []
        for q in qs:
            news = await naver_search(c, "news", q, 8)
            cafe = await naver_search(c, "cafearticle", q, 8)
            items.extend(news + cafe)
        if not items:
            return apt["id"], None, None
        result = await classify(name, dong, items)
        stage = result.get("stage", "none")
        detail = result.get("detail", "")
        if stage == "none" or not stage:
            return apt["id"], None, None
        return apt["id"], stage, detail


async def main():
    if not NAVER_ID or not ANTH_KEY:
        print("[중단] NAVER_CLIENT_ID / ANTHROPIC_API_KEY 필요")
        return
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT id, name, dong, display_name, built_year, far, units "
        "FROM apartments "
        "WHERE geocoded=1 AND last_price>0 AND built_year BETWEEN 1 AND 1995 "
        "AND (far IS NULL OR far < 250) "
        "AND units >= 100 "
        "ORDER BY units DESC"
    ).fetchall()
    conn.close()
    print(f"재건축 후보 {len(rows)}개")

    sem = asyncio.Semaphore(4)  # Naver+AI 동시 4개
    async with httpx.AsyncClient(timeout=20) as c:
        tasks = [process_apt(c, sem, dict(r)) for r in rows]
        done = 0
        results = []
        for fut in asyncio.as_completed(tasks):
            res = await fut
            done += 1
            results.append(res)
            if res[1]:
                print(f"  [{done}/{len(rows)}] id={res[0]} → {res[1]} ({res[2]})")
            elif done % 25 == 0:
                print(f"  ... {done}/{len(rows)}")

    # DB 일괄 업데이트
    conn = sqlite3.connect(DB)
    today = datetime.now().strftime("%Y-%m-%d")
    n_hit = 0
    for aid, stage, detail in results:
        if stage:
            conn.execute(
                "UPDATE apartments SET redev_stage=?, redev_detail=?, redev_updated=? WHERE id=?",
                (stage, detail, today, aid),
            )
            n_hit += 1
    conn.commit()
    conn.close()
    print(f"\n저장: {n_hit}개 단지 단계 확정 / 전체 {len(results)}개 후보")


if __name__ == "__main__":
    asyncio.run(main())
