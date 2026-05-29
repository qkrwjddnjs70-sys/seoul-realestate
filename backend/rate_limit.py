"""
IP 기반 AI 기능 일일 사용 한도
- KST 자정 리셋
- SQLite ai_usage 테이블에 (ip, date, hojae, compare, filter) 카운트
- exceeded 시 HTTPException(429)
"""
import os, sqlite3
from datetime import datetime, timezone, timedelta
from fastapi import HTTPException, Request
from pathlib import Path

DB = Path(__file__).parent / "data" / "rate_limit.db"

LIMITS = {
    "hojae":   10,    # 호재 검색
    "compare": 3,     # 비교 분석
    "filter":  10,    # 종합 AI 분석
}

# 기본 OFF. 켜려면 Render env: RATE_LIMIT_ENABLED=true
_ENABLED = (os.getenv("RATE_LIMIT_ENABLED", "false").lower() == "true")

KST = timezone(timedelta(hours=9))


def _today_kst() -> str:
    return datetime.now(KST).strftime("%Y-%m-%d")


def _init():
    DB.parent.mkdir(exist_ok=True)
    c = sqlite3.connect(DB)
    c.execute("""
        CREATE TABLE IF NOT EXISTS ai_usage (
            ip      TEXT NOT NULL,
            date    TEXT NOT NULL,
            feature TEXT NOT NULL,
            count   INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (ip, date, feature)
        )
    """)
    c.commit()
    c.close()


_init()


def _client_ip(req: Request) -> str:
    """X-Forwarded-For 우선 (Render·Vercel 프록시 환경)"""
    xff = req.headers.get("x-forwarded-for") or ""
    if xff:
        return xff.split(",")[0].strip()
    return req.client.host if req.client else "unknown"


def get_remaining(req: Request) -> dict:
    """현재 남은 횟수 반환. 비활성 시 빈 dict"""
    if not _ENABLED:
        return {}
    ip = _client_ip(req)
    today = _today_kst()
    out = {}
    c = sqlite3.connect(DB)
    for feat, limit in LIMITS.items():
        row = c.execute(
            "SELECT count FROM ai_usage WHERE ip=? AND date=? AND feature=?",
            (ip, today, feat),
        ).fetchone()
        used = row[0] if row else 0
        out[feat] = {"used": used, "limit": limit, "remaining": max(0, limit - used)}
    c.close()
    return out


def check_and_increment(req: Request, feature: str):
    """한도 체크 + 통과 시 증가. 초과 시 429 raise. 비활성 시 no-op"""
    if not _ENABLED:
        return
    if feature not in LIMITS:
        return
    # 관리자 우회 — ADMIN_BYPASS_TOKEN 헤더와 일치하면 카운트 안 함
    bypass = os.getenv("ADMIN_BYPASS_TOKEN")
    if bypass and req.headers.get("x-admin-token") == bypass:
        return

    ip = _client_ip(req)
    today = _today_kst()
    limit = LIMITS[feature]

    c = sqlite3.connect(DB)
    try:
        row = c.execute(
            "SELECT count FROM ai_usage WHERE ip=? AND date=? AND feature=?",
            (ip, today, feature),
        ).fetchone()
        used = row[0] if row else 0
        if used >= limit:
            # KST 다음날 0시까지 남은 시간
            now = datetime.now(KST)
            tomorrow = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
            hours_left = round((tomorrow - now).total_seconds() / 3600, 1)
            raise HTTPException(
                status_code=429,
                detail={
                    "code": "RATE_LIMIT",
                    "feature": feature,
                    "limit": limit,
                    "used": used,
                    "reset_in_hours": hours_left,
                    "message": f"오늘 {feature} 사용 한도({limit}회) 초과. {hours_left}시간 후 한국시간 자정에 리셋됩니다.",
                },
            )
        c.execute(
            "INSERT INTO ai_usage(ip,date,feature,count) VALUES(?,?,?,1) "
            "ON CONFLICT(ip,date,feature) DO UPDATE SET count=count+1",
            (ip, today, feature),
        )
        c.commit()
    finally:
        c.close()
