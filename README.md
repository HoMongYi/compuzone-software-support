# 컴퓨존 스마트 소프트웨어 링크 서비스 — 관리 툴

컴퓨존(compuzone.co.kr) 상품을 자동으로 수집하고, **Google Gemini AI**로 각 상품의 공식 드라이버/소프트웨어 URL을 탐색한 뒤, 담당자가 **웹 기반 관리 툴**에서 검토·승인하는 통합 파이프라인입니다.

## 서비스 URL

| 서비스 | URL |
|--------|-----|
| 관리 툴 (프론트엔드) | [compuzone1.homongyi.org](https://compuzone1.homongyi.org) |
| 백엔드 API | [compuzone1-api.homongyi.org](https://compuzone1-api.homongyi.org) |

## 시스템 구조

```
[로컬 데이터 파이프라인]
  scraper/ → compuzone.db (SQLite)
                   ↓ migrate_to_supabase.py
           NAS PostgreSQL (Docker)
                   ↑
           FastAPI api.py (Docker, :10001)
                   ↑
           nginx (Docker, :10000) ← SvelteKit build/
                   ↑
         Cloudflare Tunnel (homongyi-tunnel, HTTPS)
```

| 레이어 | 기술 | 역할 |
|--------|------|------|
| 스크래퍼 | Python + requests/BS4 | 컴퓨존 상품 수집 → SQLite 저장 |
| AI 탐색 | Google Gemini 2.5 + Google Search | 상품명 기반 공식 SW URL 자동 탐색 |
| 데이터베이스 | PostgreSQL (NAS Docker) | 영구 데이터 저장 |
| 백엔드 API | FastAPI (NAS Docker, :10001) | DB 읽기/쓰기 REST 엔드포인트 |
| 프론트엔드 | nginx (NAS Docker, :10000) | SvelteKit 정적 파일 서빙 |
| 터널 | Cloudflare Tunnel (homongyi-tunnel) | NAS → 외부 HTTPS 노출 |

## 파일 구조

```
compuzone-software-support/
├── scraper/                  데이터 파이프라인 (→ scraper/README.md 참고)
├── src/                      SvelteKit 관리 툴 프론트엔드
│   └── routes/+page.svelte
├── src-tauri/                Tauri 데스크탑 앱 래퍼
├── build/                    프론트엔드 빌드 결과물 (NAS 업로드)
├── Dockerfile                API 컨테이너 빌드
├── docker-compose.yml        NAS 배포 (PostgreSQL + FastAPI + nginx)
├── nginx.conf                nginx 설정 (NAS에 업로드)
├── .env.docker.example       NAS 환경변수 템플릿
├── requirements.txt          Python 의존성
└── set-env.example.ps1       로컬 환경변수 설정 템플릿
```

## NAS Docker 배포

### NAS 초기 설정

```bash
# 1. NAS 파일 관리자에서 /volume1/docker/compuzone-software/ 에 복사
#    Dockerfile, docker-compose.yml, requirements.txt, nginx.conf
#    scraper/__init__.py, scraper/api.py
#    build/ 폴더 전체

# 2. NAS에 .env 파일 생성 (.env.docker.example 참고)
DB_PASSWORD=비밀번호
DATABASE_URL=postgresql://compuzone:비밀번호@db:5432/compuzone

# 3. NAS SSH에서 실행
docker compose up -d
```

### 프론트엔드 업데이트

#### NAS (nginx) 배포

```powershell
# 로컬 PC에서 빌드
$env:VITE_API_BASE="https://compuzone1-api.homongyi.org"
npm run build

# build/ 폴더를 NAS /volume1/docker/compuzone-software/build/ 에 덮어쓰기 업로드
# nginx는 파일을 직접 읽으므로 재시작 불필요
```

#### Tauri 데스크탑 앱 빌드

```powershell
# Rust + Tauri CLI 설치 필요
npm run tauri build
# 빌드 결과물: src-tauri/target/release/bundle/
```

### Cloudflare Tunnel (homongyi-tunnel) 설정

[one.dash.cloudflare.com](https://one.dash.cloudflare.com) → Zero Trust → Networks → Tunnels → `homongyi-tunnel` → Published application routes

| Domain | Service |
|--------|---------|
| `compuzone1-api.homongyi.org` | `http://192.168.0.221:10001` |
| `compuzone1.homongyi.org` | `http://192.168.0.221:10000` |

## 관리 툴 주요 기능

| 기능 | 설명 |
|------|------|
| 통계 대시보드 | 전체 / 검토 대기 / 승인 / 거부 / 오류 / 미처리 수치 |
| 상태별 필터 + 검색 | 검토대기·승인·거부 등 필터, 상품명 텍스트 검색 |
| URL 검토 | ✓ 예(승인) / ✗ 아니요(수정) 버튼, Enter/Esc 단축키 |
| URL 직접 수정 | 오류 URL 교체 또는 새 URL 입력 후 저장 |
| 미처리 직접 등록 | AI 미분석 상품에 담당자가 URL 직접 입력 |

## DB 스키마

### `products`
| 컬럼 | 타입 | 설명 |
|------|------|------|
| `product_no` | INTEGER PK | 컴퓨존 상품 번호 |
| `product_name` | TEXT | 상품명 |
| `scraped_at` | TEXT | 수집 일시 |

### `software_support`
| 컬럼 | 타입 | 설명 |
|------|------|------|
| `product_no` | INTEGER PK FK | products 참조 |
| `software_url` | TEXT | 드라이버/소프트웨어 URL |
| `is_verified` | INTEGER | 0=미처리 1=URL있음 2=SW없음 3=오류 |
| `ai_note` | TEXT | AI 탐색 메모 |
| `updated_at` | TEXT | 최종 수정 일시 |
| `user_approved` | INTEGER | NULL=미검토 1=승인 0=거부 |
