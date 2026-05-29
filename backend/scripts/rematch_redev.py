"""
서울시 정비사업 추진경과 → 우리 DB 고recall 재매칭 (v2)
- 캐시된 30k 이벤트(seoul_redev_cache.json) 사용
- BIZ_NO별: 가장 진행된 단계 + 제목에서 단지명 추출
- 단지명 직접 매칭 (같은 구 + 정규화 core 일치/포함/유사도)
- redev_manual=1 단지는 건드리지 않음
- 기존 AI 추정값(서울시 공식 아님)은 공식 매칭으로 덮어씀
"""
import sys, json, re, sqlite3
sys.stdout.reconfigure(encoding='utf-8')
from pathlib import Path
from collections import defaultdict
from difflib import SequenceMatcher

ROOT = Path(__file__).parent.parent
DB = ROOT / "data" / "apartments.db"
CACHE = ROOT / "data" / "seoul_redev_cache.json"

# 단계 우선순위 (높을수록 진행됨)
STAGE_ORDER = {
    "안전진단": 1, "정비구역지정": 2, "정비계획": 2,
    "추진위원회승인": 3, "추진위원회구성승인": 3,
    "조합설립인가": 4, "정비사업전문관리업자선정": 3,
    "시공자선정": 5, "시공사선정": 5,
    "사업시행인가": 6, "사업시행계획인가": 6,
    "관리처분계획인가": 7, "관리처분인가": 7,
    "이주": 8, "철거": 8, "착공": 9, "준공": 10,
}

def normalize_stage(se_nm: str):
    if not se_nm:
        return ("", 0)
    for kw, prio in STAGE_ORDER.items():
        if kw in se_nm:
            if "조합설립" in kw: return ("조합설립인가", prio)
            if "시공" in kw: return ("시공사선정", prio)
            if "사업시행" in kw: return ("사업시행인가", prio)
            if "관리처분" in kw: return ("관리처분인가", prio)
            if "이주" in kw or "철거" in kw: return ("이주철거", prio)
            if "추진위" in kw: return ("추진위원회승인", prio)
            if "전문관리업자" in kw: return ("정비구역지정", 2)  # 약한 신호
            return (kw, prio)
    return (se_nm, 0)

# 단지명 추출 패턴
APT_PAT = re.compile(r"[가-힣A-Za-z0-9]+?(?:아파트|주공|\d+차|연립|맨션|맨숀|빌라|타운)")

# 흔한 브랜드·동 이름 — 단독이면 같은 구 전체에 번지므로 '정확히 일치'만 허용
GENERIC = {
    "현대", "삼성", "대우", "우성", "한신", "동부", "쌍용", "두산", "대림",
    "경남", "삼호", "동아", "한양", "롯데", "효성", "건영", "럭키", "미성",
    "한강", "중곡", "보광", "진주", "목화", "광장", "공작", "대교", "삼익",
    "신동아", "코오롱", "한일", "신성", "동신", "성원", "라이프", "벽산",
    "월드", "주공", "시영", "시범", "삼환", "극동", "우방", "청구", "신안",
}

_NUMERIC_FRAG = re.compile(r"^\d+(단지|차|동|지구|구역)?$")

def clean_apt_name(nm: str) -> str:
    """추출된 단지명 → 매칭용 core. 차 숫자는 보존"""
    nm = nm.replace(" ", "")
    nm = re.sub(r"(아파트|연립|맨션|맨숀|빌라|타운)$", "", nm)
    return nm

def is_junk(nm: str) -> bool:
    """매칭에 쓰면 안 되는 조각: 숫자단지·단독 단지/차 등"""
    if _NUMERIC_FRAG.match(nm):
        return True
    if nm in {"단지", "차", "동", "지구", "구역", "아파트", "주공"}:
        return True
    return False

def norm_db(nm: str) -> str:
    return re.sub(r"\s+", "", (nm or "")).lower()

def stem(nm: str) -> str:
    """차수·숫자 꼬리 제거: 신길우성2차→신길우성, 삼익그린2차→삼익그린, 고덕주공9→고덕주공"""
    s = re.sub(r"\d+\s*차?$", "", nm or "")
    return s

# 말기 단계 — 신축 단지에 붙으면 거의 오탐 (이미 다 지어진 건물)
LATE_STAGES = {"이주철거", "착공", "준공", "관리처분인가"}

# 같은 stem으로 여러 별개 프로젝트가 존재 → stem 매칭 시 번짐. 정확 일치만 허용
STEM_GENERIC = {
    "신반포", "반포", "잠실", "한신", "한양", "우성", "현대", "삼성",
    "미성", "진주", "시영", "주공", "럭키", "대우", "동아", "신동아",
}


