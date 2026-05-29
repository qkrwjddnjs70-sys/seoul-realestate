"""
정비사업 정보몽땅(cleanup.seoul.go.kr) → DB 재건축 단계 매칭 (최우선 데이터소스)
- data/cleanup_seoul.xls (1112개 사업장: 자치구·사업구분·사업장명·대표지번·진행단계)
- 1순위: 대표지번(동+번지) 정확 일치 → 거의 100% 신뢰
- 2순위: 사업장명에서 단지명 추출 후 이름 매칭 (같은 구)
- redev_manual=1 은 보존, 그 외는 정보몽땅 값으로 덮어씀(최신·정확)
"""
import sys, re, sqlite3
sys.stdout.reconfigure(encoding='utf-8')
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).parent.parent
DB = ROOT / "data" / "apartments.db"
XLS = ROOT / "data" / "cleanup_seoul.xls"

GU_CODE = {
    "종로구":"11110","중구":"11140","용산구":"11170","성동구":"11200","광진구":"11215",
    "동대문구":"11230","중랑구":"11260","성북구":"11290","강북구":"11305","도봉구":"11320",
    "노원구":"11350","은평구":"11380","서대문구":"11410","마포구":"11440","양천구":"11470",
    "강서구":"11500","구로구":"11530","금천구":"11545","영등포구":"11560","동작구":"11590",
    "관악구":"11620","서초구":"11650","강남구":"11680","송파구":"11710","강동구":"11740",
}

# cleanup 단계 → 우리 단계 (우선순위 동반)
STAGE_MAP = {
    "안전진단": ("안전진단", 1),
    "정비계획 수립": ("정비구역지정", 2),
    "정비구역지정": ("정비구역지정", 2),
    "지구단위계획수립/건축심의/교통심의": ("정비구역지정", 2),
    "추진위구성": ("추진위원회승인", 3),
    "추진위원회승인": ("추진위원회승인", 3),
    "조합규약작성": ("추진위원회승인", 3),
    "조합원 모집신고": ("추진위원회승인", 3),
    "조합창립총회": ("조합설립인가", 4),
    "조합설립인가": ("조합설립인가", 4),
    "사업계획승인": ("사업시행인가", 6),
    "사업시행인가": ("사업시행인가", 6),
    "관리처분인가": ("관리처분인가", 7),
    "이주": ("이주철거", 8),
    "철거": ("이주철거", 8),
    "철거 및 착공": ("착공", 9),
    "착공": ("착공", 9),
    "준공인가": ("준공", 10),
    "이전고시": ("준공", 10),
}
# 죽은/완료 단계 — 매칭 제외
DEAD = {"조합해산", "조합청산", "청산 및 조합해산"}


def parse_jibun(s: str):
    """'신길동 4656' / '문래동3가 77-2' → ('신길동','4656') / ('문래동3가','77-2')"""
    if not isinstance(s, str):
        return (None, None)
    m = re.match(r"([가-힣0-9]+동(?:\d+가)?)\s+([\d\-]+)", s.strip())
    if m:
        return (m.group(1), m.group(2))
    return (None, None)


def addr_jibun(addr: str):
    """DB 주소에서 동+번지 추출 (마지막 '동 번지' 패턴)"""
    if not addr:
        return (None, None)
    m = re.search(r"([가-힣0-9]+동(?:\d+가)?)\s+([\d\-]+)\s*$", addr.strip())
    if m:
        return (m.group(1), m.group(2))
    return (None, None)


def name_core(s: str) -> str:
    """사업장명 → 단지 core. '신길우성3차아파트 재건축정비사업' → '신길우성3차'"""
    s = s or ""
    # 사업/조합 등 꼬리 제거
    s = re.sub(r"\s*(주택)?(재건축|재개발|소규모재건축|가로주택)?\s*정비사업.*$", "", s)
    s = re.sub(r"\s*(주택재건축|재건축|재개발).*$", "", s)
    s = re.sub(r"아파트$", "", s)
    return s.replace(" ", "")


