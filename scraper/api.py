#!/usr/bin/env python3
"""컴퓨존 스마트 소프트웨어 링크 서비스 DB — FastAPI 웹 백엔드

Usage:
  python api.py                    # 기본 DB: compuzone.db
  python api.py path/to/other.db   # DB 경로 지정
"""

import os
import sqlite3
import sys
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

_USE_PG = bool(os.environ.get("DATABASE_URL"))
if _USE_PG:
    import psycopg2


class _PgConn:
    """psycopg2 래퍼 — sqlite3.Connection과 동일한 인터페이스 제공."""

    def __init__(self):
        self._conn = psycopg2.connect(os.environ["DATABASE_URL"])

    @staticmethod
    def _adapt(sql: str) -> str:
        return sql.replace("?", "%s").replace("datetime('now','localtime')", "NOW()")

    def execute(self, sql: str, params=()):
        cur = self._conn.cursor()
        cur.execute(self._adapt(sql), params or None)
        return cur

    def executescript(self, sql: str):
        with self._conn.cursor() as cur:
            for stmt in (s.strip() for s in sql.split(";") if s.strip()):
                cur.execute(stmt)
        self._conn.commit()

    def commit(self):
        self._conn.commit()

    def close(self):
        self._conn.close()


_DEMO_PRODUCTS = [
    (1320001, "ASUS ROG STRIX B650E-F GAMING WIFI 메인보드"),
    (1320002, "MSI MAG B650 TOMAHAWK WIFI 메인보드"),
    (1320003, "GIGABYTE B650 AORUS ELITE AX 메인보드"),
    (1320004, "ASUS TUF GAMING RTX 4070 Ti SUPER OC 그래픽카드"),
    (1320005, "MSI GeForce RTX 4080 SUPER 16G GAMING X SLIM"),
    (1320006, "Samsung 870 EVO 1TB SATA SSD"),
    (1320007, "Western Digital WD Blue SN580 1TB NVMe SSD"),
    (1320008, "ASUS RT-AX88U PRO 무선 공유기"),
    (1320009, "TP-Link Archer AX73 WiFi 6 공유기"),
    (1320010, "Logitech MX Master 3S 무선 마우스"),
    (1320011, "Corsair K100 RGB 광축 키보드"),
    (1320012, "ASUS ROG Swift PG32UQ 4K 게이밍 모니터"),
    (1320013, "HP LaserJet Pro M404n 레이저 프린터"),
    (1320014, "Canon PIXMA G3910 무한잉크 복합기"),
    (1320015, "Seagate IronWolf 4TB NAS HDD"),
    (1320016, "Kingston FURY Beast 32GB DDR5 5600MHz"),
    (1320017, "Creative Sound Blaster X4 외장 사운드카드"),
    (1320018, "Realtek RTL8125 2.5G 네트워크 어댑터"),
    (1320019, "Synology DS923+ NAS"),
    (1320020, "QNAP TS-453E 4베이 NAS"),
]

_DEMO_SOFTWARE = [
    (1320001, "https://www.asus.com/motherboards-components/motherboards/rog/rog-strix-b650e-f-gaming-wifi/helpdesk_download/", 1, "공식 URL 확인됨"),
    (1320002, "https://www.msi.com/Motherboard/MAG-B650-TOMAHAWK-WIFI/support#down-driver", 1, "공식 URL 확인됨"),
    (1320003, "https://www.gigabyte.com/Motherboard/B650-AORUS-ELITE-AX-rev-10/support#support-dl-driver", 1, "공식 URL 확인됨"),
    (1320004, "https://www.asus.com/displays-desktops/graphics-cards/rog/rog-strix-rtx4070ti-super-o16g-gaming/helpdesk_download/", 1, "공식 URL 확인됨"),
    (1320005, "https://www.msi.com/Graphics-Card/GeForce-RTX-4080-SUPER-16G-GAMING-X-SLIM/support#down-driver", 1, "공식 URL 확인됨"),
    (1320006, None, 2, "소프트웨어/드라이버 불필요 (사전필터)"),
    (1320007, "https://www.westerndigital.com/en-us/support/software/wd-blue-sn580-nvme-ssd", 1, "공식 URL 확인됨"),
    (1320008, "https://www.asus.com/networking-iot-servers/wifi-routers/asus-wifi-routers/rt-ax88u-pro/helpdesk_download/", 1, "공식 URL 확인됨"),
    (1320009, "https://www.tp-link.com/en/support/download/archer-ax73/", 1, "공식 URL 확인됨"),
    (1320010, "https://www.logitech.com/en-us/software/logi-options-plus.html", 1, "공식 URL 확인됨"),
    (1320011, "https://www.corsair.com/icue", 1, "공식 URL 확인됨"),
    (1320012, "https://www.asus.com/displays-desktops/monitors/rog/rog-swift-4k-pg32uq/helpdesk_download/", 1, "공식 URL 확인됨"),
    (1320013, "https://support.hp.com/us-en/drivers/hp-laserjet-pro-m404-m405-printer-series/19202535", 1, "공식 URL 확인됨"),
    (1320014, "https://www.canon.co.kr/support", 1, "비공식 도메인 가능성 (수동확인 권장): https://www.canon.co.kr/support"),
    (1320015, None, 2, "소프트웨어/드라이버 불필요 (사전필터)"),
    (1320016, None, 2, "소프트웨어/드라이버 불필요 (사전필터)"),
    (1320017, "https://us.creative.com/support/downloads/", 1, "공식 URL 확인됨"),
    (1320018, "https://www.realtek.com/en/component/zoo/category/network-interface-controllers-10-100-1000m-gigabit-ethernet-pci-express-software", 1, "공식 URL 확인됨"),
    (1320019, "https://www.synology.com/en-us/support/download/DS923+", 1, "공식 URL 확인됨"),
    (1320020, "https://www.qnap.com/en-us/utilities/essentials", 1, "공식 URL 확인됨"),
]