def main():
    rows = json.loads(CACHE.read_text(encoding="utf-8"))

    # BIZ_NO별 집약
    biz = defaultdict(lambda: {
        "lawd": "", "best_prio": 0, "best_stage": "", "best_date": "",
        "names": set(), "titles": [],
    })
    for r in rows:
        bn = r.get("BIZ_NO") or ""
        if "-" not in bn:
            continue
        b = biz[bn]
        b["lawd"] = bn.split("-")[0][:5]
        stage, prio = normalize_stage(r.get("SE_NM") or "")
        day = r.get("DAY") or ""
        if prio > b["best_prio"] or (prio == b["best_prio"] and day > b["best_date"]):
            b["best_prio"] = prio; b["best_stage"] = stage; b["best_date"] = day
        for fld in ("TTL", "DTL_CN"):
            t = r.get(fld) or ""
            if t:
                b["titles"].append(t)
                for m in APT_PAT.findall(t):
                    cn = clean_apt_name(m)
                    if len(cn) >= 2 and not is_junk(cn):
                        b["names"].add(cn)

    # 구별 단지명 인덱스: name_core → [(biz_no, b)]
    by_lawd = defaultdict(list)
    for bn, b in biz.items():
        if b["best_prio"] == 0 or not b["names"]:
            continue
        by_lawd[b["lawd"]].append((bn, b))

    # DB 매칭
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    apts = conn.execute(
        "SELECT id, name, display_name, dong, lawd_cd, built_year "
        "FROM apartments WHERE geocoded=1 AND last_price>0 "
        "AND (redev_manual IS NULL OR redev_manual=0)"
    ).fetchall()

    updates = []
    for a in apts:
        lawd = a["lawd_cd"]
        cands = by_lawd.get(lawd, [])
        if not cands:
            continue
        apt_name = norm_db(a["display_name"] or a["name"])
        # core: 끝의 '아파트' 제거
        apt_core = re.sub(r"(아파트)$", "", apt_name)
        apt_stem = stem(apt_core)
        best = None; best_score = 0.0
        for bn, b in cands:
            for ext in b["names"]:
                e = ext.lower()
                if len(e) < 2:
                    continue
                is_generic = ext in GENERIC
                e_stem = stem(e)
                score = 0.0
                if e == apt_core or e == apt_name:
                    score = 100                       # 정확 일치
                elif is_generic:
                    continue                          # generic은 정확 일치만
                elif (e_stem == apt_stem and len(e_stem) >= 3
                      and e_stem not in GENERIC and e_stem not in STEM_GENERIC):
                    score = 92                        # 차수 시리즈 (신길우성1~5차)
                else:
                    shorter = min(len(e), len(apt_core))
                    if shorter >= 4 and (apt_core.startswith(e) or e.startswith(apt_core)):
                        score = 80 + shorter           # 접두 일치
                if score > best_score:
                    best_score = score; best = (bn, b, ext)
        if best and best_score >= 80:
            bn, b, ext = best
            stage = b["best_stage"]
            date = b["best_date"]
            # 신축 단지에 말기단계는 오탐 → 건너뜀
            if stage in LATE_STAGES and (a["built_year"] or 0) >= 2008:
                continue
            dfmt = f"{date[:4]}.{date[4:6]}" if len(date) >= 6 else date
            # 정비구역명: 가장 긴 title 첫 토큰
            zone = ext
            detail = f"{stage}"
            if dfmt: detail += f" / {dfmt}"
            detail += f" / {zone} (서울시 공식)"
            updates.append((a["id"], stage, detail, best_score))

    # 적용
    n = 0
    for aid, stage, detail, score in updates:
        conn.execute(
            "UPDATE apartments SET redev_stage=?, redev_detail=?, redev_updated=? "
            "WHERE id=? AND (redev_manual IS NULL OR redev_manual=0)",
            (stage, detail, "2026-05-29", aid),
        )
        n += 1
    conn.commit()

    # 통계
    total = conn.execute("SELECT COUNT(*) FROM apartments WHERE geocoded=1 AND last_price>0").fetchone()[0]
    withs = conn.execute("SELECT COUNT(*) FROM apartments WHERE redev_stage IS NOT NULL AND redev_stage!=''").fetchone()[0]
    conn.close()
    print(f"신규/갱신 매칭: {n}개")
    print(f"전체 단계 보유: {withs}/{total} ({withs*100//total}%)")


if __name__ == "__main__":
    main()
