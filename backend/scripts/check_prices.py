import sqlite3
conn = sqlite3.connect('data/apartments.db')

print('=== 강남구 84m2 전후 아파트 매매가 ===')
rows = conn.execute("""
    SELECT name, last_price, area_m2, last_deal_date
    FROM apartments
    WHERE lawd_cd='11680' AND area_m2 BETWEEN 80 AND 90
    ORDER BY last_price DESC LIMIT 15
""").fetchall()
for r in rows:
    print(f'{r[0][:20]:20s} {r[1]:7,}만 ({r[1]/10000:.1f}억)  {r[2]}m2  {r[3]}')

print()
print('=== 서초구 84m2 전후 아파트 매매가 ===')
rows2 = conn.execute("""
    SELECT name, last_price, area_m2, last_deal_date
    FROM apartments
    WHERE lawd_cd='11650' AND area_m2 BETWEEN 80 AND 90
    ORDER BY last_price DESC LIMIT 10
""").fetchall()
for r in rows2:
    print(f'{r[0][:20]:20s} {r[1]:7,}만 ({r[1]/10000:.1f}억)  {r[2]}m2  {r[3]}')

conn.close()
