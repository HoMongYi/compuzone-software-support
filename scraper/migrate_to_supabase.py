#!/usr/bin/env python3
"""compuzone.db → Supabase 데이터 이전 스크립트

사용법:
    $env:DATABASE_URL = "postgresql://..."
    python scraper/migrate_to_supabase.py              # 기본: compuzone.db
    python scraper/migrate_to_supabase.py path/to.db   # DB 경로 지정
"""

import os
import sqlite3
import sys

import psycopg2


def migrate(src_path: str, db_url: str):
    src = sqlite3.connect(src_path)
    src.row_factory = sqlite3.Row
    dst = psycopg2.connect(db_url)

    products = src.execute("SELECT product_no, product_name, scraped_at FROM products").fetchall()
    software = src.execute(
        "SELECT product_no, software_url, is_verified, ai_note, updated_at, user_approved FROM software_support"
    ).fetchall()

    with dst.cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS products (
                product_no   INTEGER PRIMARY KEY,
                product_name TEXT NOT NULL,
                scraped_at   TEXT
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS software_support (
                product_no    INTEGER PRIMARY KEY REFERENCES products(product_no),
                software_url  TEXT,
                is_verified   INTEGER DEFAULT 0,
                ai_note       TEXT,
                updated_at    TEXT,
                user_approved INTEGER DEFAULT NULL
            )
        """)
        dst.commit()

        inserted_p = 0
        for row in products:
            cur.execute(
                "INSERT INTO products (product_no, product_name, scraped_at) VALUES (%s, %s, %s) ON CONFLICT DO NOTHING",
                (row["product_no"], row["product_name"], row["scraped_at"]),
            )
            inserted_p += cur.rowcount

        inserted_s = 0
        for row in software:
            cur.execute(
                """INSERT INTO software_support
                   (product_no, software_url, is_verified, ai_note, updated_at, user_approved)
                   VALUES (%s, %s, %s, %s, %s, %s)
                   ON CONFLICT DO NOTHING""",
                (
                    row["product_no"],
                    row["software_url"],
                    row["is_verified"],
                    row["ai_note"],
                    row["updated_at"],
                    row["user_approved"],
                ),
            )
            inserted_s += cur.rowcount

    dst.commit()
    src.close()
    dst.close()

    print(f"✓ 상품 {inserted_p}/{len(products)}개, 소프트웨어 {inserted_s}/{len(software)}개 이전 완료")


if __name__ == "__main__":
    src_path = sys.argv[1] if len(sys.argv) > 1 else "compuzone.db"
    db_url = os.environ.get("DATABASE_URL")

    if not db_url:
        print("오류: DATABASE_URL 환경변수가 설정되지 않았습니다")
        print("  $env:DATABASE_URL = \"postgresql://...\"")
        sys.exit(1)

    if not os.path.exists(src_path):
        print(f"오류: {src_path} 파일을 찾을 수 없습니다")
        sys.exit(1)

    print(f"이전 시작: {src_path} → Supabase")
    migrate(src_path, db_url)
