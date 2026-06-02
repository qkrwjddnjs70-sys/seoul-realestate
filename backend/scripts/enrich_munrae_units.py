"""문래동 정비사업에 세대수·정확 좌표 보강 (큐레이션)"""
import json
from pathlib import Path
ROOT = Path(__file__).parent.parent
fp = ROOT / "data" / "redev_points.json"
zones = json.loads(fp.read_text(encoding="utf-8"))

# 큐레이션 데이터 (이름 키워드 → units, 정확 좌표)
CURATED = [
    ("문래동4가 재개발(문래네이븐)", "재개발", 2176, "조합설립인가·시공사선정(삼성물산·대우)", 37.5150504796577, 126.890374150617, ["문래동4가","네이븐","문래4"]),
    ("문래진주 재건축(더샵 르프리베)", "재건축", 324, "관리처분·이주", 37.5171739609813, 126.884785741455, ["문래진주","진주"]),
    ("문래국화아파트 재건축", "재건축", 662, "조합설립/추진위", 37.5163766907311, 126.892756094025, ["문래국화","국화"]),
    ("남성아파트 재건축(포레나 문래)", "재건축", 488, "사업시행인가", 37.5125889887418, 126.8916007938, ["남성"]),
    ("문래공원한신 재건축", "재건축", None, "안전진단", 37.5175839837132, 126.892997679027, ["공원한신"]),
    ("대선제분 재개발1구역", "재개발(도시정비형)", None, "사업시행인가", 37.5178944111753, 126.900989487235, ["대선제분"]),
    ("문래동1·2가 도시환경정비", "재개발(도시정비형)", None, "정비구역지정", 37.5113791801412, 126.894250598342, ["문래동1","문래동1·2"]),
    ("문래동2·3가 도시환경정비", "재개발(도시정비형)", None, "정비구역지정", 37.5135123288362, 126.894577756619, ["문래동2·3","문래동3가 도시환경"]),
]

# 기존 항목에 units 필드 디폴트 추가
for z in zones:
    z.setdefault("units", None)

# 큐레이션 단지: 기존 매칭되면 갱신, 없으면 추가
for nm, typ, units, stage, lat, lng, keys in CURATED:
    matched = None
    for z in zones:
        if z["gu"] == "영등포구" and any(k.replace(" ","") in (z["name"]+z.get("jibun","")).replace(" ","") for k in keys):
            matched = z; break
    if matched:
        matched["name"] = nm; matched["type"] = typ; matched["units"] = units
        matched["stage"] = stage; matched["lat"] = lat; matched["lng"] = lng
    else:
        zones.append({"name": nm, "type": typ, "units": units, "stage": stage,
                      "gu": "영등포구", "dong": "문래동", "jibun": "", "lat": lat, "lng": lng})

fp.write_text(json.dumps(zones, ensure_ascii=False), encoding="utf-8")
print(f"문래 큐레이션 반영 완료. 전체 {len(zones)}개")
mun = [z for z in zones if "문래" in z.get("dong","") or z["name"].startswith("문래") or "남성" in z["name"] or "대선제분" in z["name"]]
for z in mun:
    print(f"  {z['name']} | {z.get('units')}세대 | {z['stage']}")