def _seed_demo(conn):
    if _USE_PG:
        for no, name in _DEMO_PRODUCTS:
            conn.execute(
                "INSERT INTO products (product_no, product_name, scraped_at) VALUES (%s, %s, NOW()) ON CONFLICT DO NOTHING",
                (no, name),
            )
        for no, url, verified, note in _DEMO_SOFTWARE:
            conn.execute(
                "INSERT INTO software_support (product_no, software_url, is_verified, ai_note, updated_at) VALUES (%s, %s, %s, %s, NOW()) ON CONFLICT DO NOTHING",
                (no, url, verified, note),
            )
    else:
        for no, name in _DEMO_PRODUCTS:
            conn.execute(
                "INSERT OR IGNORE INTO products (product_no, product_name, scraped_at) VALUES (?, ?, datetime('now','localtime'))",
                (no, name),
            )
        for no, url, verified, note in _DEMO_SOFTWARE:
            conn.execute(
                "INSERT OR IGNORE INTO software_support (product_no, software_url, is_verified, ai_note, updated_at) VALUES (?, ?, ?, ?, datetime('now','localtime'))",
                (no, url, verified, note),
            )
    conn.commit()


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _db_path
    try:
        if _USE_PG:
            conn = _PgConn()
        else:
            if _db_path is None:
                _db_path = os.path.abspath(os.environ.get("DB_PATH", "compuzone.db"))
            conn = sqlite3.connect(_db_path)
        migrate(conn)
        if conn.execute("SELECT COUNT(*) FROM products").fetchone()[0] == 0:
            _seed_demo(conn)
        conn.close()
    except Exception as e:
        print(f"[lifespan] DB 초기화 오류: {e}")
    yield


