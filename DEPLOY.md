# 배포 가이드 (Vercel + Render)

## 0. 사전 준비

- GitHub 계정
- backend/.env에 있는 모든 키 값 복사해두기 (Render 환경변수 입력에 사용)

---

## 1. GitHub 푸시 (최초 1회)

PowerShell에서:
```powershell
cd C:\Users\qkrwj\seoul-realestate
git init
git add .
git commit -m "Initial deploy"
git branch -M main
git remote add origin https://github.com/<your-username>/seoul-realestate.git
git push -u origin main
```

GitHub에서 먼저 빈 repo 만든 뒤(README 체크 해제) 위 명령. `<your-username>` 본인 것으로.

> ⚠️ `.env`는 `.gitignore`에 있어 자동 제외됩니다. 절대 직접 git add 하지 마세요.

---

## 2. 백엔드 — Render 배포

1. https://render.com 가입 (GitHub 로그인)
2. 대시보드 → **New +** → **Web Service** → GitHub 저장소 `seoul-realestate` 연결
3. 설정:
   - **Name**: `seoul-realestate-api` (URL이 됨)
   - **Region**: Singapore (한국에서 가장 가까움)
   - **Branch**: main
   - **Root Directory**: `backend`
   - **Runtime**: Python 3
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `uvicorn main:app --host 0.0.0.0 --port $PORT`
   - **Plan**: **Free**
4. **Environment Variables** — 하나씩 추가 (backend/.env 값 그대로):

| 키 | 값 출처 |
|---|---|
| `ANTHROPIC_API_KEY` | sk-ant-... |
| `MOLIT_API_KEY` | (.env) |
| `KAKAO_REST_KEY` | (.env) |
| `NAVER_CLIENT_ID` | (.env) |
| `NAVER_CLIENT_SECRET` | (.env) |
| `SEOUL_API_KEY_PROGRESS` | 7147566478... |
| `SEOUL_API_KEY_STATUS` | 73686b7a... |
| `PUBLIC_DATA_KEY_ENCODED` | pmaK5RXorxc...%3D%3D |
| `PUBLIC_DATA_KEY_DECODED` | pmaK5RXorxc...== |
| `ALLOW_ORIGINS` | (Vercel 배포 후 받는 URL — 일단 비워두기) |

5. **Create Web Service** 클릭 → 빌드 5~10분 대기 → 완료되면
   `https://seoul-realestate-api.onrender.com` URL 받음
6. 그 URL 끝에 `/` 붙여 브라우저 접속 → `{"status":"ok","service":"서울 부동산 API v2"}` 나오면 성공

---

## 3. 프론트엔드 — Vercel 배포

1. https://vercel.com 가입 (GitHub 로그인)
2. **Add New → Project** → `seoul-realestate` import
3. **Configure**:
   - Framework Preset: **Vite** (자동 인식)
   - Root Directory: `frontend`
   - Build Command: `npm run build` (기본)
   - Output Directory: `dist` (기본)
4. **Deploy** 클릭 → 1~2분 후 `https://seoul-realestate.vercel.app` 받음
5. 받은 Vercel URL을 Render `ALLOW_ORIGINS`에 추가 → Render 자동 재배포

---

## 4. 프록시 URL 연결 (핵심!)

Vercel은 `/api/*` 요청을 Render 백엔드로 프록시해야 함. `frontend/vercel.json` 수정:

```json
{
  "rewrites": [
    {
      "source": "/api/:path*",
      "destination": "https://seoul-realestate-api.onrender.com/api/:path*"
    }
  ]
}
```

`__RENDER_URL__` 플레이스홀더를 위 실제 Render URL로 교체.

```powershell
cd C:\Users\qkrwj\seoul-realestate
git add frontend/vercel.json
git commit -m "Point proxy to Render"
git push
```

Vercel이 자동 재배포 (1분).

---

## 5. DB(apartments.db) 처리

| 옵션 | 설명 |
|---|---|
| **A. Git에 포함** (~5MB) ← 추천 | SQLite 파일 그대로 push. 배포 시 DB 같이 올라감. 데이터 갱신은 로컬 enrich → git push. |
| B. Render Disk 마운트 | 영구 디스크 붙여 enrich 스크립트도 클라우드에서. 무료 플랜에선 불가. |

옵션 A 사용. `backend/data/apartments.db`가 `.gitignore`에 없는지 확인:
```powershell
git check-ignore backend/data/apartments.db
# 출력 없으면 OK (추적 가능). 출력 있으면 그 줄 .gitignore에서 삭제 필요.
```

---

## 6. 점검 체크리스트

- [ ] Render 백엔드 URL `/` → `{"status":"ok",...}` ✓
- [ ] `/api/properties?bounds_size=0.05&lat_center=37.5&lng_center=126.9` → JSON 응답
- [ ] Vercel 사이트 접속 → 지도·마커 보임
- [ ] 단지 클릭 → 상세 패널 + 네이버 매물 카드
- [ ] 호재 검색 → AI 요약 박스
- [ ] 비교 분석 → 7개 카테고리 표시

---

## ⚠️ Render 무료 플랜 특성 (꼭 알아두기)

- **15분 동안 요청 없으면 슬립** → 첫 요청 시 깨어나는 데 **약 30초~1분** 소요
  - 친구에게 공유 직전 한 번 클릭해서 깨워두면 좋음
  - 또는 [UptimeRobot](https://uptimerobot.com) 같은 무료 ping 서비스로 5분마다 깨워둘 수 있음
- **750시간/월 무료** (한 서비스 24/7 가능)
- **빌드 메모리 512MB** — 우리는 가벼워서 문제 없음

---

## 트러블슈팅

| 증상 | 원인 / 해결 |
|---|---|
| **CORS 에러** | Render `ALLOW_ORIGINS`에 Vercel URL 미설정. 추가 후 재배포. |
| **502 / 504 첫 요청** | 슬립 깨우는 중. 30초 기다리면 정상. |
| **AI 응답 없음 (호재/비교)** | `ANTHROPIC_API_KEY` 누락 / Tier 한도. Render Logs에서 확인. |
| **DB 비어있음** (지도에 마커 0개) | `backend/data/apartments.db`가 git에 포함됐는지 확인. |
| **빌드 실패: ModuleNotFoundError** | `backend/requirements.txt`에 빠진 패키지. `pip freeze` 비교. |
| **vercel.json이 안 먹힘** | rewrites destination URL 끝에 / 빠지거나 오타. Vercel 빌드 로그 확인. |

---

## 비용 (모두 무료로 시작)

| 서비스 | 무료 한도 | 우리 앱 예상 |
|---|---|---|
| **Vercel** | 100GB/월 대역폭, 빌드 6000분/월 | 무료로 충분 |
| **Render** | 750시간/월 (1개 서비스 24/7 가능) | 무료로 충분 |
| **Anthropic API** | Tier에 따라 다름 (지금 결제됨) | 호재 1회 ≈ $0.01, 비교 1회 ≈ $0.05 |

---

## 다음 단계 (선택)

- **커스텀 도메인** (예: realestate.yourdomain.com) — Vercel 무료, DNS 설정만
- **UptimeRobot으로 슬립 방지** — 5분마다 백엔드 ping → 항상 깨어있음
- **데이터 갱신 자동화** — GitHub Actions로 매주 enrich 스크립트 실행 후 자동 commit
