"""Swagger 문서에서 실제 엔드포인트 확인"""
import asyncio, json
import httpx

SWAGGER_URL = "https://infuser.odcloud.kr/api/stages/41233/api-docs?1664169292067"

async def main():
    async with httpx.AsyncClient(timeout=15) as c:
        r = await c.get(SWAGGER_URL)
        print(f"status: {r.status_code}")
        if r.status_code == 200:
            try:
                data = r.json()
                paths = data.get("paths", {})
                print(f"\n사용 가능한 엔드포인트 ({len(paths)}개):")
                for path in paths:
                    print(f"  {path}")
                    methods = paths[path]
                    for method, info in methods.items():
                        params = [p.get("name") for p in info.get("parameters", [])]
                        print(f"    [{method.upper()}] params: {params}")
            except Exception as e:
                print(f"JSON 파싱 실패: {e}")
                print(r.text[:500])

asyncio.run(main())
