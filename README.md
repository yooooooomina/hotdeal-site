# 핫딜 줍줍 — 자동화 설정 가이드

## 폴더 구조
```
hotdeal-site/
├── index.html
├── style.css
├── script.js                 ← data/*.json 을 fetch해서 화면에 그림
├── data/
│   ├── keywords.json          ← 쿠팡에서 감시할 검색어 목록 (직접 수정)
│   ├── price-history.json     ← 자동 생성/갱신 (건드릴 필요 없음)
│   ├── deals-coupang.json     ← 자동 생성/갱신 (건드릴 필요 없음)
│   └── deals-toss.json        ← 토스쇼핑 핫딜 (직접 수정)
├── scripts/
│   └── fetch-deals.mjs        ← 쿠팡파트너스 API 호출 + 핫딜 판별 스크립트
└── .github/workflows/
    └── update-deals.yml       ← 3시간마다 자동 실행되는 GitHub Actions
```

## 처음 설정 순서

### 1. GitHub 저장소 만들고 이 폴더 전체 업로드
- github.com → New repository → `hotdeal-site` 생성
- 이 폴더의 모든 파일(하위 폴더 포함)을 그대로 업로드

### 2. GitHub Pages 켜기
- 저장소 Settings → Pages → Branch를 `main`으로 선택 → Save
- `https://내아이디.github.io/hotdeal-site/` 주소 생성됨

### 3. 쿠팡파트너스 API 키를 GitHub Secrets에 등록
- 쿠팡파트너스 대시보드에서 Access Key / Secret Key 발급 (누적 판매 15만원 이상일 때 신청 가능)
- 저장소 Settings → Secrets and variables → Actions → New repository secret
  - 이름: `COUPANG_ACCESS_KEY` / 값: 발급받은 Access Key
  - 이름: `COUPANG_SECRET_KEY` / 값: 발급받은 Secret Key
- **절대 이 키를 코드 파일 안에 직접 적지 마세요.** Secrets에만 저장하세요.

### 4. 감시할 키워드 정하기
- `data/keywords.json` 열어서 원하는 카테고리/키워드로 수정

### 5. 자동화 켜기
- 저장소 Actions 탭 → "핫딜 자동 업데이트" 워크플로우 선택 → "Run workflow" 눌러서 첫 실행 테스트
- 정상 동작하면 이후로는 3시간마다 자동으로 돌아갑니다 (`.github/workflows/update-deals.yml`의 `cron` 값을 바꾸면 주기 조절 가능)

### 6. 토스쇼핑 핫딜 추가하기 (수동)
- `data/deals-toss.json` 에 상품을 직접 추가하고 커밋 → 사이트에 바로 반영

## 핫딜 판정 기준 바꾸기
`scripts/fetch-deals.mjs` 상단의 이 값들을 조절하면 돼요:
```js
const DISCOUNT_THRESHOLD = 0.15;   // 15% 이상 떨어지면 핫딜
const HISTORY_KEEP = 10;           // 상품별 가격 기록 보관 개수
const DEAL_EXPIRY_HOURS = 48;      // 이 시간 지나면 목록에서 제외
```

## 로컬에서 미리보기 하려면
```bash
python3 -m http.server 8000
```
브라우저에서 `http://localhost:8000` 접속 (index.html을 그냥 더블클릭하면 fetch가 막혀서 안 보여요)
