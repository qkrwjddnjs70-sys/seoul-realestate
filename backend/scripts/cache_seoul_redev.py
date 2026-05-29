"""서울시 정비사업 추진경과 30k 이벤트를 JSON으로 캐싱 (재매칭 실험용)"""
import os, sys, asyncio, httpx, json
sys.stdout.reconfigure(encoding='utf-8')
from pathlib import Path
from dotenv import dotenv_values

ROOT = Path(__file__).parent.parent
_ENV = dotenv_values(ROOT / ".env")
KEY = _ENV.get("SEOUL_API_KEY_PROGRESS")
OUT = ROOT / "data" / "seoul_redev_cache.json"
URL = "http://openapi.seoul.go.kr:8088"


async def main():
    async with httpx.AsyncClient(timeout=30) as c:
        r0 = await c.get(f"{URL}/{KEY}/json/CleanupBussinessProgress/1/1/")
        total = r0.json()["CleanupBussinessProgress"]["list_total_count"]
        print(f"총 {total}건 캐싱 시작")
        rows = []
        sem = asyncio.Semaphore(5)
        async def page(start):
            end = min(start + 999, total)
            async with sem:
                for _ in range(3):
                    try:
                        r = await c.get(f"{URL}/{KEY}/json/CleanupBussinessProgress/{start}/{end}/")
                        return r.json().get("CleanupBussinessProgress", {}).get("row", [])
                    except Exception:
                        await asyncio.sleep(1)
                return []
        tasks = [page(s) for s in range(1, total + 1, 1000)]
        done = 0
        for fut in asyncio.as_completed(tasks):
            rows.extend(await fut)
            done += 1
            print(f"  {done}/{len(tasks)}", end='\r')
        print()
    OUT.write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")
    print(f"저장: {OUT} ({len(rows)}건)")


if __name__ == "__main__":
    asyncio.run(main())
