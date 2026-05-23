import os, sys, requests, xml.etree.ElementTree as ET
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env"))

DECODING_KEY = "pmaK5RXorxc32YSBugs7WNx7uhkjCv7zSb+66f+8BXQAxEU5ldWczBp7Y3nuqI7JXkghSersUYKDr/0x2IoRnA=="
URL = "https://apis.data.go.kr/1613000/RTMSDataSvcAptTradeDev/getRTMSDataSvcAptTradeDev"

r = requests.get(URL, params={
    "serviceKey": DECODING_KEY,
    "LAWD_CD": "11680", "DEAL_YMD": "202503", "numOfRows": "3", "pageNo": "1"
})

root = ET.fromstring(r.text)
items = root.findall(".//item")
print(f"건수: {len(items)}")
print("\n=== 필드 목록 (첫 번째 item) ===")
for child in items[0]:
    print(f"  {child.tag}: {child.text}")
