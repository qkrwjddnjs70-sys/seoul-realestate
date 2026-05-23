"""
서울 지하철 노선도 일괄 재구축
- 노선별 역 목록을 올바르게 정의
- 카카오 Local API 키워드 검색(SW8 카테고리)으로 각 역 좌표 조회
- frontend/src/data/subwayLines.js 로 출력
"""
import os, re, asyncio
from pathlib import Path
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")
import httpx

KAKAO_KEY = os.getenv("KAKAO_REST_KEY", "")
HEADERS = {"Authorization": f"KakaoAK {KAKAO_KEY}"}
URL = "https://dapi.kakao.com/v2/local/search/keyword.json"

LINES = [
    {"id": 1, "name": "1호선", "color": "#0052A4", "stations": [
        "도봉산", "도봉", "방학", "창동", "녹천", "월계", "광운대", "석계",
        "신이문", "외대앞", "회기", "청량리", "제기동", "신설동", "동묘앞",
        "동대문", "종로5가", "종로3가", "종각", "시청", "서울역", "남영",
        "용산", "노량진", "대방", "신길", "영등포", "신도림", "구로",
        "가산디지털단지", "독산", "금천구청",
    ]},
    {"id": 2, "name": "2호선", "color": "#009D3E", "stations": [
        "시청", "을지로입구", "을지로3가", "을지로4가", "동대문역사문화공원",
        "신당", "상왕십리", "왕십리", "한양대", "뚝섬", "성수", "건대입구",
        "구의", "강변", "잠실나루", "잠실", "잠실새내", "종합운동장",
        "삼성", "선릉", "역삼", "강남", "교대", "서초", "방배", "사당",
        "낙성대", "서울대입구", "봉천", "신림", "신대방", "구로디지털단지",
        "대림", "신도림", "문래", "영등포구청", "당산", "합정", "홍대입구",
        "신촌", "이대", "아현", "충정로", "시청",
    ]},
    {"id": 3, "name": "3호선", "color": "#EF7C1C", "stations": [
        "지축", "구파발", "연신내", "불광", "녹번", "홍제", "무악재",
        "독립문", "경복궁", "안국", "종로3가", "을지로3가", "충무로",
        "동대입구", "약수", "금호", "옥수", "압구정", "신사", "잠원",
        "고속터미널", "교대", "남부터미널", "양재", "매봉", "도곡", "대치",
        "학여울", "대청", "일원", "수서", "가락시장", "경찰병원", "오금",
    ]},
    {"id": 4, "name": "4호선", "color": "#00A5DE", "stations": [
        "당고개", "상계", "노원", "창동", "쌍문", "수유", "미아", "미아사거리",
        "길음", "성신여대입구", "한성대입구", "혜화", "동대문",
        "동대문역사문화공원", "충무로", "명동", "회현", "서울역", "숙대입구",
        "삼각지", "신용산", "이촌", "동작", "이수", "사당", "남태령",
    ]},
    {"id": 5, "name": "5호선", "color": "#996CAC", "stations": [
        "방화", "개화산", "김포공항", "송정", "마곡", "발산", "우장산", "화곡",
        "까치산", "신정", "목동", "오목교", "양평", "영등포구청", "영등포시장",
        "신길", "여의도", "여의나루", "마포", "공덕", "애오개", "충정로",
        "서대문", "광화문", "종로3가", "을지로4가", "동대문역사문화공원",
        "청구", "신금호", "행당", "왕십리", "마장", "답십리", "장한평",
        "군자", "아차산", "광나루", "천호", "강동",
    ]},
    {"id": 51, "name": "5호선(상일동)", "color": "#996CAC", "stations": [
        "강동", "길동", "굽은다리", "명일", "고덕", "상일동",
    ]},
    {"id": 52, "name": "5호선(마천)", "color": "#996CAC", "stations": [
        "강동", "둔촌동", "올림픽공원", "방이", "오금", "개롱", "거여", "마천",
    ]},
    {"id": 6, "name": "6호선", "color": "#CD7C2F", "stations": [
        "응암", "역촌", "불광", "독바위", "연신내", "구산", "새절", "증산",
        "디지털미디어시티", "월드컵경기장", "마포구청", "망원", "합정", "상수",
        "광흥창", "대흥", "공덕", "효창공원앞", "삼각지", "녹사평", "이태원",
        "한강진", "버티고개", "약수", "청구", "신당", "동묘앞", "창신",
        "보문", "안암", "고려대", "월곡", "상월곡", "돌곶이", "석계",
        "태릉입구", "화랑대", "봉화산",
    ]},
    {"id": 7, "name": "7호선", "color": "#747F00", "stations": [
        "장암", "도봉산", "수락산", "마들", "노원", "중계", "하계", "공릉",
        "태릉입구", "먹골", "중화", "상봉", "면목", "사가정", "용마산", "중곡",
        "군자", "어린이대공원", "건대입구", "뚝섬유원지", "청담", "강남구청",
        "학동", "논현", "반포", "고속터미널", "내방", "이수", "남성",
        "숭실대입구", "상도", "장승배기", "신대방삼거리", "보라매", "신풍",
        "대림", "가산디지털단지", "철산", "광명사거리", "천왕", "온수",
    ]},
    {"id": 8, "name": "8호선", "color": "#E6186C", "stations": [
        "암사", "천호", "강동구청", "몽촌토성", "잠실", "석촌", "송파",
        "가락시장", "문정", "장지", "복정", "남위례", "산성", "남한산성입구",
        "단대오거리", "신흥", "수진", "모란",
    ]},
    {"id": 9, "name": "9호선", "color": "#BDB092", "stations": [
        "개화", "김포공항", "공항시장", "신방화", "마곡나루", "양천향교",
        "가양", "증미", "등촌", "염창", "신목동", "선유도", "당산",
        "국회의사당", "여의도", "샛강", "노량진", "노들", "흑석", "동작",
        "구반포", "신반포", "고속터미널", "사평", "신논현", "언주", "선정릉",
        "삼성중앙", "봉은사", "종합운동장", "삼전", "석촌고분", "석촌",
        "송파나루", "한성백제", "올림픽공원", "둔촌오륜", "중앙보훈병원",
    ]},
]


