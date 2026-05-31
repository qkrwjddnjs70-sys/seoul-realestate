import re
from typing import Optional
from fastapi import APIRouter, Query

import database as db_module
from data.mock_properties import PROPERTIES

router = APIRouter()


def _use_db() -> bool:
    try:
        return db_module.db_exists()
    except Exception:
        return False


# ───── 아파트 이름 풀네임 보정 ─────
# 같은 단지명("우성" 등)이 여러 동에 흩어져 있으면 동 접두어를 붙여 구분한다.
_AMBIGUOUS_BASES = None


def _base_name(name: str) -> str:
    """끝의 숫자·차 제거: '우성1차'→'우성', '신길우성2'→'신길우성'"""
    return re.sub(r"\d+\s*차?$", "", name or "").strip()


def _dong_prefix(dong: str) -> str:
    """'신길동'→'신길', '당산동5가'→'당산', '여의도동'→'여의도'"""
    if not dong:
        return ""
    return dong.split("동")[0].strip()


def _load_ambiguous() -> set:
    """2개 이상의 동에 걸쳐 존재하는 단지명(base) 집합"""
    global _AMBIGUOUS_BASES
    if _AMBIGUOUS_BASES is not None:
        return _AMBIGUOUS_BASES
    base_dongs: dict[str, set] = {}
    try:
        conn = db_module.get_db()
        rows = conn.execute("SELECT name, dong FROM apartments WHERE geocoded=1").fetchall()
        conn.close()
        for r in rows:
            base = _base_name(r["name"])
            if base:
                base_dongs.setdefault(base, set()).add(r["dong"])
    except Exception:
        pass
    _AMBIGUOUS_BASES = {b for b, dongs in base_dongs.items() if len(dongs) >= 2}
    return _AMBIGUOUS_BASES


def _display_name(name: str, dong: str) -> str:
    """모호한 단지명에 동 접두어 부여 + 끝 숫자 → N차"""
    if not name:
        return name
    out = name
    base = _base_name(name)
    prefix = _dong_prefix(dong)
    # 동 접두어 (모호한 이름 + 아직 접두어 없을 때)
    if base in _load_ambiguous() and prefix and prefix not in name:
        out = prefix + name
    # 끝자리 한 자리 숫자 → N차 (이미 차/단지/주공이면 건너뜀)
    if not any(x in out for x in ("차", "단지", "주공")):
        out = re.sub(r"(?<!\d)(\d)$", r"\1차", out)
    return out


def _mock_to_property(p: dict) -> dict:
    return {
        "id":             p["id"],
        "name":           p["name"],
        "address":        p["address"],
        "lat":            p["lat"],
        "lng":            p["lng"],
        "price":          p["price"],
        "area_m2":        p["area_m2"],
        "floor":          p.get("floor", 0),
        "total_floors":   p.get("total_floors", 0),
        "units":          p.get("units", 0),
        "built_year":     p.get("built_year", 0),
        "nearest_subway": p.get("nearest_subway", ""),
        "subway_line":    p.get("subway_line", ""),
        "walk_minutes":   p.get("walk_minutes", 0),
        "bus_routes":     p.get("bus_routes", []),
        "transaction_date": p.get("transaction_date", ""),
        "lawd_cd":        p.get("lawd_cd", ""),
        "hojaes":         p.get("hojaes", []),
        "is_mock":        True,
    }


def _parse_future_transit(val):
    if not val:
        return []
    try:
        import json as _j
        return _j.loads(val)
    except Exception:
        return []


