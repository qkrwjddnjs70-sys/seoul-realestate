"""
경사도(slope) 보강 — Open-Meteo elevation API
- 단지 중심 ±80m 5점 표고 → max-min = slope(m)
- 동시 5개 호출, 단지마다 즉시 commit
"""
import os, sys, asyncio, sqlite3
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
import httpx

DB = Path(__file__).parent.parent / "data" / "apartments.db"
URL = "https://api.open-meteo.com/v1/elevation"
DIST = 0.0008
CONCURRENCY = 5


async def fetch_slope(client, lat, lng):
    lats = [lat, lat+DIST, lat-DIST, lat, lat]
    lngs = [lng, lng, lng, lng+DIST, lng-DIST]
    try:
        r = await client.get(URL, params={
            "latitude":  ",".join(f"{x:.6f}" for x in lats),
            "longitude": ",".join(f"{x:.6f}" for x in lngs),
        }, timeout=10)
        if r.status_code != 200:
            return None
        elevs = [e for e in (r.json().get("elevation") or []) if e is not None]
        if len(elevs) < 3:
            return None
        return round(max(elevs) - min(elevs), 1)
    except Exception:
        return None


async def main():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT id, lat, lng FROM apartments "
        "WHERE geocoded=1 AND last_price>0 AND area_m2 BETWEEN 1 AND 85 "
        "AND (slope=0 OR slope IS NULL)"
    ).fetchall()
    total = len(rows)
    print(f"[start] 대상 {total}개", flush=True)

    done = 0
    sem = asyncio.Semaphore(CONCURRENCY)

    async with httpx.AsyncClient() as client:

        async def work(row):
            nonlocal done
            async with sem:
                s = await fetch_slope(client, row["lat"], row["lng"])
                if s is not None:
                    conn.execute("UPDATE apartments SET slope=? WHERE id=?", (s, row["id"]))
                done += 1
                if done % 50 == 0:
                    conn.commit()
                    print(f"[{done}/{total}]", flush=True)

        await asyncio.gather(*[work(r) for r in rows])

    conn.commit()
    conn.close()
    ok = sqlite3.connect(DB).execute("SELECT COUNT(*) FROM apartments WHERE slope>0").fetchone()[0]
    print(f"[done] 채워진 단지: {ok}", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
