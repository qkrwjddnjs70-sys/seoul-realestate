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
    base = 0.50 * d.get("nohu", 0) + 0.20 * age_n + 0.15 * use_fit
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

fp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

# 미지정 주거형 후보 TOP 15 (도심상업 제외)
cand = [d for d in data["dongs"] if not d["already_zone"] and d["subtype"] != "도심상업"]
print("=== 미지정 '주거·준공업' 재개발 후보 TOP 15 (도심상업 제외) ===")
for d in sorted(cand, key=lambda a: -a["score"])[:15]:
    print(f"  [{d['grade']}] {d['score']:>5}  {d['gu']:<7}{d['dong']:<9} 노후{d['nohu']:>5}% {d['subtype']:<10} 건물{d['buildings']}")
print(f"\n총 {len(data['dongs'])}개 동 점수화 완료")