def _db_to_property(row: dict) -> dict:
    return {
        "id":             row["id"],
        "name":           row.get("display_name") or _display_name(row["name"], row["dong"]),
        "address":        row["address"],
        "lat":            row["lat"],
        "lng":            row["lng"],
        "price":          row["last_price"],
        "area_m2":        row["area_m2"],
        "floor":          row["floor"],
        "total_floors":   row["total_floors"],
        "units":          row["units"],
        "far":            row["far"],
        "slope":          row["slope"] if "slope" in row.keys() else 0,
        "built_year":     row["built_year"],
        "nearest_subway": row["nearest_subway"],
        "subway_line":    row["subway_line"],
        "walk_minutes":   row["walk_minutes"],
        "bus_routes":     row["bus_routes"],
        "transaction_date": row["last_deal_date"],
        "lawd_cd":        row["lawd_cd"],
        "hojaes":         row["hojaes"],
        "naver_id":      row.get("naver_id") or "",
        # 대지지분(이론): 공급면적(전용/0.75) ÷ (용적률/100)
        #   = area_m2 × 133.3 / far
        #   예: 59㎡ + far 246% → 32.1㎡
        "land_share":    (
            round(row["area_m2"] * 133.3 / row["far"], 1)
            if (row.get("far") and row["far"] > 0 and row.get("area_m2"))
            else 0
        ),
        "lot_area":      row.get("lot_area") or 0,   # K-apt 단지 부지 (참고용)
        "builder":       row.get("builder") or "",
        "redev_stage":     row.get("redev_stage") or "",
        "redev_detail":    row.get("redev_detail") or "",
        "redev_updated":   row.get("redev_updated") or "",
        "redev_ai_stage":  row.get("redev_ai_stage") or "",
        "redev_ai_detail": row.get("redev_ai_detail") or "",
        "future_transit":  _parse_future_transit(row.get("future_transit")),
        "commute": {
            "gangnam":     row.get("time_gangnam", 0),
            "yeouido":     row.get("time_yeouido", 0),
            "gwanghwamun": row.get("time_gwanghwamun", 0),
            "siccheong":   row.get("time_siccheong", 0),
            "hongdae":     row.get("time_hongdae", 0),
        },
        "is_mock":        False,
    }


@router.get("")
def get_properties(
    max_walk_minutes:    Optional[int]   = Query(None),
    min_units:           Optional[int]   = Query(None),
    max_units:           Optional[int]   = Query(None),
    min_price:           Optional[int]   = Query(None),
    max_price:           Optional[int]   = Query(None),
    min_built_year:      Optional[int]   = Query(None),
    max_built_year:      Optional[int]   = Query(None),
    subway_station:      Optional[str]   = Query(None),
    apt_name:            Optional[str]   = Query(None),
    hojaes:              Optional[str]   = Query(None),
    max_time_gangnam:    Optional[int]   = Query(None),
    max_time_yeouido:    Optional[int]   = Query(None),
    max_time_gwanghwamun:Optional[int]   = Query(None),
    max_time_siccheong:  Optional[int]   = Query(None),
    max_time_hongdae:    Optional[int]   = Query(None),
    lat_min:             Optional[float] = Query(None),
    lat_max:             Optional[float] = Query(None),
    lng_min:             Optional[float] = Query(None),
    lng_max:             Optional[float] = Query(None),
    lat_center:          Optional[float] = Query(None),
    lng_center:          Optional[float] = Query(None),
    lawd_cd:             Optional[str]   = Query(None),
    dong:                Optional[str]   = Query(None),
    area_bands:          Optional[str]   = Query(None),
    bounds_size:         Optional[float] = Query(None),
    redev_stages:        Optional[str]   = Query(None),
):
    hojae_list = [t.strip() for t in hojaes.split(",") if t.strip()] if hojaes else None

    if _use_db():
        rows = db_module.get_apartments(
            max_walk_minutes=max_walk_minutes,
            min_units=min_units, max_units=max_units,
            min_price=min_price, max_price=max_price,
            min_built_year=min_built_year, max_built_year=max_built_year,
            subway_station=subway_station,
            apt_name=apt_name,
            hojaes=hojae_list,
            max_time_gangnam=max_time_gangnam,
            max_time_yeouido=max_time_yeouido,
            max_time_gwanghwamun=max_time_gwanghwamun,
            max_time_siccheong=max_time_siccheong,
            max_time_hongdae=max_time_hongdae,
            lat_min=lat_min, lat_max=lat_max,
            lng_min=lng_min, lng_max=lng_max,
            lat_center=lat_center, lng_center=lng_center,
            lawd_cd=lawd_cd,
            dong=dong,
            area_bands=area_bands,
            bounds_size=bounds_size,
            redev_stages=redev_stages,
        )
        items = [_db_to_property(r) for r in rows]
        is_mock = False
    else:
        filtered = _filter_mock(
            max_walk_minutes, min_units, max_units,
            min_price, max_price, min_built_year, max_built_year,
            bus_route, subway_station, hojae_list,
        )
        items = [_mock_to_property(p) for p in filtered]
        is_mock = True

    return {"total": len(items), "items": items, "is_mock": is_mock}


