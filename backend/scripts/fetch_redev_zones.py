"""
서울시 UPIS 정비구역 경계 폴리곤 → GeoJSON 캐시
- urban.seoul.go.kr UPIS MapServer 레이어 123 (UPIS_C_UQ111)
- 25개 자치구 코드별로 조회, WGS84(4326), 정비사업 관련 SCLAS만 필터
- frontend/public/redev_zones.geojson 으로 저장
"""
import sys, json, time
sys.stdout.reconfigure(encoding='utf-8')
from pathlib import Path
import httpx

ROOT = Path(__file__).parent.parent
OUT = ROOT.parent / "frontend" / "public" / "redev_zones.geojson"

BASE = ("https://urban.seoul.go.kr/proxy/proxy.jsp?"
        "http://98.33.2.225:6080/arcgis/rest/services/UPIS/20200526_WMS/MapServer/123/query")

GU_CODES = ["11110","11140","11170","11200","11215","11230","11260","11290","11305",
            "11320","11350","11380","11410","11440","11470","11500","11530","11545",
            "11560","11590","11620","11650","11680","11710","11740"]

GU_NAME = {
    "11110":"종로구","11140":"중구","11170":"용산구","11200":"성동구","11215":"광진구",
    "11230":"동대문구","11260":"중랑구","11290":"성북구","11305":"강북구","11320":"도봉구",
    "11350":"노원구","11380":"은평구","11410":"서대문구","11440":"마포구","11470":"양천구",
    "11500":"강서구","11530":"구로구","11545":"금천구","11560":"영등포구","11590":"동작구",
    "11620":"관악구","11650":"서초구","11680":"강남구","11710":"송파구","11740":"강동구",
}

# 정비사업 관련 소분류 코드(UQA1xx = 주택재개발/재건축/도시환경/주거환경 등)
# 일반주거지역 등 용도지역 제외 위해 'UQA'로 시작하는 것만 채택
def is_redev(sclas):
    return bool(sclas) and sclas.startswith("UQA")


def main():
    all_feats = []
    with httpx.Client(verify=False, timeout=60) as c:
        for code in GU_CODES:
            params = {
                "where": f"SIGNGU_SE='{code}'",
                "outFields": "DGM_NM,SCLAS_CL,SIGNGU_SE,WTNNC_SN,DGM_AR",
                "outSR": "4326",
                "f": "geojson",
            }
            try:
                r = c.get(BASE, params=params)
                gj = r.json()
                feats = gj.get("features", [])
                kept = []
                for f in feats:
                    p = f.get("properties", {})
                    if not is_redev(p.get("SCLAS_CL")):
                        continue
                    p["gu"] = GU_NAME.get(code, code)
                    kept.append(f)
                all_feats.extend(kept)
                print(f"  {GU_NAME[code]}: {len(feats)}개 중 정비구역 {len(kept)}개")
            except Exception as e:
                print(f"  {GU_NAME[code]} 오류: {e}")
            time.sleep(0.3)

    out = {"type": "FeatureCollection", "features": all_feats}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    size_kb = OUT.stat().st_size // 1024
    print(f"\n저장: {OUT} ({len(all_feats)}개 폴리곤, {size_kb}KB)")
    # 소분류 분포
    from collections import Counter
    cnt = Counter(f["properties"].get("SCLAS_CL") for f in all_feats)
    print("소분류 분포:", dict(cnt))


if __name__ == "__main__":
    main()
