# -*- coding: utf-8 -*-
"""building_age.json에 종합 재개발 후보점수 추가 (API 재호출 없이 재계산).
점수(0~100) = 노후도(50%) + 평균연식(20%) + 용도적합도(15%) + 미지정가산(15%)
  - 용도적합도: 재건축(아파트밀집)=공동주택비중 / 재개발=저층(단독·근린·공장)비중
등급: S≥80, A 70+, B 60+, C 50+, D<50
"""
import sys, json
sys.stdout.reconfigure(encoding="utf-8")
from pathlib import Path

ROOT = Path(__file__).parent.parent
fp = ROOT / "data" / "building_age.json"
data = json.loads(fp.read_text(encoding="utf-8"))

def grade(s):
    return "S" if s >= 80 else "A" if s >= 70 else "B" if s >= 60 else "C" if s >= 50 else "D"

for d in data["dongs"]:
    tot = d.get("sampled") or 1
    p = d.get("purpose", {})
    apt = p.get("공동주택", 0) / tot
    lowres = (p.get("단독주택", 0) + p.get("근린생활", 0) + p.get("공장", 0)) / tot
    age_n = min(d.get("avg_age", 0) / 45, 1) * 100
    use_fit = (apt if d.get("kind") == "재건축" else lowres) * 100
    # 사업성·입지 = 저층여력 + 역세권 + 평지 (모두 0~100, 높을수록 좋음)
    low_s = d.get("lowrise", 0)                                  # 저층비율(용적률 여력)
    far = d.get("est_far")
    if far is not None and far > 250:
        low_s *= max(0.5, 1 - (far - 250) / 500)                 # 이미 밀집이면 여력 감소
    dist = d.get("station_dist")
    stn_s = max(0, min(1, (1000 - dist) / 700)) * 100 if dist is not None else 50  # 역 300m=만점,1km=0
    slope = d.get("avg_slope")
    if slope is not None:
        slp_s = max(0, min(1, (20 - slope) / 15)) * 100          # 평지(≤5도) 만점, 20도+ 0
        biz_room = 0.45 * low_s + 0.35 * stn_s + 0.20 * slp_s
    else:
        biz_room = 0.55 * low_s + 0.45 * stn_s                   # 경사 없으면 둘로 배분
    d["biz_room"] = round(biz_room, 1)
    base = 0.42 * d.get("nohu", 0) + 0.20 * biz_room + 0.13 * age_n + 0.10 * use_fit
    bonus = 15 if not d.get("already_zone") else 5  # 미지정(예측가치)에 가산
    score = round(min(base + bonus, 100), 1)
    d["score"] = score
    d["grade"] = grade(score)
    # 유형 분류 (사용자가 주거 재개발 vs 도심상업 구분)
    single = p.get("단독주택", 0) / tot
    fac = p.get("공장", 0) / tot
    biz = (p.get("업무", 0) + p.get("근린생활", 0)) / tot
    if apt > 0.5:
        d["subtype"] = "재건축(아파트)"
    elif fac > 0.2:
        d["subtype"] = "준공업재개발"
    elif single > 0.3:
        d["subtype"] = "주거재개발"
    elif biz > 0.55:
        d["subtype"] = "도심상업"
    else:
        d["subtype"] = "혼합주거"

# ===== 비고(note): 개발 제약 / 실제 진행여부 (웹검증 기반 큐레이션) =====
# flag: "제약"(개발가능성 낮음·이유) / "진행중"(우리DB 누락이나 실제 사업중) / "주의"
NOTES = {
    # 🚫 개발 제약 — 점수 높아도 실현 어려움
    ("서대문구", "봉원동"):   ("제약", "안산 자연경관지구·고도제한 + 봉원사·연세대 인접 → 대규모 개발 어려움. 정비사업 이력 없음"),
    ("종로구", "팔판동"):     ("제약", "북촌 한옥마을 보존·특별관리지역. 재개발 아닌 보존 대상 → 개발 사실상 불가"),
    ("용산구", "용산동4가"):  ("주의", "용산공원(미군기지)·전쟁기념관 인접, 표본 22채로 소규모. 정비사업 없음(인근 용산동2가가 신통기획)"),
    # ✅ 실제 정비사업 진행중 — 우리DB 누락이라 '미지정'으로 잘못 뜸
    ("용산구", "남영동"):     ("진행중", "남영동 업무지구 제2구역 도시정비형 재개발 — 2026.6 통합심의 통과, 시공사(삼성물산) 선정"),
    ("용산구", "주성동"):     ("진행중", "한남5재정비촉진구역(한남뉴타운) 일부 — 사업시행인가 완료(2025), 시공 DL이앤씨"),
    ("용산구", "한강로3가"):  ("진행중", "정비창전면1구역 등 다수 정비사업 진행(2026.1 시공계약). 구역별 단계 편차 큼"),
    ("서대문구", "충정로3가"): ("진행중", "충정로1구역 공공재개발(SH) — 정비구역 지정 완료(2024.12), 시행자 지정"),
    ("서대문구", "옥천동"):   ("진행중", "옥천동 123-2 신통기획 재개발 후보지 선정(2026.2)·구역지정 절차 진입"),
    ("성북구", "삼선동1가"):  ("진행중", "삼선3구역 신통기획 후보지 선정(2025.6) — 초기 단계(구역지정 전), 역사문화환경 검토 병행"),
    ("성동구", "하왕십리동"): ("주의", "하왕십리9·10구역 신통기획 재도전했으나 9구역 반대율 25% 초과로 난항. 왕십리 지구단위계획 별도"),
}
for d in data["dongs"]:
    key = (d["gu"], d["dong"])
    if key in NOTES:
        d["note_flag"], d["note"] = NOTES[key]
    elif d.get("subtype") == "도심상업":
        d["note_flag"], d["note"] = "주의", "도심 상업지 — 주거 재개발과 성격 다름(상업·업무 위주)"
    elif (d.get("buildings") or 0) < 30:
        d["note_flag"], d["note"] = "주의", "표본 적음(소규모 동) — 노후도 신뢰도 낮음"
    else:
        d["note_flag"], d["note"] = "", ""

fp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

# 미지정 주거형 후보 TOP 15 (도심상업 제외)
cand = [d for d in data["dongs"] if not d["already_zone"] and d["subtype"] != "도심상업"]
print("=== 미지정 '주거·준공업' 재개발 후보 TOP 15 (도심상업 제외) ===")
for d in sorted(cand, key=lambda a: -a["score"])[:15]:
    print(f"  [{d['grade']}] {d['score']:>5}  {d['gu']:<7}{d['dong']:<9} 노후{d['nohu']:>5}% {d['subtype']:<10} 건물{d['buildings']}")
print(f"\n총 {len(data['dongs'])}개 동 점수화 완료")