def _filter_mock(
    max_walk_minutes=None, min_units=None, max_units=None,
    min_price=None, max_price=None,
    min_built_year=None, max_built_year=None,
    bus_route=None, subway_station=None, hojae_list=None,
) -> list[dict]:
    results = list(PROPERTIES)
    if max_walk_minutes is not None:
        results = [p for p in results if p["walk_minutes"] <= max_walk_minutes]
    if min_units is not None:
        results = [p for p in results if p["units"] >= min_units]
    if max_units is not None:
        results = [p for p in results if p["units"] <= max_units]
    if min_price is not None:
        results = [p for p in results if p["price"] >= min_price]
    if max_price is not None:
        results = [p for p in results if p["price"] <= max_price]
    if min_built_year is not None:
        results = [p for p in results if p["built_year"] >= min_built_year]
    if max_built_year is not None:
        results = [p for p in results if p["built_year"] <= max_built_year]
    if subway_station:
        results = [p for p in results if subway_station in p["nearest_subway"]]
    if bus_route:
        results = [p for p in results if any(bus_route in b for b in p["bus_routes"])]
    if hojae_list:
        results = [p for p in results if any(t in p.get("hojaes", []) for t in hojae_list)]
    return results


@router.get("/dongs")
def get_dongs(lawd_cd: str = ""):
    """특정 구의 동 목록 반환"""
    if not _use_db():
        return {"dongs": []}
    import database as db
    conn = db.get_db()
    if lawd_cd:
        codes = [c.strip() for c in lawd_cd.split(",") if c.strip()]
        placeholders = ",".join("?" * len(codes))
        rows = conn.execute(
            f"SELECT DISTINCT dong FROM apartments WHERE lawd_cd IN ({placeholders}) AND geocoded=1 AND last_price>0 AND dong!='' ORDER BY dong",
            codes
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT DISTINCT dong FROM apartments WHERE geocoded=1 AND last_price>0 AND dong!='' ORDER BY dong"
        ).fetchall()
    conn.close()
    return {"dongs": [r[0] for r in rows]}


@router.get("/meta/filters")
def get_filter_meta():
    if _use_db():
        meta = db_module.get_meta()
        return {
            "min_price":      meta.get("min_price", 10000),
            "max_price":      meta.get("max_price", 500000),
            "min_units":      meta.get("min_units", 0),
            "max_units":      meta.get("max_units", 10000),
            "min_built_year": meta.get("min_built_year", 1985),
            "max_built_year": meta.get("max_built_year", 2026),
            "min_walk":       meta.get("min_walk", 1),
            "max_walk":       meta.get("max_walk", 30),
            "is_mock":        False,
        }
    prices = [p["price"] for p in PROPERTIES]
    years  = [p["built_year"] for p in PROPERTIES]
    units  = [p["units"] for p in PROPERTIES]
    walks  = [p["walk_minutes"] for p in PROPERTIES]
    return {
        "price":       {"min": min(prices), "max": max(prices)},
        "units":       {"min": min(units),  "max": max(units)},
        "built_year":  {"min": min(years),  "max": max(years)},
        "walk_minutes":{"min": min(walks),  "max": max(walks)},
        "bus_routes":  sorted({b for p in PROPERTIES for b in p["bus_routes"]}),
        "hojaes":      sorted({t for p in PROPERTIES for t in p.get("hojaes", [])}),
        "is_mock":     True,
    }


@router.get("/{property_id}")
def get_property(property_id: int):
    if _use_db():
        row = db_module.get_apartment_by_id(property_id)
        if row:
            return _db_to_property(row)
    for p in PROPERTIES:
        if p["id"] == property_id:
            return _mock_to_property(p)
    from fastapi import HTTPException
    raise HTTPException(status_code=404, detail="매물을 찾을 수 없습니다")


# ─────────── 지역 개발성 (반경 700m 재건축 + 동 정비사업) ───────────
import os as _os, json as _json, math as _math

_GU_FULL = {
    "11110":"종로구","11140":"중구","11170":"용산구","11200":"성동구","11215":"광진구",
    "11230":"동대문구","11260":"중랑구","11290":"성북구","11305":"강북구","11320":"도봉구",
    "11350":"노원구","11380":"은평구","11410":"서대문구","11440":"마포구","11470":"양천구",
    "11500":"강서구","11530":"구로구","11545":"금천구","11560":"영등포구","11590":"동작구",
    "11620":"관악구","11650":"서초구","11680":"강남구","11710":"송파구","11740":"강동구",
}
_DEAD = {"조합해산","조합청산","청산 및 조합해산","이전고시"}
_CLEANUP = {}
try:
    _cjp = _os.path.join(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))), "data", "cleanup_projects.json")
    with open(_cjp, encoding="utf-8") as _f:
        for _p in _json.load(_f):
            _bd = re.match(r"([가-힣]+동)", _p.get("dong","") or "")
            _key = (_p["gu"], _bd.group(1) if _bd else _p.get("dong",""))
            _CLEANUP.setdefault(_key, []).append(_p)
