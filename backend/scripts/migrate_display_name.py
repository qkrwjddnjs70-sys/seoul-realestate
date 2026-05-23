"""
display_name 컬럼 추가 + 모든 단지에 대해 풀네임(예: 신길우성1차) 사전 계산 저장.
이후 단지명 검색은 이 컬럼을 기준으로 한다.
"""
import sys, sqlite3
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from routers.properties import _display_name

DB_PATH = Path(__file__).parent.parent / "data" / "apartments.db"
conn = sqlite3.connect(DB_PATH)
cur = conn.cursor()

cols = [r[1] for r in cur.execute("PRAGMA table_info(apartments)")]
if "display_name" not in cols:
    cur.execute("ALTER TABLE apartments ADD COLUMN display_name TEXT")
    conn.commit()
    print("display_name 컬럼 추가")
else:
    print("display_name 컬럼 이미 존재")

rows = cur.execute("SELECT id, name, dong FROM apartments").fetchall()
for rid, name, dong in rows:
    dn = _display_name(name or "", dong or "")
    cur.execute("UPDATE apartments SET display_name=? WHERE id=?", (dn, rid))
conn.commit()

# 인덱스 추가 (검색 속도)
cur.execute("CREATE INDEX IF NOT EXISTS idx_apt_display_name ON apartments(display_name)")
conn.commit()

print(f"{len(rows)}개 단지 display_name 업데이트")
conn.close()
