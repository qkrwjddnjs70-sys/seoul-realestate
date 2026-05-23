"""
카카오 카테고리 검색(SC4=학교)으로 강서구·영등포구 초/중/고 수집
→ backend/data/schools.json 저장
"""
import os, sys, json, time
import httpx
from dotenv import load_dotenv

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))

KAKAO_KEY = os.getenv("KAKAO_REST_KEY", "")
HEADERS = {"Authorization": f"KakaoAK {KAKAO_KEY}"}
URL = "https://dapi.kakao.com/v2/local/search/category.json"

# 강서구 + 영등포구 포괄 영역
LAT_MIN, LAT_MAX = 37.47, 37.61
LNG_MIN, LNG_MAX = 126.77, 126.98
STEP = 0.02

schools = {}


def fetch_cell(lng, lat):
    rect = f"{lng:.4f},{lat:.4f},{lng+STEP:.4f},{lat+STEP:.4f}"
    page = 1
    while True:
        try:
            r = httpx.get(URL, headers=HEADERS, timeout=10, params={
                "category_group_code": "SC4",
                "rect": rect, "page": page, "size": 15,
            })
        except Exception as e:
            print(f"  요청 실패: {e}")
            return
        if r.status_code != 200:
            print(f"  HTTP {r.status_code}: {r.text[:120]}")
            return
        data = r.json()
        for doc in data.get("documents", []):
            addr = doc.get("address_name", "") or doc.get("road_address_name", "")
            if "강서구" not in addr and "영등포구" not in addr:
                continue
            cat = doc.get("category_name", "")
            if "초등학교" in cat:   kind = "초"
            elif "중학교" in cat:   kind = "중"
            elif "고등학교" in cat: kind = "고"
            else:                   continue   # 대학교/특수 제외
            schools[doc["id"]] = {
                "name":    doc["place_name"],
                "kind":    kind,
                "lat":     float(doc["y"]),
                "lng":     float(doc["x"]),
                "address": addr,
                "gu":      "강서구" if "강서구" in addr else "영등포구",
            }
        if data.get("meta", {}).get("is_end", True):
            return
        page += 1
        if page > 3:   # 최대 45개
            return


def main():
    lat = LAT_MIN
    cells = 0
    while lat < LAT_MAX:
        lng = LNG_MIN
        while lng < LNG_MAX:
            fetch_cell(lng, lat)
            cells += 1
            lng += STEP
            time.sleep(0.05)
        lat += STEP

    result = sorted(schools.values(), key=lambda s: (s["gu"], s["kind"], s["name"]))
    out_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "data", "schools.json"
    )
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=1)

    by_gu = {}
    for s in result:
        by_gu.setdefault(s["gu"], {"초": 0, "중": 0, "고": 0})
        by_gu[s["gu"]][s["kind"]] += 1
    print(f"검색 셀: {cells}개")
    print(f"총 학교: {len(result)}개")
    for gu, c in by_gu.items():
        print(f"  {gu}: 초 {c['초']} / 중 {c['중']} / 고 {c['고']}")
    print(f"저장: {out_path}")


if __name__ == "__main__":
    main()