except Exception:
    pass

def _hav(la1, ln1, la2, ln2):
    R=6371; dlat=_math.radians(la2-la1); dlng=_math.radians(ln2-ln1)
    a=_math.sin(dlat/2)**2+_math.cos(_math.radians(la1))*_math.cos(_math.radians(la2))*_math.sin(dlng/2)**2
    return R*2*_math.asin(_math.sqrt(a))


@router.get("/{property_id}/development")
def get_development(property_id: int):
    """단지 주변 개발성 — 반경 700m 재건축 + 동 정비사업 (정보몽땅)"""
    if not _use_db():
        return {"nearby_redev": [], "dong_projects": []}
    row = db_module.get_apartment_by_id(property_id)
    if not row:
        return {"nearby_redev": [], "dong_projects": []}
    apt = dict(row)
    nearby, projects = [], []
    # 반경 700m 재건축
    if apt.get("lat") and apt.get("lng"):
        conn = db_module.get_db()
        rows = conn.execute(
            "SELECT id, display_name, name, lat, lng, redev_stage, redev_ai_stage "
            "FROM apartments WHERE lawd_cd=? AND geocoded=1 "
            "AND (redev_stage IS NOT NULL AND redev_stage!='' "
            "  OR redev_ai_stage IS NOT NULL AND redev_ai_stage!='')",
            (apt.get("lawd_cd"),)
        ).fetchall()
        conn.close()
        for r in rows:
            if r["id"] == property_id or not r["lat"] or not r["lng"]:
                continue
            d = _hav(apt["lat"], apt["lng"], r["lat"], r["lng"])
            if 0 < d <= 0.7:
                nearby.append({
                    "name": r["display_name"] or r["name"],
                    "dist_m": int(d*1000),
                    "stage": r["redev_stage"] or r["redev_ai_stage"],
                    "official": bool(r["redev_stage"]),
                })
        nearby.sort(key=lambda x: x["dist_m"]); nearby = nearby[:10]
    # 동 정비사업
    gu = _GU_FULL.get(apt.get("lawd_cd"))
    m = re.search(r"([가-힣]+동)(?!구)(?:\d+가)?", apt.get("address") or "")
    base_dong = m.group(1) if m else ""
    if gu and base_dong:
        seen = set()
        for p in _CLEANUP.get((gu, base_dong), []):
            if p["stage"] in _DEAD or p["name"] in seen:
                continue
            seen.add(p["name"])
            projects.append({"name": p["name"][:30], "type": p["type"][:12], "stage": p["stage"]})
    return {"nearby_redev": nearby, "dong_projects": projects, "dong": base_dong}


@router.patch("/{property_id}/manual")
def patch_manual(property_id: int, payload: dict):
    """단지 정보 수동 입력 — 사용자가 직접 알려주는 정확한 값 저장
    payload: { "far": 240.0, "units": 417 } 등. 입력 즉시 manual 플래그 ON
    그러면 enrich 스크립트들이 해당 값을 덮어쓰지 않음.
    """
    from fastapi import HTTPException
    if not _use_db():
        raise HTTPException(status_code=503, detail="DB 미사용")
    sets, vals = [], []
    # 숫자 필드
    for k, col in [("far", "far"), ("units", "units")]:
        if k in payload and payload[k] is not None:
            try:
                v = float(payload[k]) if k == "far" else int(payload[k])
                if v < 0: continue
                sets.append(f"{col}=?"); vals.append(v)
                sets.append(f"{col}_manual=1")
            except Exception:
                pass
    # 재건축 단계 (문자열)
    if "redev_stage" in payload:
        stage = (payload.get("redev_stage") or "").strip()
        sets.append("redev_stage=?"); vals.append(stage or None)
        detail = (payload.get("redev_detail") or "").strip()
        if detail:
            sets.append("redev_detail=?"); vals.append(detail)
        sets.append("redev_manual=1")
        # 업데이트 일자도 자동 갱신
        from datetime import datetime
        sets.append("redev_updated=?"); vals.append(datetime.now().strftime("%Y-%m-%d"))
    if not sets:
        raise HTTPException(status_code=400, detail="입력값이 없습니다")
    conn = db_module.get_db()
    vals.append(property_id)
    conn.execute(f"UPDATE apartments SET {', '.join(sets)} WHERE id=?", vals)
    conn.commit()
    row = conn.execute("SELECT * FROM apartments WHERE id=?", (property_id,)).fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="단지 없음")
    return _db_to_property(dict(row))
