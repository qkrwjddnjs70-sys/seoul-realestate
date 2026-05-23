"""한국부동산원 API getAptInfo 실제 호출 테스트"""
import os, sys, asyncio, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")
import httpx

KEY = os.getenv("MOLIT_API_KEY", "")
BASE = "https://api.odcloud.kr/api/AptIdInfoSvc/v1"

async def main():
    async with httpx.AsyncClient(timeout=15) as c:
        # 강남구 아파트 샘플 조회
        r = await c.get(f"{BASE}/getAptInfo", params={
            "serviceKey": KEY,
            "page": 1,
            "perPage": 3,
            "cond[ADRES::LIKE]": "강남구",
        })
        print(f"status: {r.status_code}")
        if r.status_code == 200:
            data = r.json()
            print(f"total: {data.get('totalCount')}")
            if data.get("data"):
                print(f"\n필드 목록: {list(data['data'][0].keys())}")
                print(f"\n샘플 데이터:")
                for item in data["data"]:
                    print(json.dumps(item, ensure_ascii=False, indent=2))
        else:
            print(r.text[:400])

asyncio.run(main())
