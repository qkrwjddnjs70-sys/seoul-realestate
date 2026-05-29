"""
재건축 데이터 정리: 정보몽땅(권위) = redev_stage / AI 추정 = redev_ai_stage 분리
- AI 추정값을 redev_log.txt + 현재 비공식 redev_stage 에서 redev_ai_* 로 이관
- redev_stage 에는 정보몽땅·수동만 남김
- API/UI에서 둘 비교 → 다르면 '확인 필요' 표시
"""
import sys, re, sqlite3
sys.stdout.reconfigure(encoding='utf-8')
from pathlib import Path

ROOT = Path(__file__).parent.parent
DB = ROOT / "data" / "apartments.db"
LOG = ROOT / "redev_log.txt"

# 1) 로그에서 AI 추정 파싱 (PowerShell이 cp949로 저장)
ai_from_log = {}
if LOG.exists():
    text = None
    for enc in ("cp949", "euc-kr", "utf-8"):
        try:
            text = LOG.read_text(encoding=enc)
            break
        except Exception:
            continue
    for line in (text or "").splitlines():
        m = re.search(r"id=(\d+)\s*[→\-=>]+\s*([가-힣]+)\s*\((.*)\)\s*$", line)
        if m:
            ai_from_log[int(m.group(1))] = (m.group(2), m.group(3))

conn = sqlite3.connect(DB)
conn.row_factory = sqlite3.Row
rows = [dict(r) for r in conn.execute(
    "SELECT id, redev_stage, redev_detail, redev_manual, redev_ai_stage FROM apartments "
    "WHERE redev_stage IS NOT NULL OR redev_ai_stage IS NOT NULL OR id IN ({})".format(
        ",".join(str(i) for i in ai_from_log) or "0")
).fetchall()]

moved = 0
ai_set = 0
for r in rows:
    aid = r["id"]
    detail = r["redev_detail"] or ""
    is_official = "정보몽땅" in detail
    is_manual = bool(r["redev_manual"])

    # AI 추정 출처 결정: 로그 우선, 없으면 (비공식·비수동 현재값)
    ai = ai_from_log.get(aid)
    if not ai and r["redev_stage"] and not is_official and not is_manual:
        ai = (r["redev_stage"], detail)

    if ai:
        conn.execute("UPDATE apartments SET redev_ai_stage=?, redev_ai_detail=? WHERE id=?",
                     (ai[0], ai[1], aid))
        ai_set += 1

    # redev_stage 에 AI-only 값이 들어있으면 비움 (권위 출처만 남김)
    if r["redev_stage"] and not is_official and not is_manual:
        conn.execute("UPDATE apartments SET redev_stage=NULL, redev_detail=NULL, redev_updated=NULL WHERE id=?", (aid,))
        moved += 1

conn.commit()

# 통계
auth = conn.execute("SELECT COUNT(*) FROM apartments WHERE redev_stage IS NOT NULL AND redev_stage!=''").fetchone()[0]
ai_cnt = conn.execute("SELECT COUNT(*) FROM apartments WHERE redev_ai_stage IS NOT NULL AND redev_ai_stage!=''").fetchone()[0]
# 충돌(둘 다 있고 다름)
conflict = conn.execute(
    "SELECT COUNT(*) FROM apartments WHERE redev_stage IS NOT NULL AND redev_stage!='' "
    "AND redev_ai_stage IS NOT NULL AND redev_ai_stage!='' AND redev_stage != redev_ai_stage"
).fetchone()[0]
conn.close()
print(f"로그 AI 파싱: {len(ai_from_log)}개")
print(f"AI 추정 이관: {ai_set}개 / redev_stage 비움: {moved}개")
print(f"권위(정보몽땅+수동): {auth} / AI추정 보유: {ai_cnt} / 충돌(확인필요): {conflict}")
