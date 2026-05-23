"""
문래동삼환아파트 (aptSeq=11560-63) DB에 추가 + 보강
"""
import os, sqlite3, httpx, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

KAKAO = os.getenv("KAKAO_REST_KEY", "")
MOLIT = os.getenv("MOLIT_API_KEY", "")
DB = Path(__file__).parent.parent / "data" / "apartments.db"

# 최근 거래 정보 (MOLIT에서 확인됨)
NAME = "문래동삼환"
APT_SEQ = "11560-63"
ADDRESS = "서울특별시 영등포구 문래동4가"
LAWD_CD = "11560"
DONG = "문래동4가"
PRICE = 96500   # 만원 (2026-01-29 거래)
AREA = 59.85
DEAL = "2026-01-29"

# 1) Kakao 주소 → 좌표
r = httpx.get("https://dapi.kakao.com/v2/local/search/keyword.json",
              headers={"Authorization": f"KakaoAK {KAKAO}"},
              params={"query": "영등포구 문래동4가 삼환아파트", "size": 5},
              timeout=10)
lat = lng = None
for d in r.json().get("documents", []):
    if "삼환" in d.get("place_name", ""):
        lat, lng = float(d["y"]), float(d["x"])
        print(f"좌표: {d['place_name']} → ({lat}, {lng})")
        break
if not (lat and lng):
    # 주소 기반 폴백
    r2 = httpx.get("https://dapi.kakao.com/v2/local/search/address.json",
                   headers={"Authorization": f"KakaoAK {KAKAO}"},
                   params={"query": "서울 영등포구 문래동4가"}, timeout=10)
    docs = r2.json().get("documents", [])
    if docs:
        lat, lng = float(docs[0]["y"]), float(docs[0]["x"])
        print(f"폴백 좌표: ({lat}, {lng})")

# 2) ODCloud 으로 세대수·PNU 찾기
units = 0
pnu = None
r = httpx.get("https://api.odcloud.kr/api/AptIdInfoSvc/v1/getAptInfo",
              params={"serviceKey": MOLIT, "page": 1, "perPage": 1000,
                      "cond[ADRES::LIKE]": "문래동"}, timeout=30)
for it in r.json().get("data", []):
    for fld in ("COMPLEX_NM1", "COMPLEX_NM2", "COMPLEX_NM3"):
        nm = (it.get(fld) or "").replace(" ", "")
        if "삼환" in nm and "문래" in nm:
            units = it.get("UNIT_CNT") or 0
            pnu = it.get("PNU")
            print(f"ODCloud: {nm} | UNIT={units} | PNU={pnu}")
            break
    if pnu: break

# 3) 건축물대장 → 용적률
far = 0
if pnu and len(pnu) == 19:
    sg, bj, bun, ji = pnu[:5], pnu[5:10], pnu[11:15], pnu[15:19]
    r = httpx.get("https://apis.data.go.kr/1613000/BldRgstHubService/getBrRecapTitleInfo",
                  params={"serviceKey": MOLIT, "sigunguCd": sg, "bjdongCd": bj,
                          "platGbCd": "0", "bun": bun, "ji": ji,
                          "numOfRows": 10, "pageNo": 1, "_type": "json"}, timeout=20)
    items = r.json().get("response", {}).get("body", {}).get("items", {}).get("item")
    if items:
        if isinstance(items, dict): items = [items]
        for it in items:
            vl = float(it.get("vlRat") or 0)
            if vl > 0:
                far = round(vl, 1)
                break

# 4) INSERT
conn = sqlite3.connect(DB)
existing = conn.execute("SELECT id FROM apartments WHERE apt_seq=?", (APT_SEQ,)).fetchone()
if existing:
    print(f"이미 존재 id={existing[0]}")
else:
    display_name = NAME   # 이미 동 prefix 포함된 풀네임
    conn.execute("""
        INSERT INTO apartments
        (name, address, lat, lng, lawd_cd, dong, built_year, last_price, last_deal_date,
         area_m2, nearest_subway, subway_line, walk_minutes, bus_routes, hojaes,
         units, floor, total_floors, far, slope, geocoded, apt_seq, display_name)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, (
        NAME, ADDRESS, lat or 0, lng or 0, LAWD_CD, DONG, 1986,
        PRICE, DEAL, AREA, "문래", "2호선", 0, "[]", "[]",
        units, 0, 0, far, 0, 1 if (lat and lng) else 0, APT_SEQ, display_name,
    ))
    conn.commit()
    print(f"추가됨 — units={units}, far={far}, lat={lat}, lng={lng}")
conn.close()
