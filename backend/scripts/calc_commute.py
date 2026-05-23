"""
아파트 → 주요 거점 대중교통 소요시간 계산
직선거리 기반 추정: 서울 평균 대중교통 속도 ~27km/h + 기본 대기/환승 8분
"""
import os, sys, math, sqlite3
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "apartments.db")

# 주요 거점 좌표 (지하철역 기준)
HUBS = {
    "gangnam":     (37.4980, 127.0282),  # 강남역 (2호선/신분당선)
    "yeouido":     (37.5217, 126.9242),  # 여의도역 (5호선/9호선)
    "gwanghwamun": (37.5714, 126.9770),  # 광화문역 (5호선)
    "siccheong":   (37.5659, 126.9772),  # 시청역 (1/2호선)
    "hongdae":     (37.5572, 126.9239),  # 홍대입구역 (2호선)
}

def haversine_km(lat1, lng1, lat2, lng2) -> float:
    R = 6371
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lng2 - lng1)
    a = math.sin(dp/2)**2 + math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))

def estimate_time(lat, lng, hub_lat, hub_lng) -> int:
    """직선거리 → 대중교통 소요시간(분) 추정"""
    dist = haversine_km(lat, lng, hub_lat, hub_lng)
    # 서울 대중교통 평균 27km/h + 기본 8분 (대기/환승)
    minutes = int(dist / 0.45 + 8)
    return max(5, minutes)

def main():
    conn = sqlite3.connect(DB_PATH)

    # 컬럼 추가 (없는 경우만)
    existing = {row[1] for row in conn.execute("PRAGMA table_info(apartments)")}
    for col in ("time_gangnam", "time_yeouido", "time_gwanghwamun", "time_siccheong", "time_hongdae"):
        if col not in existing:
            conn.execute(f"ALTER TABLE apartments ADD COLUMN {col} INTEGER DEFAULT 0")
    conn.commit()
    print("컬럼 준비 완료")

    rows = conn.execute("SELECT id, lat, lng FROM apartments WHERE geocoded=1 AND lat != 0").fetchall()
    print(f"계산 대상: {len(rows):,}개")

    for apt_id, lat, lng in rows:
        times = {
            hub: estimate_time(lat, lng, hlat, hlng)
            for hub, (hlat, hlng) in HUBS.items()
        }
        conn.execute("""
            UPDATE apartments SET
                time_gangnam=?, time_yeouido=?, time_gwanghwamun=?,
                time_siccheong=?, time_hongdae=?
            WHERE id=?
        """, (
            times["gangnam"], times["yeouido"], times["gwanghwamun"],
            times["siccheong"], times["hongdae"], apt_id,
        ))

    conn.commit()
    conn.close()

    # 샘플 출력
    conn2 = sqlite3.connect(DB_PATH)
    samples = conn2.execute("""
        SELECT name, time_gangnam, time_yeouido, time_gwanghwamun, time_siccheong, time_hongdae
        FROM apartments WHERE geocoded=1 ORDER BY time_gangnam LIMIT 5
    """).fetchall()
    print("\n강남 근접 TOP 5:")
    print(f"{'단지명':<20} {'강남':>5} {'여의도':>6} {'광화문':>6} {'시청':>5} {'홍대':>5}")
    for r in samples:
        print(f"{r[0]:<20} {r[1]:>4}분 {r[2]:>5}분 {r[3]:>5}분 {r[4]:>4}분 {r[5]:>4}분")
    conn2.close()
    print("\n[완료]")

if __name__ == "__main__":
    main()
