import os
from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from routers import properties
from routers import transactions
from routers import hojae
from routers import schools
from routers import compare

app = FastAPI(title="서울 부동산 API", version="2.0.0")

# CORS — 로컬 + Vercel/배포 도메인 + env로 추가 허용
_extra = [o.strip() for o in os.getenv("ALLOW_ORIGINS", "").split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"https://.*\.vercel\.app",
    allow_origins=["http://localhost:5173", "http://localhost:3000", *_extra],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(properties.router, prefix="/api/properties", tags=["properties"])
app.include_router(transactions.router, prefix="/api/properties", tags=["transactions"])
app.include_router(hojae.router,     prefix="/api/hojae",      tags=["hojae"])
app.include_router(schools.router,   prefix="/api/schools",    tags=["schools"])
app.include_router(compare.router,   prefix="/api/compare",    tags=["compare"])


@app.get("/")
def root():
    return {"status": "ok", "service": "서울 부동산 API v2"}
