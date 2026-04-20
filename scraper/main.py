#!/usr/bin/env python3
"""컴퓨존 스마트 소프트웨어 링크 서비스 DB — 통합 CLI

subcommands:
  scrape   상품 수집 (카테고리 모드 / 스캔 모드)
  enrich   AI 드라이버 URL 탐색
  stats    DB 통계
  search   상품명 키워드 검색
  export   CSV 내보내기
"""

import argparse
import csv
import logging
import sys

import db
import crawler
import enricher


def setup_logging(verbose=False):
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
        level=level,
        stream=sys.stdout,
    )


# ── scrape ────────────────────────────────────────────────────────────────────

def cmd_scrape(args):
    conn = db.get_conn()
    db.init_db(conn)

    if args.scan:
        crawler.scrape_scan_mode(
            conn,
            start=args.start,
            end=args.end,
            batch=args.batch,
        )
    else:
        cats = args.categories if args.categories else None
        crawler.scrape_category_mode(
            conn,
            categories=cats,
            max_pages=args.max_pages,
        )

    conn.close()


# ── enrich ────────────────────────────────────────────────────────────────────

def cmd_enrich(args):
    conn = db.get_conn()
    db.init_db(conn)

    if args.dry_run:
        rows = db.get_unprocessed(conn, limit=args.limit)
        print(f"미처리 상품 (최대 {args.limit}개, 실제 {len(rows)}개):")
        for row in rows:
            print(f"  {row['product_no']:>10}  {row['product_name']}")
    else:
        enricher.enrich_batch(conn, limit=args.limit, delay=args.delay)

    conn.close()


# ── stats ─────────────────────────────────────────────────────────────────────

def cmd_stats(args):
    conn = db.get_conn()
    db.init_db(conn)
    s = db.stats(conn)
    conn.close()

    print("=" * 40)
    print(f"  전체 상품:        {s['total']:>8,}")
    print(f"  미처리:           {s['unprocessed']:>8,}")
    print(f"  URL 보유:         {s['has_url']:>8,}")
    print(f"  소프트웨어 없음:  {s['no_software']:>8,}")
    print(f"  오류:             {s['error']:>8,}")
    print("=" * 40)


# ── search ────────────────────────────────────────────────────────────────────

def cmd_search(args):
    conn = db.get_conn()
    db.init_db(conn)
    keyword = f"%{args.keyword}%"
    rows = conn.execute("""
        SELECT p.product_no, p.product_name, s.software_url, s.is_verified, s.ai_note
        FROM products p
        LEFT JOIN software_support s ON p.product_no = s.product_no
        WHERE p.product_name LIKE ?
        LIMIT 50
    """, (keyword,)).fetchall()
    conn.close()

    if not rows:
        print("검색 결과 없음")
        return

    status_map = {0: "미처리", 1: "URL있음", 2: "없음", 3: "오류"}
    for r in rows:
        status = status_map.get(r["is_verified"], "?")
        print(f"{r['product_no']:>10}  [{status:<5}]  {r['product_name']}")
        if r["software_url"]:
            print(f"             {r['software_url']}")
        if r["ai_note"] and r["is_verified"] not in (None, 0):
            print(f"             ※ {r['ai_note']}")


# ── export ────────────────────────────────────────────────────────────────────

def cmd_export(args):
    conn = db.get_conn()
    db.init_db(conn)
    rows = conn.execute("""
        SELECT p.product_no, p.product_name, p.scraped_at,
               s.software_url, s.is_verified, s.ai_note, s.updated_at
        FROM products p
        LEFT JOIN software_support s ON p.product_no = s.product_no
        ORDER BY p.product_no
    """).fetchall()
    conn.close()

    out_path = args.out
    with open(out_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow([
            "product_no", "product_name", "scraped_at",
            "software_url", "is_verified", "ai_note", "updated_at",
        ])
        for r in rows:
            writer.writerow(list(r))

    print(f"내보내기 완료: {out_path}  ({len(rows):,}행)")


# ── parser ────────────────────────────────────────────────────────────────────

def build_parser():
    parser = argparse.ArgumentParser(
        prog="main.py",
        description="컴퓨존 스마트 소프트웨어 링크 서비스 DB 관리 CLI",
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="디버그 로그 출력")
    sub = parser.add_subparsers(dest="command", required=True)

    p_scrape = sub.add_parser("scrape", help="상품 수집")
    p_scrape.add_argument(
        "--scan", action="store_true",
        help="스캔 모드 — ProductNo를 순차 탐색 (기본: 카테고리 모드)",
    )
    p_scrape.add_argument("--start",      type=int, default=1000000, metavar="N")
    p_scrape.add_argument("--end",        type=int, default=1400000, metavar="N")
    p_scrape.add_argument("--batch",      type=int, default=5000,    metavar="N")
    p_scrape.add_argument(
        "--categories", type=int, nargs="+", metavar="BIGDIVNO",
        help="카테고리 BigDivNo 목록 (기본: 전체 카테고리)",
    )
    p_scrape.add_argument("--max-pages",  type=int, default=20,      metavar="N")

    p_enrich = sub.add_parser("enrich", help="AI 드라이버 URL 탐색")
    p_enrich.add_argument("--limit",   type=int,   default=100, metavar="N")
    p_enrich.add_argument("--delay",   type=float, default=2.0, metavar="SEC",
                          help="API 호출 간격 (초, 기본 2.0)")
    p_enrich.add_argument("--dry-run", action="store_true",
                          help="실제 API 호출 없이 미처리 목록만 출력")

    sub.add_parser("stats", help="DB 통계 출력")

    p_search = sub.add_parser("search", help="상품명 키워드 검색")
    p_search.add_argument("keyword", help="검색할 키워드")

    p_export = sub.add_parser("export", help="전체 데이터 CSV 내보내기")
    p_export.add_argument("--out", default="result.csv", metavar="FILE")

    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()
    setup_logging(args.verbose)

    dispatch = {
        "scrape": cmd_scrape,
        "enrich": cmd_enrich,
        "stats":  cmd_stats,
        "search": cmd_search,
        "export": cmd_export,
    }
    dispatch[args.command](args)


if __name__ == "__main__":
    main()
