import re
import time
import random
import logging
import requests
from bs4 import BeautifulSoup
from concurrent.futures import ThreadPoolExecutor, as_completed

BASE_URL = "https://www.compuzone.co.kr"
REQUEST_DELAY = 0.5
MAX_WORKERS = 5
MAX_CONSEC_MISS = 300

CATEGORY_BIG_DIV = {
    "데스크탑조립PC":       1,
    "노트북태블릿":         2,
    "Apple":                3,
    "컴퓨터부품":           4,
    "모니터":               5,
    "음향영상카메라":        7,
    "키보드마우스저장장치":  8,
    "소프트웨어":           9,
    "프린터전산소모품":      11,
    "네트워크케이블CCTV":   12,
    "생활가전":             13,
    "자동차공구안전":        14,
    "가구조명전기":          87,
    "스마트폰액세서리":      88,
    "중고리퍼비시":          89,
    "영상가전":             101,
    "게임드론완구":          103,
    "스포츠레저":           105,
    "계절가전":             107,
    "주방가전":             110,
    "서버워크스테이션":      111,
    "구독렌탈":             112,
}

log = logging.getLogger(__name__)

_session = None


def get_session():
    global _session
    if _session is None:
        _session = requests.Session()
        _session.headers.update({
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            )
        })
    return _session


def fetch_url(url, timeout=12, max_retries=3):
    for attempt in range(max_retries):
        try:
            r = get_session().get(url, timeout=timeout)
            if r.status_code == 403:
                wait = 60 * (attempt + 1) + random.uniform(0, 10)
                log.warning("403 차단 감지 — %d초 대기", int(wait))
                time.sleep(wait)
                continue
            if r.status_code == 200:
                return r.content
            log.debug("HTTP %d: %s", r.status_code, url)
            return None
        except requests.RequestException as e:
            log.debug("요청 실패 (시도 %d/%d): %s — %s", attempt + 1, max_retries, url, e)
            time.sleep(2 ** attempt)
    return None


def parse_list_page_product_nos(html_bytes):
    try:
        html = html_bytes.decode("euc-kr", errors="replace")
    except Exception:
        html = html_bytes.decode("utf-8", errors="replace")
    return list(set(map(int, re.findall(r'product_detail\.htm\?ProductNo=(\d+)', html))))


def parse_product_name(html_bytes):
    try:
        html = html_bytes.decode("euc-kr", errors="replace")
    except Exception:
        html = html_bytes.decode("utf-8", errors="replace")
    soup = BeautifulSoup(html, "html.parser")
    title_tag = soup.find("title")
    if not title_tag:
        return None
    title = title_tag.get_text(strip=True)
    if title.startswith("컴퓨존") or len(title) < 4:
        return None
    name = re.sub(r'\s*:\s*컴퓨존.*$', '', title).strip()
    return name if name else None


def scrape_category_mode(conn, categories=None, max_pages=20):
    from db import upsert_product

    if categories is None:
        categories = list(CATEGORY_BIG_DIV.values())

    total_saved = 0
    for big_div_no in categories:
        log.info("카테고리 BigDivNo=%d 수집 시작", big_div_no)
        for page in range(1, max_pages + 1):
            list_url = (
                f"{BASE_URL}/product/productB_new_list.htm"
                f"?BigDivNo={big_div_no}&page={page}"
            )
            raw = fetch_url(list_url)
            if raw is None:
                log.warning("페이지 가져오기 실패: %s", list_url)
                break
            nos = parse_list_page_product_nos(raw)
            if not nos:
                log.info(
                    "카테고리 %d 페이지 %d: 상품 없음 → 다음 카테고리",
                    big_div_no, page,
                )
                break
            log.info(
                "카테고리 %d 페이지 %d: %d개 ProductNo 발견",
                big_div_no, page, len(nos),
            )
            for no in nos:
                detail_url = f"{BASE_URL}/product/product_detail.htm?ProductNo={no}"
                detail_raw = fetch_url(detail_url)
                if detail_raw is None:
                    continue
                name = parse_product_name(detail_raw)
                if name:
                    upsert_product(conn, no, name)
                    total_saved += 1
                    log.debug("저장: %d — %s", no, name)
                time.sleep(REQUEST_DELAY)
            time.sleep(REQUEST_DELAY)

    log.info("카테고리 모드 완료 — 총 %d개 저장", total_saved)
    return total_saved


def _fetch_product(no):
    url = f"{BASE_URL}/product/product_detail.htm?ProductNo={no}"
    raw = fetch_url(url)
    if raw is None:
        return no, None
    name = parse_product_name(raw)
    return no, name


def scrape_scan_mode(conn, start=1000000, end=1400000, batch=5000):
    from db import upsert_product

    total_saved = 0
    consec_miss = 0

    for chunk_start in range(start, end + 1, batch):
        chunk_end = min(chunk_start + batch - 1, end)
        log.info("스캔 청크 %d ~ %d", chunk_start, chunk_end)

        chunk_saved = 0
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
            futures = {
                ex.submit(_fetch_product, no): no
                for no in range(chunk_start, chunk_end + 1)
            }
            for fut in as_completed(futures):
                no, name = fut.result()
                if name:
                    upsert_product(conn, no, name)
                    total_saved += 1
                    chunk_saved += 1
                    log.debug("저장: %d — %s", no, name)
                time.sleep(REQUEST_DELAY / MAX_WORKERS)

        if chunk_saved == 0:
            consec_miss += (chunk_end - chunk_start + 1)
            log.info("청크 결과 0개 — 누적 연속 미스: %d", consec_miss)
            if consec_miss >= MAX_CONSEC_MISS:
                log.info("연속 빈 구간 %d개 → 조기 종료", consec_miss)
                break
        else:
            consec_miss = 0

    log.info("스캔 모드 완료 — 총 %d개 저장", total_saved)
    return total_saved
