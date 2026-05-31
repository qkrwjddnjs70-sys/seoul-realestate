"""
SQLite DB 헬퍼 - 실 아파트 데이터 저장소
"""
import sqlite3
import json
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "data", "apartments.db")


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS apartments (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            name        TEXT NOT NULL,
            address     TEXT NOT NULL,
            lat         REAL DEFAULT 0,
            lng         REAL DEFAULT 0,
            lawd_cd     TEXT,
            dong        TEXT,
            built_year  INTEGER DEFAULT 0,
            last_price  INTEGER DEFAULT 0,
            last_deal_date TEXT DEFAULT '',
            area_m2     REAL DEFAULT 0,
            nearest_subway TEXT DEFAULT '',
            subway_line TEXT DEFAULT '',
            walk_minutes INTEGER DEFAULT 0,
            bus_routes  TEXT DEFAULT '[]',
            hojaes      TEXT DEFAULT '[]',
            units       INTEGER DEFAULT 0,
            floor       INTEGER DEFAULT 0,
            total_floors INTEGER DEFAULT 0,
            far         REAL DEFAULT 0,
            geocoded    INTEGER DEFAULT 0
        );

        CREATE UNIQUE INDEX IF NOT EXISTS idx_apt_key
            ON apartments(name, dong, lawd_cd);
    """)
    conn.commit()
    conn.close()


def db_exists() -> bool:
    """DB 파일과 데이터가 존재하는지 확인"""
    if not os.path.exists(DB_PATH):
        return False
    conn = get_db()
    count = conn.execute("SELECT COUNT(*) FROM apartments WHERE geocoded=1").fetchone()[0]
    conn.close()
    return count > 0


def row_to_dict(row) -> dict:
    d = dict(row)
    for field in ("bus_routes", "hojaes"):
        try:
            d[field] = json.loads(d[field])
        except Exception:
            d[field] = []
    return d


def get_apartments(
    max_walk_minutes=None,
    min_units=None, max_units=None,
    min_price=None, max_price=None,
    min_built_year=None, max_built_year=None,
    subway_station=None,
    apt_name=None,
    hojaes=None,
    max_time_gangnam=None,
    max_time_yeouido=None,
    max_time_gwanghwamun=None,
    max_time_siccheong=None,
    max_time_hongdae=None,
    lat_min=None, lat_max=None,
    lng_min=None, lng_max=None,
    lat_center=None, lng_center=None,
    lawd_cd=None,
    dong=None,
    area_bands=None,    # "50,80" 등 — 50/80㎡대 필터
    bounds_size=None,   # lng_max - lng_min (뷰포트 크기)
    redev_stages=None,  # "사업시행인가,조합설립인가" 또는 "any" — 재건축 단계 필터
    limit=800,
) -> list[dict]:
    conn = get_db()
    clauses = ["geocoded = 1"]
    params = []

    # 평형대 필터 — 지정 시 그 평형대 거래가 있는 단지만 (band 컬럼 기준)
    bands = []
    if area_bands:
        bands = [int(b.strip()) for b in area_bands.split(",") if b.strip().isdigit() and int(b.strip()) in (50, 80)]
    if bands:
        # 50/80 둘 중 하나라도 보유한 단지만
        parts = [f"price_{b}>0" for b in bands]
        clauses.append("(" + " OR ".join(parts) + ")")
    else:
        # 기본: 전체 (last_price 기준)
        clauses.append("last_price > 0")
        clauses.append("area_m2 BETWEEN 1 AND 90")

    if max_walk_minutes is not None:
        clauses.append("walk_minutes <= ?")
        params.append(max_walk_minutes)
    if min_units is not None:
        clauses.append("(units = 0 OR units >= ?)")
        params.append(min_units)
    if max_units is not None:
        clauses.append("(units = 0 OR units <= ?)")
        params.append(max_units)
    # 가격 필터 — band 선택 시 SQL 단계에서 적용 X (Python 단에서 override 후 적용)
    if not bands:
        if min_price is not None:
            clauses.append("last_price >= ?")
            params.append(min_price)
        if max_price is not None:
            clauses.append("last_price <= ?")
            params.append(max_price)
    if min_built_year is not None:
        clauses.append("(built_year = 0 OR built_year >= ?)")
        params.append(min_built_year)
    if max_built_year is not None:
        clauses.append("(built_year = 0 OR built_year <= ?)")
        params.append(max_built_year)
    if subway_station:
        clauses.append("nearest_subway LIKE ?")
        params.append(f"%{subway_station}%")

    # 재건축/재개발 단계 필터 — 정보몽땅·수동·AI 중 하나라도 단계 있으면 매칭
    if redev_stages:
        wanted = [s.strip() for s in redev_stages.split(",") if s.strip()]
        if wanted:
            if "any" in wanted:
                # '진행중 전체' — 단계가 있고 준공이 아닌 단지
                clauses.append(
                    "((redev_stage IS NOT NULL AND redev_stage!='' AND redev_stage!='준공') "
                    " OR (redev_ai_stage IS NOT NULL AND redev_ai_stage!='' AND redev_ai_stage!='준공'))"
                )
            else:
                ph = ",".join("?" * len(wanted))
                clauses.append(f"(redev_stage IN ({ph}) OR redev_ai_stage IN ({ph}))")
                params.extend(wanted)
                params.extend(wanted)
    if apt_name:
        # 띄어쓰기·끝의 "차"/"단지"/"아파트" 제거 후 양쪽(display_name + name) 매칭.
        import re as _re
        q = apt_name.replace(" ", "").strip()
        q = _re.sub(r"(차|단지|아파트)+$", "", q)
        if q:
            clauses.append(
                "(REPLACE(COALESCE(display_name, ''), ' ', '') LIKE ? "
                "OR REPLACE(name, ' ', '') LIKE ?)"
            )
            params.append(f"%{q}%")
            params.append(f"%{q}%")
    if max_time_gangnam is not None:
        clauses.append("time_gangnam <= ?"); params.append(max_time_gangnam)
    if max_time_yeouido is not None:
        clauses.append("time_yeouido <= ?"); params.append(max_time_yeouido)
    if max_time_gwanghwamun is not None:
        clauses.append("time_gwanghwamun <= ?"); params.append(max_time_gwanghwamun)
    if max_time_siccheong is not None:
        clauses.append("time_siccheong <= ?"); params.append(max_time_siccheong)
    if max_time_hongdae is not None:
        clauses.append("time_hongdae <= ?"); params.append(max_time_hongdae)
    if lawd_cd:
        codes = [c.strip() for c in lawd_cd.split(",") if c.strip()]
        if len(codes) == 1:
            clauses.append("lawd_cd = ?"); params.append(codes[0])
        elif len(codes) > 1:
            placeholders = ",".join("?" * len(codes))
            clauses.append(f"lawd_cd IN ({placeholders})")
            params.extend(codes)
    # 지도 뷰포트 범위 필터 (서버사이드)
    if dong:
        dongs = [d.strip() for d in dong.split(",") if d.strip()]
        if len(dongs) == 1:
            clauses.append("dong = ?"); params.append(dongs[0])
        elif len(dongs) > 1:
            placeholders = ",".join("?" * len(dongs))
            clauses.append(f"dong IN ({placeholders})")
            params.extend(dongs)
    if lat_min is not None:
        clauses.append("lat >= ?"); params.append(lat_min)
    if lat_max is not None:
        clauses.append("lat <= ?"); params.append(lat_max)
    if lng_min is not None:
        clauses.append("lng >= ?"); params.append(lng_min)
    if lng_max is not None:
        clauses.append("lng <= ?"); params.append(lng_max)

    where = " AND ".join(clauses)
    # 줌인(뷰포트 작을 때)만 거리순, 서울 전체 보기면 가격순
    use_distance = (
        lat_center is not None and lng_center is not None
        and bounds_size is not None and bounds_size < 0.25   # 경도 0.25° 미만 = 줌인 상태
    )
    if use_distance:
        order = f"((lat - {lat_center})*(lat - {lat_center}) + (lng - {lng_center})*(lng - {lng_center})) ASC"
    else:
        order = "last_price DESC"
    rows = conn.execute(
        f"SELECT * FROM apartments WHERE {where} ORDER BY {order} LIMIT ?",
        params + [limit],
    ).fetchall()
    conn.close()

    results = [row_to_dict(r) for r in rows]

    # band 선택 시 가격·면적·거래일을 band-specific 값으로 덮어쓰기 + min/max 필터
    if bands:
        filtered = []
        for d in results:
            best_p, best_a, best_d = 0, 0, ""
            for b in bands:
                p = d.get(f"price_{b}") or 0
                if p > 0:
                    dt = d.get(f"date_{b}") or ""
                    if not best_d or dt > best_d:
                        best_p = p
                        best_a = d.get(f"area_{b}") or 0
                        best_d = dt
            if best_p <= 0:
                continue
            if min_price is not None and best_p < min_price:
                continue
            if max_price is not None and best_p > max_price:
                continue
            d["last_price"]     = best_p
            d["area_m2"]        = best_a
            d["last_deal_date"] = best_d
            filtered.append(d)
        results = filtered

    if hojaes:
        results = [r for r in results if any(t in r["hojaes"] for t in hojaes)]

    return results


def get_apartment_by_id(apt_id: int) -> dict | None:
    conn = get_db()
    row = conn.execute("SELECT * FROM apartments WHERE id = ?", (apt_id,)).fetchone()
    conn.close()
    return row_to_dict(row) if row else None


def get_meta() -> dict:
    conn = get_db()
    row = conn.execute("""
        SELECT
            MIN(last_price) AS min_price, MAX(last_price) AS max_price,
            MIN(NULLIF(built_year,0)) AS min_built_year, MAX(built_year) AS max_built_year,
            MIN(NULLIF(walk_minutes,0)) AS min_walk, MAX(walk_minutes) AS max_walk,
            MIN(NULLIF(units,0)) AS min_units, MAX(units) AS max_units
        FROM apartments WHERE geocoded=1 AND last_price > 0
    """).fetchone()
    conn.close()
    return dict(row) if row else {}
