import os, httpx, asyncio
from dotenv import load_dotenv
from pathlib import Path
load_dotenv(Path(__file__).parent.parent / ".env")
KEY = os.getenv("MOLIT_API_KEY", "")

URLS = [
    "https://apis.data.go.kr/1613000/AptBasisInfoService/getAphusBassInfo1",
    "https://apis.data.go.kr/1613000/AptBasisInfoService/getAphusBassInfo",
    "https://apis.data.go.kr/1613000/AptHouseSaleService/getAptHouseSaleInfoList",
    "https://apis.data.go.kr/1613000/AptListInfoService/getAptListInfo",
    "https://apis.data.go.kr/1613000/AptBasisInfoService1/getAptList",
    "https://apis.data.go.kr/1613000/RTMSDataSvcAptTradeDev/getAphusBassInfo",
]

async def main():
    async with httpx.AsyncClient(timeout=10) as c:
        for url in URLS:
            try:
                r = await c.get(url, params={"serviceKey": KEY, "bjdCode": "11680", "numOfRows": 1})
                svc = url.split("/")[-1]
                print(f"{svc}: {r.status_code} | {r.text[:120]}")
            except Exception as e:
                svc = url.split("/")[-1]
                print(f"{svc}: ERROR {e}")

asyncio.run(main())