app = FastAPI(title="컴퓨존 스마트 소프트웨어 링크 서비스 API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

_db_path: Optional[str] = None


# ── helpers ───────────────────────────────────────────────────────────────────

def get_conn():
    if _USE_PG:
        return _PgConn()
    if not _db_path:
        raise HTTPException(status_code=400, detail="DB가 초기화되지 않았습니다")
    conn = sqlite3.connect(_db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.row_factory = sqlite3.Row
    return conn


def migrate(conn):
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS products (
            product_no   INTEGER PRIMARY KEY,
            product_name TEXT NOT NULL,
            scraped_at   TEXT
        );
        CREATE TABLE IF NOT EXISTS software_support (
            product_no   INTEGER PRIMARY KEY REFERENCES products(product_no),
            software_url TEXT,
            is_verified  INTEGER DEFAULT 0,
            ai_note      TEXT,
            updated_at   TEXT
        )
    """)
    if _USE_PG:
        conn.execute(
            "ALTER TABLE software_support ADD COLUMN IF NOT EXISTS user_approved INTEGER DEFAULT NULL"
        )
    else:
        has_col = conn.execute(
            "SELECT COUNT(*) FROM pragma_table_info('software_support') WHERE name='user_approved'"
        ).fetchone()[0]
        if not has_col:
            conn.execute(
                "ALTER TABLE software_support ADD COLUMN user_approved INTEGER DEFAULT NULL"
            )
    conn.commit()


# ── request models ─────────────────────────────────────────────────────────────

class InitDbRequest(BaseModel):
    db_path: str


class SetApprovedRequest(BaseModel):
    product_no: int
    approved: Optional[int] = None


class UpdateUrlRequest(BaseModel):
    product_no: int
    software_url: str


# ── endpoints ─────────────────────────────────────────────────────────────────

@app.post("/init_db")
def init_db(req: InitDbRequest):
    if _USE_PG:
        return {"ok": True, "mode": "supabase"}
    global _db_path
    path = os.path.abspath(req.db_path)
    conn = sqlite3.connect(path)
    migrate(conn)
    conn.close()
    _db_path = path
    return {"ok": True, "db_path": path}


@app.get("/stats")
def get_stats():
    conn = get_conn()
    try:
        def q(sql: str):
            return conn.execute(sql).fetchone()[0]

        return {
            "total":          q("SELECT COUNT(*) FROM products"),
            "has_url":        q("SELECT COUNT(*) FROM software_support WHERE is_verified = 1"),
            "no_software":    q("SELECT COUNT(*) FROM software_support WHERE is_verified = 2"),
            "error_count":    q("SELECT COUNT(*) FROM software_support WHERE is_verified = 3"),
            "unprocessed":    q("""
                SELECT COUNT(*) FROM products p
                LEFT JOIN software_support s ON p.product_no = s.product_no
                WHERE s.product_no IS NULL OR s.is_verified = 0
            """),
            "pending_review": q(
                "SELECT COUNT(*) FROM software_support WHERE is_verified = 1 AND user_approved IS NULL"
            ),
            "approved":       q("SELECT COUNT(*) FROM software_support WHERE user_approved = 1"),
            "rejected":       q("SELECT COUNT(*) FROM software_support WHERE user_approved = 0"),
        }
    finally:
        conn.close()


@app.get("/products")
def get_products(
    filter: str = Query(default="all"),
    search: str = Query(default=""),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=500),
):
    conn = get_conn()
    try:
        filter_map = {
            "has_url":        "s.is_verified = 1",
            "pending_review": "s.is_verified = 1 AND s.user_approved IS NULL",
            "approved":       "s.user_approved = 1",
            "rejected":       "s.user_approved = 0",
            "no_software":    "s.is_verified = 2",
            "error":          "s.is_verified = 3",
            "unprocessed":    "(s.product_no IS NULL OR s.is_verified = 0)",
        }
        where_filter = filter_map.get(filter, "1=1")

        safe_search = search.replace("'", "''")
        where_search = f"p.product_name LIKE '%{safe_search}%'" if safe_search else "1=1"

        total = conn.execute(
            f"SELECT COUNT(*) FROM products p "
            f"LEFT JOIN software_support s ON p.product_no = s.product_no "
            f"WHERE ({where_filter}) AND ({where_search})"
        ).fetchone()[0]

        offset = (page - 1) * page_size
        rows = conn.execute(f"""
            SELECT p.product_no, p.product_name, p.scraped_at,
                   s.software_url, s.is_verified, s.ai_note, s.updated_at, s.user_approved
            FROM products p
            LEFT JOIN software_support s ON p.product_no = s.product_no
            WHERE ({where_filter}) AND ({where_search})
            ORDER BY
              CASE WHEN s.user_approved IS NULL THEN 0 ELSE 1 END,
              p.product_no DESC
            LIMIT {page_size} OFFSET {offset}
        """).fetchall()

        items = [
            {
                "product_no":   r[0],
                "product_name": r[1],
                "scraped_at":   r[2],
                "software_url": r[3],
                "is_verified":  r[4],
                "ai_note":      r[5],
                "updated_at":   r[6],
                "user_approved": r[7],
            }
            for r in rows
        ]

        return {"items": items, "total": total, "page": page, "page_size": page_size}
    finally:
        conn.close()


@app.post("/set_user_approved")
def set_user_approved(req: SetApprovedRequest):
    conn = get_conn()
    try:
        cursor = conn.execute(
            "UPDATE software_support SET user_approved = ? WHERE product_no = ?",
            (req.approved, req.product_no),
        )
        conn.commit()
        if cursor.rowcount == 0:
            raise HTTPException(
                status_code=404,
                detail=f"product_no={req.product_no}에 대한 software_support 레코드가 없습니다",
            )
        return {"ok": True}
    finally:
        conn.close()


@app.post("/update_url")
def update_url(req: UpdateUrlRequest):
    conn = get_conn()
    try:
        cursor = conn.execute(
            "UPDATE software_support SET software_url = ?, is_verified = 1, updated_at = datetime('now','localtime') WHERE product_no = ?",
            (req.software_url, req.product_no),
        )
        conn.commit()
        if cursor.rowcount == 0:
            raise HTTPException(
                status_code=404,
                detail=f"product_no={req.product_no}에 대한 software_support 레코드가 없습니다",
            )
        return {"ok": True}
    finally:
        conn.close()


# ── entrypoint ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn

    db_arg = sys.argv[1] if len(sys.argv) > 1 else "compuzone.db"
    _db_path = os.path.abspath(db_arg)
    if _USE_PG:
        print("[API] Supabase (PostgreSQL) 모드")
    else:
        print(f"[API] SQLite 모드: {_db_path}")
    print("[API] http://localhost:8000 에서 실행 중")

    uvicorn.run(app, host="0.0.0.0", port=8000)
