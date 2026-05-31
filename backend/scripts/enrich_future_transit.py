"""
미래 교통호재(신규/예정 노선) 역 좌표 → 근접 단지 자동 태깅
- GTX-B, GTX-A, GTX-C, 신안산선, 위례신사선, 동북선 등 주요 미래노선 핵심 역
- 각 단지에서 도보(거리/80m) 15분 이내면 future_transit에 기록
- future_transit: JSON [{line, station, walk_min, status}]
"""
import sys, json, sqlite3, math
sys.stdout.reconfigure(encoding='utf-8')
from pathlib import Path

DB = Path(__file__).parent.parent / "data" / "apartments.db"

# 미래/예정 노선 핵심 역 (서울 구간 위주). status: 착공/예정/추진
FUTURE = [
    # GTX-B (2025.8 착공, 2030 개통 목표) — 서울 정차역
    ("GTX-B", "신도림", 37.5089, 126.8913, "착공"),
    ("GTX-B", "여의도", 37.5215, 126.9243, "착공"),
    ("GTX-B", "용산",   37.5299, 126.9645, "착공"),
    ("GTX-B", "서울역", 37.5547, 126.9707, "착공"),
    ("GTX-B", "청량리", 37.5803, 127.0469, "착공"),
    # GTX-A (운정~동탄, 일부 개통) — 서울
    ("GTX-A", "서울역", 37.5547, 126.9707, "개통/공사"),
    ("GTX-A", "삼성",   37.5089, 127.0631, "공사"),
    ("GTX-A", "수서",   37.4870, 127.1015, "개통"),
    ("GTX-A", "연신내", 37.6191, 126.9215, "공사"),
    # GTX-C (2028 목표) — 서울
    ("GTX-C", "청량리", 37.5803, 127.0469, "착공"),
    ("GTX-C", "왕십리", 37.5612, 127.0376, "예정"),
    ("GTX-C", "삼성",   37.5089, 127.0631, "예정"),
    ("GTX-C", "양재",   37.4844, 127.0345, "착공"),
    ("GTX-C", "광운대", 37.6235, 127.0617, "예정"),
    ("GTX-C", "창동",   37.6532, 127.0474, "착공"),
    # 신안산선 (2025~26 개통 예정) — 서울 구간
    ("신안산선", "여의도",   37.5215, 126.9243, "공사"),
    ("신안산선", "영등포",   37.5157, 126.9076, "공사"),
    ("신안산선", "신풍",     37.5003, 126.9098, "공사"),
    ("신안산선", "구로디지털", 37.4853, 126.9015, "공사"),
    ("신안산선", "독산",     37.4660, 126.8895, "공사"),
    # 위례신사선 (추진)
    ("위례신사선", "신사", 37.5163, 127.0204, "추진"),
    # 동북선 (2026 목표)
    ("동북선", "왕십리",   37.5612, 127.0376, "공사"),
    ("동북선", "제기동",   37.5780, 127.0348, "공사"),
    ("동북선", "고려대",   37.5905, 127.0364, "공사"),
    ("동북선", "미아사거리", 37.6133, 127.0301, "공사"),
    ("동북선", "상계",     37.6557, 127.0660, "공사"),
    # 면목선·서부선 등은 추진 초기라 제외
]

def hav(la1, ln1, la2, ln2):
    R=6371; dlat=math.radians(la2-la1); dlng=math.radians(ln2-ln1)
    a=math.sin(dlat/2)**2+math.cos(math.radians(la1))*math.cos(math.radians(la2))*math.sin(dlng/2)**2
    return R*2*math.asin(math.sqrt(a))

def main():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT id, lat, lng FROM apartments WHERE geocoded=1 AND lat>0").fetchall()
    n_tagged = 0
    for r in rows:
        hits = []
        for line, stn, la, ln, status in FUTURE:
            d_km = hav(r["lat"], r["lng"], la, ln)
            walk = int(d_km * 1000 / 80)   # 80m/분
            if walk <= 15:
                hits.append({"line": line, "station": stn, "walk_min": walk, "status": status})
        # 같은 노선이면 가장 가까운 역만
        best = {}
        for h in hits:
            if h["line"] not in best or h["walk_min"] < best[h["line"]]["walk_min"]:
                best[h["line"]] = h
        hits = sorted(best.values(), key=lambda x: x["walk_min"])
        val = json.dumps(hits, ensure_ascii=False) if hits else None
        conn.execute("UPDATE apartments SET future_transit=? WHERE id=?", (val, r["id"]))
        if hits:
            n_tagged += 1
    conn.commit()
    # 통계
    print(f"태깅된 단지: {n_tagged}/{len(rows)}")
    # 노선별
    from collections import Counter
    cnt = Counter()
    for r in conn.execute("SELECT future_transit FROM apartments WHERE future_transit IS NOT NULL").fetchall():
        for h in json.loads(r["future_transit"]):
            cnt[h["line"]] += 1
    for line, c in cnt.most_common():
        print(f"  {line}: {c}개 단지")
    # 문래남성 확인
    r = conn.execute("SELECT display_name, future_transit FROM apartments WHERE id=1464").fetchone()
    print(f"\n문래남성: {r['future_transit']}")
    conn.close()

if __name__ == "__main__":
    main()