def main():
    df = pd.read_excel(XLS, header=1)
    df.columns = ["no","gu","type","name","jibun","stage","op_type","op_stage","c1","c2","c3"]

    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    apts = [dict(r) for r in conn.execute(
        "SELECT id, name, display_name, dong, lawd_cd, address, built_year, redev_manual "
        "FROM apartments WHERE geocoded=1 AND last_price>0"
    ).fetchall()]

    # DB 인덱스: (lawd, dong, bunji) → apt, 그리고 (lawd, namecore) → apt
    by_jibun = {}
    by_name = {}
    for a in apts:
        d, b = addr_jibun(a["address"])
        if d and b:
            by_jibun.setdefault((a["lawd_cd"], d, b), []).append(a)
        nc = name_core(a["display_name"] or a["name"]).lower()
        if len(nc) >= 2:
            by_name.setdefault((a["lawd_cd"], nc), []).append(a)

    updates = {}   # apt_id → (stage, detail, prio)
    n_jibun = n_name = 0
    for _, row in df.iterrows():
        gu = row["gu"]; stage_raw = row["stage"]; nm = row["name"]
        if gu not in GU_CODE or not isinstance(stage_raw, str):
            continue
        if stage_raw in DEAD:
            continue
        mapped = STAGE_MAP.get(stage_raw.strip())
        if not mapped:
            continue
        stage, prio = mapped
        lawd = GU_CODE[gu]
        proj_name = re.sub(r"^\d+\.\s*", "", str(nm)).strip()  # 앞 번호 제거
        detail_base = f"{stage} / {proj_name[:30]} (정비사업 정보몽땅)"

        matched = []
        # 1순위: 지번
        jd, jb = parse_jibun(row["jibun"])
        if jd and jb and (lawd, jd, jb) in by_jibun:
            matched = by_jibun[(lawd, jd, jb)]
            tag = "지번"
        else:
            # 2순위: 이름 (재건축류만 — 재개발은 구역이라 단지 특정 어려움)
            if "재건축" in str(row["type"]) or "가로주택" in str(row["type"]):
                nc = name_core(proj_name).lower()
                if len(nc) >= 3 and (lawd, nc) in by_name:
                    matched = by_name[(lawd, nc)]
                    tag = "이름"
        if not matched:
            continue
        for a in matched:
            if a["redev_manual"]:
                continue
            prev = updates.get(a["id"])
            if not prev or prio > prev[2]:
                updates[a["id"]] = (stage, detail_base, prio)
        if matched:
            if tag == "지번": n_jibun += 1
            else: n_name += 1

    # 기존 '공식/정보몽땅' 매칭만 초기화 (AI 추정·수동 보존) 후 정보몽땅 적용
    conn.execute(
        "UPDATE apartments SET redev_stage=NULL, redev_detail=NULL, redev_updated=NULL "
        "WHERE (redev_manual IS NULL OR redev_manual=0) "
        "AND (redev_detail LIKE '%서울시 공식%' OR redev_detail LIKE '%정보몽땅%')"
    )
    for aid, (stage, detail, prio) in updates.items():
        conn.execute(
            "UPDATE apartments SET redev_stage=?, redev_detail=?, redev_updated=? WHERE id=?",
            (stage, detail, "2026-05-29", aid),
        )
    conn.commit()

    total = conn.execute("SELECT COUNT(*) FROM apartments WHERE geocoded=1 AND last_price>0").fetchone()[0]
    withs = conn.execute("SELECT COUNT(*) FROM apartments WHERE redev_stage IS NOT NULL AND redev_stage!=''").fetchone()[0]
    conn.close()
    print(f"매칭(지번 {n_jibun} + 이름 {n_name}) → 단지 {len(updates)}개 갱신")
    print(f"전체 단계 보유: {withs}/{total} ({withs*100//total}%)")


if __name__ == "__main__":
    main()
