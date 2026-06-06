# -*- coding: utf-8 -*-
"""주요 정비사업 구역 건립예정 세대수 큐레이션 (공개자료 검증).
units 필드만 보강한다. stage(단계)는 정보몽땅 원본을 신뢰해 건드리지 않음.
사용:  python enrich_major_units.py          # 드라이런(매칭 리포트)
       python enrich_major_units.py --write   # 실제 반영
"""
import sys, json
sys.stdout.reconfigure(encoding="utf-8")
from pathlib import Path

ROOT = Path(__file__).parent.parent
FP = ROOT / "data" / "redev_points.json"
WRITE = "--write" in sys.argv

# (구, [키워드들], 세대수, [동필터(선택)])  — 키워드는 name+dong+jibun 에 부분일치
CURATED = [
    # 용산 한남뉴타운
    ("용산구", ["한남2"], 1537, None),
    ("용산구", ["한남4"], 2331, None),
    # 동작 노량진뉴타운
    ("동작구", ["노량진1"], 2992, None),
    ("동작구", ["노량진2"], 421, None),
    ("동작구", ["노량진3"], 1272, None),
    ("동작구", ["노량진4"], 860, None),
    ("동작구", ["노량진5"], 727, None),
    ("동작구", ["노량진6"], 1499, None),
    ("동작구", ["노량진7"], 576, None),
    ("동작구", ["노량진8"], 1007, None),
    # 동작 흑석뉴타운
    ("동작구", ["흑석11"], 1511, None),
    ("동작구", ["흑석2"], 1012, None),
    # 강남 은마
    ("강남구", ["은마"], 5893, None),
    # 동대문 이문·휘경
    ("동대문구", ["이문1"], 3069, None),
    ("동대문구", ["이문3"], 4321, None),
    ("동대문구", ["이문4"], 3628, None),
    ("동대문구", ["휘경3"], 1800, None),
    # 성북 장위뉴타운 (장위4=완공 자이레디언트는 데이터 없음)
    ("성북구", ["장위제6", "장위6"], 1637, None),
    ("성북구", ["장위10"], 2004, None),
    ("성북구", ["장위14"], 2469, None),
    # 노원 상계주공 (상계주공6은 데이터 미수록)
    ("노원구", ["상계주공5"], 996, None),
    # 영등포 신길뉴타운
    ("영등포구", ["신길2"], 1332, None),
    ("영등포구", ["신길13"], 586, None),
    # 영등포 여의도 재건축
    ("영등포구", ["시범"], 2473, "여의도"),
    ("영등포구", ["한양"], 992, "여의도"),
    ("영등포구", ["대교"], 912, "여의도"),
    ("영등포구", ["삼부"], 1735, "여의도"),
    ("영등포구", ["광장아파트28"], 1314, "여의도"),
    # 송파 잠실
    ("송파구", ["잠실5단지", "잠실주공5"], 6491, None),
    ("송파구", ["잠실우성아파트"], 2716, None),
]

# 정보몽땅 데이터에 없는 대형 구역 → 신규 포인트로 추가 (키워드 지오코딩 좌표)
ADD_NEW = [
    # name, type, stage, gu, dong, jibun, lat, lng, units
    ("한남3재정비촉진구역 주택재개발정비사업(디에이치 한남)", "재개발", "관리처분·이주", "용산구", "한남동", "한남동 686", 37.5281678754691, 126.99983708973, 5970),
    ("한남5재정비촉진구역 주택재개발정비사업", "재개발", "사업시행인가", "용산구", "동빙고동", "동빙고동 60", 37.52868118703339, 126.99217007148006, 2592),
    ("흑석9재정비촉진구역 주택재개발정비사업", "재개발", "착공", "동작구", "흑석동", "흑석동 90", 37.504676405704, 126.965600515903, 1540),
]


def norm(s):
    return (s or "").replace(" ", "")


def main():
    zones = json.loads(FP.read_text(encoding="utf-8"))
    for z in zones:
        z.setdefault("units", None)

    total_set = 0
    report = []
    for gu, keys, units, dong in CURATED:
        matched = []
        for z in zones:
            if z.get("gu") != gu:
                continue
            if dong and dong not in norm(z.get("dong", "")):
                continue
            hay = norm(z.get("name", "") + z.get("dong", "") + z.get("jibun", ""))
            if any(norm(k) in hay for k in keys):
                matched.append(z)
        tag = "·".join(keys)
        if not matched:
            report.append(f"  ❌ [{gu}] {tag} ({units}세대) → 매칭 0건")
            continue
        report.append(f"  ✅ [{gu}] {tag} → {units}세대 | 매칭 {len(matched)}건")
        for m in matched:
            report.append(f"        - {m.get('name')} | {m.get('dong')} {m.get('jibun')} | 단계:{m.get('stage')}")
            if WRITE:
                m["units"] = units
                total_set += 1

    # 신규 포인트 추가 (중복 방지: 같은 gu+이름 핵심 키워드 이미 있으면 skip)
    for nm, typ, stage, gu, dong, jibun, lat, lng, units in ADD_NEW:
        core = norm(nm)[:6]
        exists = any(z.get("gu") == gu and core in norm(z.get("name", "")) for z in zones)
        if exists:
            report.append(f"  ⏭  [신규] {nm} → 이미 존재, skip")
            continue
        report.append(f"  ➕ [신규추가] {nm} | {gu} {jibun} | {units}세대 | {stage}")
        if WRITE:
            zones.append({"name": nm, "type": typ, "stage": stage, "gu": gu,
                          "dong": dong, "jibun": jibun, "lat": lat, "lng": lng, "units": units})
            total_set += 1

    print("\n".join(report))
    if WRITE:
        FP.write_text(json.dumps(zones, ensure_ascii=False), encoding="utf-8")
        have = len([z for z in zones if z.get("units")])
        print(f"\n반영 완료: 이번에 {total_set}개 zone에 세대수 기록. 전체 units 보유 {have}개 / {len(zones)}")
    else:
        print("\n[드라이런] 실제 반영하려면 --write 옵션을 붙이세요.")


if __name__ == "__main__":
    main()
