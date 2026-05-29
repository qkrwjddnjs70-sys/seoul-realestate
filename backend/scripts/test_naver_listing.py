"""네이버 부동산 비공식 API PoC v2"""
import httpx, json

UA = "Mozilla/5.0 (iPhone; CPU iPhone OS 14_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.0 Mobile/15E148 Safari/604.1"
HEADERS = {"User-Agent": UA, "Referer": "https://m.land.naver.com/"}

# 신길우성2차 (37.4982, 126.9126) — 넓은 bbox
r = httpx.get("https://m.land.naver.com/cluster/ajax/complexList",
    headers=HEADERS, params={
        "view": "atcl", "cortarNo": "1156013200",
        "rletTpCd": "APT", "tradTpCd": "A1",
        "z": "16", "lat": "37.4982", "lon": "126.9126",
        "btm": "37.4920", "lft": "126.9020",
        "top": "37.5050", "rgt": "126.9230",
    }, timeout=15)
data = r.json()
items = data.get("result") if isinstance(data, dict) else data
print(f"단지 {len(items)}개:")
target = None
for c in items:
    nm = c.get("hscpNm", "")
    print(f"  hscpNo={c.get('hscpNo')} {nm} deal={c.get('dealCnt')}")
    if "우성2" in nm:
        target = c

if not target and items:
    print("\n신길우성2차 매칭 실패 — 첫 단지로 매물 테스트")
    target = items[0]

if target:
    print(f"\n=== 매물 리스트 (hscpNo={target['hscpNo']}, {target['hscpNm']}) ===")
    r2 = httpx.get("https://m.land.naver.com/complex/getComplexArticleList",
        headers=HEADERS, params={
            "hscpNo": target["hscpNo"],
            "tradeType": "A1", "order": "date", "page": 1,
        }, timeout=15)
    print(f"status={r2.status_code}")
    print(r2.text[:1500])
