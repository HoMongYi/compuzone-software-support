import re
import time
import logging
import os

from google import genai
from google.genai import types

log = logging.getLogger(__name__)

GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash-preview-04-17")

OFFICIAL_DOMAINS = re.compile(
    r'https?://(?:'
    r'(?:[\w-]+\.)*asus\.com|'
    r'(?:[\w-]+\.)*asrock\.com|'
    r'(?:[\w-]+\.)*gigabyte\.com|'
    r'(?:[\w-]+\.)*msi\.com|'
    r'(?:[\w-]+\.)*samsung\.com|'
    r'(?:[\w-]+\.)*lg\.com|'
    r'(?:[\w-]+\.)*intel\.com|'
    r'(?:[\w-]+\.)*amd\.com|'
    r'(?:[\w-]+\.)*nvidia\.com|'
    r'(?:[\w-]+\.)*logitech\.com|'
    r'(?:[\w-]+\.)*tp-link\.com|'
    r'(?:[\w-]+\.)*hp\.com|'
    r'(?:[\w-]+\.)*brother\.com|'
    r'(?:[\w-]+\.)*canon\.com|'
    r'(?:[\w-]+\.)*epson\.com|'
    r'(?:[\w-]+\.)*realtek\.com|'
    r'(?:[\w-]+\.)*synology\.com|'
    r'(?:[\w-]+\.)*qnap\.com|'
    r'(?:[\w-]+\.)*razer\.com|'
    r'(?:[\w-]+\.)*corsair\.com|'
    r'(?:[\w-]+\.)*creative\.com|'
    r'(?:[\w-]+\.)*seagate\.com|'
    r'(?:[\w-]+\.)*westerndigital\.com|'
    r'(?:[\w-]+\.)*kingston\.com|'
    r'(?:[\w-]+\.)*crucial\.com'
    r')',
    re.IGNORECASE,
)

_NO_SW_KEYWORDS = re.compile(
    r'케이블|케이블선|'
    r'쿨러팬|케이스팬|'
    r'파워서플라이|파워 |\bPSU\b|'
    r'스탠드|모니터암|마운트|'
    r'장패드|마우스패드|'
    r'컴퓨터케이스|미들타워|풀타워|미니타워|'
    r'써멀|서멀그리스|써멀구리스|'
    r'멀티탭|전원케이블',
    re.IGNORECASE,
)

SYSTEM_PROMPT = (
    "당신은 PC 하드웨어 전문가입니다. "
    "사용자가 제품명을 주면, 그 제품의 공식 드라이버/소프트웨어 다운로드 페이지 URL을 "
    "한 줄로만 반환하세요. "
    "Google 검색을 사용해 반드시 실제로 존재하는 공식 URL만 반환하세요. "
    "드라이버나 소프트웨어가 필요 없는 제품이거나 찾을 수 없으면 'NONE'만 반환하세요. "
    "URL 이외의 설명은 절대 추가하지 마세요."
)


def needs_software(product_name):
    return not bool(_NO_SW_KEYWORDS.search(product_name))


def query_ai(product_name):
    api_key = os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        raise RuntimeError("GOOGLE_API_KEY 환경변수가 설정되지 않았습니다.")

    client = genai.Client(api_key=api_key)

    def _call():
        return client.models.generate_content(
            model=GEMINI_MODEL,
            contents=f"제품명: {product_name}",
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT,
                tools=[types.Tool(google_search=types.GoogleSearch())],
            ),
        )

    try:
        response = _call()
    except Exception as e:
        err = str(e)
        if "404" in err or "NOT_FOUND" in err:
            raise
        if "429" in err or "quota" in err.lower() or "rate limit" in err.lower():
            log.warning("Rate limit — 60초 대기 후 재시도")
            time.sleep(60)
            response = _call()
        else:
            raise

    text = response.text.strip() if response.text else ""

    if not text or "NONE" in text.upper():
        return None, 2, "드라이버/소프트웨어 없음 또는 불필요"

    url = None
    lines = text.splitlines()
    if lines and lines[0].startswith("http"):
        url = lines[0].strip().rstrip(".")
    else:
        matches = re.findall(r'https?://\S+', text)
        if matches:
            url = matches[0].rstrip(".")

    if url is None:
        return None, 2, "AI 응답에서 URL을 찾지 못함"

    if not OFFICIAL_DOMAINS.match(url):
        return url, 1, f"비공식 도메인 가능성 (수동확인 권장): {url}"

    return url, 1, "공식 URL 확인됨"


def enrich_batch(conn, limit=100, delay=2.0):
    from db import get_unprocessed, upsert_software

    rows = get_unprocessed(conn, limit)
    log.info("미처리 %d개 처리 시작", len(rows))

    for row in rows:
        product_no = row["product_no"]
        product_name = row["product_name"]

        if not needs_software(product_name):
            log.info("[SKIP] %d — %s (소프트웨어 불필요)", product_no, product_name)
            upsert_software(conn, product_no, None, 2, "소프트웨어/드라이버 불필요 (사전필터)")
            continue

        log.info("[AI]   %d — %s", product_no, product_name)
        try:
            url, verified, note = query_ai(product_name)
            upsert_software(conn, product_no, url, verified, note)
            log.info("       → %s (%s)", url or "없음", note)
        except Exception as e:
            log.error("       오류: %s", e)
            upsert_software(conn, product_no, None, 3, str(e))

        time.sleep(delay)

    log.info("enrich 완료")
