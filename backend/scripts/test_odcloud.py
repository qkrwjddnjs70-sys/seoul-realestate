"""한국부동산원 공동주택 단지 식별정보 API 탐색"""
import os, sys, asyncio, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")
import httpx

KEY = os.getenv("MOLIT_API_KEY", "")
BASE = "https://api.odcloud.kr/api/41233/v1"

ENDPOINTS = [
    "/단지기본정보",
    "/단지식별정보",
    "/단지목록",
    "/aptDanjiInfo",
    "/danjiInfo",
    "/basicInfo",
]

async def main():
    async with httpx.AsyncClient(timeout=15) as c:
        for ep in ENDPOINTS:
            url = BASE + ep
            r = await c.get(url, params={
                "serviceKey": KEY,
                "page": 1,
                "perPage": 2,
            })
            preview = r.text[:200].replace("\n", " ")
            print(f"{ep:25s} -> {r.status_code} | {preview}")
            if r.status_code == 200:
                try:
                    data = r.json()
                    print(f"  keys: {list(data.keys())}")
                    if data.get("data"):
                        print(f"  첫번째 항목 키: {list(data['data'][0].keys())[:15]}")
                except Exception:
                    pass
            print()

asyncio.run(main())