async def lookup_station(client, station: str, base_line: str):
    """Kakao 검색 → category_name에 노선명 포함된 결과 우선"""
    queries = [f"{station}역 {base_line}", f"{station}역"]
    for q in queries:
        try:
            r = await client.get(URL, headers=HEADERS, params={
                "query": q, "category_group_code": "SW8", "size": 15,
            })
            if r.status_code != 200:
                continue
            docs = r.json().get("documents", [])
            # 1순위: place_name에 역이름 + category에 노선명
            for d in docs:
                if station in (d.get("place_name") or "") and base_line in (d.get("category_name") or ""):
                    return float(d["y"]), float(d["x"])
            # 2순위: category에 노선명
            for d in docs:
                if base_line in (d.get("category_name") or ""):
                    return float(d["y"]), float(d["x"])
        except Exception:
            continue
    # 마지막: 노선명 무시하고 역이름만으로
    try:
        r = await client.get(URL, headers=HEADERS, params={
            "query": f"{station}역", "category_group_code": "SW8", "size": 5,
        })
        if r.status_code == 200:
            for d in r.json().get("documents", []):
                if station in (d.get("place_name") or ""):
                    return float(d["y"]), float(d["x"])
    except Exception:
        pass
    return None


async def main():
    if not KAKAO_KEY:
        print("[오류] KAKAO_REST_KEY 없음")
        return
    out_lines = []
    async with httpx.AsyncClient(timeout=15) as client:
        for line in LINES:
            base = re.sub(r"\(.*\)", "", line["name"]).strip()
            print(f"[{line['name']}] {len(line['stations'])}개...", end=" ", flush=True)
            tasks = [lookup_station(client, s, base) for s in line["stations"]]
            results = await asyncio.gather(*tasks)
            coords = list(zip(results, line["stations"]))
            miss = sum(1 for r, _ in coords if r is None)
            print(f"실패 {miss}")
            out_lines.append({**line, "coords": coords})
            await asyncio.sleep(0.2)

    js = ["// 서울 지하철 노선 좌표 — Kakao Local API 일괄 보강",
          "export const SUBWAY_LINES = ["]
    for ln in out_lines:
        js.append("  {")
        js.append(f"    id: {ln['id']}, name: '{ln['name']}', color: '{ln['color']}',")
        js.append("    stations: [")
        for res, name in ln["coords"]:
            if res:
                lat, lng = res
                js.append(f"      [{lat:.4f}, {lng:.4f}, '{name}'],")
            else:
                js.append(f"      // 좌표 못찾음: {name}")
        js.append("    ],")
        js.append("  },")
    js.append("]")

    out_path = Path(__file__).parent.parent.parent / "frontend" / "src" / "data" / "subwayLines.js"
    out_path.write_text("\n".join(js) + "\n", encoding="utf-8")
    print(f"\n저장: {out_path}")


if __name__ == "__main__":
    asyncio.run(main())
