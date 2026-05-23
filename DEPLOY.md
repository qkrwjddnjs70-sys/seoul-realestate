# 배포 가이드 — Vercel(프론트) + Render(백엔드)

## 1. GitHub 푸시

```bash
cd seoul-realestate
git init
git add .
git commit -m "Initial commit"
git branch -M main
git remote add origin https://github.com/<USERNAME>/<REPO>.git
git push -u origin main
```

## 2. Render에 백엔드 배포

1. https://render.com 로그인 → "New +" → "Web Service"
2. GitHub 레포 연결 → 권한 허용
3. 설정:
   - Name: `seoul-realestate-api` (자유)
   - Root Directory: `backend`
   - Build Command: `pip install -r requirements.txt`
   - Start Command: `uvicorn main:app --host 0.0.0.0 --port $PORT`
   - Instance Type: **Free**
4. Environment Variables 추가 (Advanced 섹션):
   - `MOLIT_API_KEY` = (data.go.kr 일반 인증키)
   - `KAKAO_REST_KEY`
   - `NAVER_CLIENT_ID`
   - `NAVER_CLIENT_SECRET`
   - `ANTHROPIC_API_KEY`
   - `ALLOW_ORIGINS` = (배포 후 Vercel URL을 여기 추가, 콤마 구분)
5. "Create Web Service" → 빌드 (5분 정도)
6. 완료되면 URL 받음 (예: `https://seoul-realestate-api.onrender.com`)

테스트: `https://<RENDER-URL>/api/properties?lawd_cd=11560` — 매물 JSON 떠야 정상

## 3. Vercel 프론트 배포 전 — vercel.json 수정

`frontend/vercel.json` 파일에서 `__RENDER_URL__` 자리에 위에서 받은 Render URL 도메인을 넣고 커밋:

```json
{
  "rewrites": [
    { "source": "/api/:path*", "destination": "https://seoul-realestate-api.onrender.com/api/:path*" }
  ]
}
```

```bash
git add frontend/vercel.json
git commit -m "Set Render backend URL"
git push
```

## 4. Vercel에 프론트 배포

1. https://vercel.com 로그인 → "Add New" → "Project"
2. GitHub 레포 import
3. 설정:
   - Framework Preset: **Vite**
   - Root Directory: `frontend`
   - Build Command: `npm run build` (기본)
   - Output Directory: `dist` (기본)
4. "Deploy" — 약 1~2분
5. 발행 URL 받음 (예: `https://seoul-realestate.vercel.app`)

## 5. CORS 설정 — Render에 Vercel URL 등록

Render 대시보드 → 환경변수 `ALLOW_ORIGINS` 에 Vercel URL 추가:
```
https://seoul-realestate.vercel.app
```
(`*.vercel.app` 도메인은 이미 자동 허용되어 있어서 사실 필수는 아님)

## 6. 끝!

발급된 Vercel URL을 친구·동료에게 공유하면 됩니다.

---

## ⚠️ 알아둘 점

- **Render 무료 플랜은 15분 유휴 후 sleep** → 첫 접속 시 30~50초 느림. 그 후는 정상 속도.
- DB 파일(`backend/data/apartments.db`)은 git에 포함되어 재배포 시 자동 복원됨.
- 코드 변경 후 `git push` → Vercel·Render 자동 재배포.
- API 키는 절대 git에 올리면 안 됨 (`.env`는 `.gitignore`에 포함됨).

## 비용

- Vercel: 무료 (개인 사이트 100GB/월 대역폭)
- Render: 무료 (Web Service 750h/월)
- API 호출 비용:
  - 네이버 검색·Kakao·MOLIT·건축물대장: 무료
  - **Anthropic Claude (호재·비교 분석)**: 사용량 과금. 보통 호재 검색 1회 ~10원, 비교 분석 ~50원.
