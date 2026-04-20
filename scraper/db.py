import sqlite3
import logging

DB_PATH = "compuzone.db"
log = logging.getLogger(__name__)


def get_conn(db_path=DB_PATH):
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.row_factory = sqlite3.Row
    return conn


def init_db(conn):
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS products (
            product_no    INTEGER PRIMARY KEY,
            product_name  TEXT    NOT NULL,
            scraped_at    TEXT
        );

        CREATE TABLE IF NOT EXISTS software_support (
            product_no    INTEGER PRIMARY KEY REFERENCES products(product_no),
            software_url  TEXT,
            is_verified   INTEGER DEFAULT 0,
            ai_note       TEXT,
            updated_at    TEXT
        );
    """)
    conn.commit()


def upsert_product(conn, product_no, product_name):
    conn.execute("""
        INSERT INTO products (product_no, product_name, scraped_at)
        VALUES (?, ?, datetime('now','localtime'))
        ON CONFLICT(product_no) DO UPDATE SET
            product_name = excluded.product_name,
            scraped_at   = excluded.scraped_at
    """, (product_no, product_name))
    conn.commit()


def upsert_software(conn, product_no, software_url, is_verified, note):
    conn.execute("""
        INSERT INTO software_support (product_no, software_url, is_verified, ai_note, updated_at)
        VALUES (?, ?, ?, ?, datetime('now','localtime'))
        ON CONFLICT(product_no) DO UPDATE SET
            software_url = excluded.software_url,
            is_verified  = excluded.is_verified,
            ai_note      = excluded.ai_note,
            updated_at   = excluded.updated_at
    """, (product_no, software_url, is_verified, note))
    conn.commit()


def get_unprocessed(conn, limit=100):
    rows = conn.execute("""
        SELECT p.product_no, p.product_name
        FROM products p
        LEFT JOIN software_support s ON p.product_no = s.product_no
        WHERE s.product_no IS NULL OR s.is_verified = 0
        LIMIT ?
    """, (limit,)).fetchall()
    return rows


def stats(conn):
    total = conn.execute("SELECT COUNT(*) FROM products").fetchone()[0]
    unprocessed = conn.execute("""
        SELECT COUNT(*) FROM products p
        LEFT JOIN software_support s ON p.product_no = s.product_no
        WHERE s.product_no IS NULL OR s.is_verified = 0
    """).fetchone()[0]
    has_url = conn.execute(
        "SELECT COUNT(*) FROM software_support WHERE is_verified = 1"
    ).fetchone()[0]
    no_software = conn.execute(
        "SELECT COUNT(*) FROM software_support WHERE is_verified = 2"
    ).fetchone()[0]
    error = conn.execute(
        "SELECT COUNT(*) FROM software_support WHERE is_verified = 3"
    ).fetchone()[0]
    return {
        "total":       total,
        "unprocessed": unprocessed,
        "has_url":     has_url,
        "no_software": no_software,
        "error":       error,
    }
