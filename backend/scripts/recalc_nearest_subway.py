"""
각 단지의 가장 가까운 지하철역 + 도보분 재계산.
- frontend/src/data/subwayLines.js의 정확한 역 좌표 사용
- 직선 거리(m) / 80m = 도보분 (대략 1분 80m 보행)
"""
import re, math, sqlite3
from pathlib import Path

BASE = Path(__file__).parent.parent
DB = BASE / "data" / "apartments.db"
JS = BASE.parent / "frontend" / "src" / "data" / "subwayLines.js"

# 노선 파일 파싱 — [lat, lng, '역이름'] 추출 (라인별 노선명도)
txt = JS.read_text(encoding="utf-8")
all_stations = []
for line_m in re.finditer(
    r"id:\s*(\d+),\s*name:\s*'([^']+)',\s*color:\s*'[^']+',\s*stations:\s*\[(.*?)\]\s*,?\s*\}",
    txt, re.DOTALL,
):
    line_id   = int(line_m.group(1))
    line_name = line_m.group(2)
    body      = line_m.group(3)
    for st_m in re.finditer(r"\[\s*([\d.]+)\s*,\s*([\d.]+)\s*,\s*'([^']+)'\s*\]", body):
        all_stations.append((
            st_m.group(3),               # 역이름
            line_name,
            float(st_m.group(1)),         # lat
            float(st_m.group(2)),         # lng
        ))
print(f"역 좌표 {len(all_stations)}개 로드")


def dist_m(lat1, lng1, lat2, lng2):
    """미터 단위 직선 거리 (서울 위도 cosine 보정)"""
    dy = (lat1 - lat2) * 111_000
    dx = (lng1 - lng2) * 111_000 * math.cos(math.radians((lat1 + lat2) / 2))
    return math.sqrt(dx * dx + dy * dy)


conn = sqlite3.connect(DB)
conn.row_factory = sqlite3.Row
rows = conn.execute(
    "SELECT id, lat, lng FROM apartments WHERE geocoded=1 AND lat>0 AND lng>0"
).fetchall()
print(f"대상 단지 {len(rows)}개")

updated = 0
for r in rows:
    best_name, best_line, best_d = None, None, float("inf")
    for name, line, slat, slng in all_stations:
        d = dist_m(r["lat"], r["lng"], slat, slng)
        if d < best_d:
            best_d, best_name, best_line = d, name, line
    if best_name:
        walk = max(1, round(best_d / 80))
        conn.execute(
            "UPDATE apartments SET nearest_subway=?, subway_line=?, walk_minutes=? WHERE id=?",
            (best_name, best_line, walk, r["id"]),
        )
        updated += 1

conn.commit()
conn.close()
print(f"업데이트 {updated}개")
