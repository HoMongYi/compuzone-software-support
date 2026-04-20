# scraper — 데이터 파이프라인

컴퓨존 상품 수집 → AI URL 탐색 → PostgreSQL 이전까지의 전체 데이터 처리 파이프라인입니다.

## 파일 구성

| 파일 | 역할 |
|------|------|
| `main.py` | 통합 CLI 진입점 |
| `crawler.py` | 컴퓨존 상품 페이지 수집 |
| `enricher.py` | Google Gemini AI로 드라이버/SW URL 탐색 |
| `db.py` | SQLite CRUD 헬퍼 |
| `api.py` | FastAPI 백엔드 (PostgreSQL/SQLite 듀얼 모드) |
| `migrate_to_supabase.py` | SQLite → PostgreSQL 데이터 이전 스크립트 |

---

## CLI 사용법

프로젝트 루트에서 실행합니다.

### 상품 수집 (scrape)

```bash
# 카테고리 모드 — 전체 카테고리 수집 (권장)
python scraper/main.py scrape

# 특정 카테고리만 수집
python scraper/main.py scrape --categories 4 8 --max-pages 10

# 스캔 모드 — ProductNo 범위 순차 탐색
python scraper/main.py scrape --scan --start 1000000 --end 1400000 --batch 5000
```

| 옵션 | 기본값 | 설명 |
|------|--------|------|
| `--categories` | 전체 | 수집할 카테고리 BigDivNo 목록 |
| `--max-pages` | 20 | 카테고리당 최대 페이지 수 |
| `--scan` | - | 스캔 모드 활성화 |
| `--start` | 1000000 | 스캔 시작 ProductNo |
| `--end` | 1400000 | 스캔 종료 ProductNo |
| `--batch` | 5000 | 스캔 배치 크기 |

### AI URL 탐색 (enrich)

```bash
# 미처리 상품 100개 탐색 (API 호출)
python scraper/main.py enrich --limit 100 --delay 2.0

# 미처리 목록만 출력 (API 호출 없음)
python scraper/main.py enrich --dry-run
```

| 옵션 | 기본값 | 설명 |
|------|--------|------|
| `--limit` | 100 | 처리할 최대 상품 수 |
| `--delay` | 2.0 | API 호출 간격 (초) |
| `--dry-run` | - | 실제 API 호출 없이 목록만 출력 |

> `GOOGLE_API_KEY` 환경변수 필요

### 통계 / 검색 / 내보내기

```bash
# DB 통계 출력
python scraper/main.py stats

# 상품명 키워드 검색
python scraper/main.py search "ASUS ROG"

# 전체 데이터 CSV 내보내기
python scraper/main.py export --out result.csv
```

---

## DB 업데이트 워크플로우

```
1. 스크래퍼 실행 → compuzone.db 업데이트
2. AI 탐색 실행 → compuzone.db URL 채움
3. NAS PostgreSQL로 이전
```

```powershell
# 1. 수집 + 탐색
python scraper/main.py scrape
python scraper/main.py enrich

# 2. NAS PostgreSQL 이전 (사내 네트워크에서)
$env:DATABASE_URL = "postgresql://compuzone:비밀번호@NAS_IP:5432/compuzone"
python scraper/migrate_to_supabase.py compuzone.db
```

---

## 카테고리 BigDivNo

| 카테고리 | BigDivNo |
|----------|----------|
| 데스크탑조립PC | 1 |
| 노트북태블릿 | 2 |
| 컴퓨터부품 | 4 |
| 모니터 | 5 |
| 키보드마우스저장장치 | 8 |
| 소프트웨어 | 9 |
| 프린터전산소모품 | 11 |
| 네트워크케이블CCTV | 12 |

전체 목록은 `crawler.py`의 `CATEGORY_BIG_DIV` 딕셔너리를 참조하세요.

---

## 주의사항

- 컴퓨존 사이트는 **EUC-KR** 인코딩 사용
- IP 차단 발생 시 `crawler.py`의 `REQUEST_DELAY` (기본 0.5초) 값을 올려 조정
- `compuzone.db`는 `.gitignore`에 등록되어 커밋되지 않음
- `enrich`는 인터넷 연결 및 `GOOGLE_API_KEY` 필요
