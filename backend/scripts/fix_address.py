import sqlite3, os, re

SEOUL_DISTRICTS = {
    "11110": "종로구", "11140": "중구",    "11170": "용산구",
    "11200": "성동구", "11215": "광진구",  "11230": "동대문구",
    "11260": "중랑구", "11290": "성북구",  "11305": "강북구",
    "11320": "도봉구", "11350": "노원구",  "11380": "은평구",
    "11410": "서대문구","11440": "마포구", "11470": "양천구",
    "11500": "강서구", "11530": "구로구",  "11545": "금천구",
    "11560": "영등포구","11590": "동작구", "11620": "관악구",
    "11650": "서초구", "11680": "강남구",  "11710": "송파구",
    "11740": "강동구",
}

db_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "apartments.db")
conn = sqlite3.connect(db_path)

# 1) "서울시 서울 구이름" → "서울시 구이름"
conn.execute("UPDATE apartments SET address = REPLACE(address, '서울시 서울 ', '서울시 ')")

# 2) lawd_cd로 구 이름 보정 (구 이름 없는 주소)
rows = conn.execute("SELECT id, address, lawd_cd FROM apartments WHERE address LIKE '서울시  %'").fetchall()
print(f"구 이름 누락 레코드: {len(rows)}개 보정 중...")
for row_id, addr, lawd_cd in rows:
    gu = SEOUL_DISTRICTS.get(lawd_cd, "")
    if gu:
        new_addr = addr.replace("서울시  ", f"서울시 {gu} ", 1)
        conn.execute("UPDATE apartments SET address = ? WHERE id = ?", (new_addr, row_id))

conn.commit()

# 결과 확인
total = conn.execute("SELECT COUNT(*) FROM apartments WHERE geocoded=1").fetchone()[0]
samples = conn.execute("SELECT name, address FROM apartments ORDER BY last_price DESC LIMIT 5").fetchall()
print(f"\n총 {total:,}개 아파트")
print("상위 5개:")
for name, addr in samples:
    print(f"  {name} | {addr}")
conn.close()
