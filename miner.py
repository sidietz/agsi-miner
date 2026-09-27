#!/usr/bin/env python3
"""
Main CLI tool for AGSI Gas Storage Miner.
Extracts gas storage transparency data from live website or local HTML snapshot
and saves into an explicit relational SQLite or PostgreSQL database.
"""

import os
import sys
import argparse
import requests
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any

from db import get_db, init_db, save_parsed_dataset, DatabaseBackend
from parser import parse_live_api, parse_html_file


AGSI_API_URL = "https://agsi.gie.eu/api"
DEFAULT_HTML_FILE = "Gas Infrastructure Europe - AGSI.html"
DEFAULT_DB_FILE = "agsi_storage.db"

HEADERS = {
    "Referer": "https://agsi.gie.eu/",
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "X-Requested-With": "XMLHttpRequest",
    "Accept": "application/json, text/javascript, */*; q=0.01"
}


def fetch_live_data(date: Optional[str] = None, timeout: int = 15) -> Dict[str, Any]:
    """Fetches full hierarchical JSON data from AGSI transparency website."""
    params = {}
    if date:
        params["date"] = date

    print(f"[*] Fetching live AGSI data from {AGSI_API_URL}" + (f" for date {date}..." if date else "..."))
    resp = requests.get(AGSI_API_URL, headers=HEADERS, params=params, timeout=timeout)
    resp.raise_for_status()

    data = resp.json()
    if data.get("error") and not data.get("data"):
        raise RuntimeError(f"AGSI API error: {data.get('message') or data.get('error')}")

    return data


def print_summary(db: DatabaseBackend, gas_day: Optional[str] = None):
    """Prints a structured summary of the latest storage status from the database."""
    print("\n" + "=" * 70)
    print(f"            AGSI GAS STORAGE SUMMARY REPORT ({db.db_type.upper()})")
    print("=" * 70)

    n_regions = db.execute("SELECT COUNT(*) AS cnt FROM regions;").fetchone()["cnt"]
    n_countries = db.execute("SELECT COUNT(*) AS cnt FROM countries;").fetchone()["cnt"]
    n_operators = db.execute("SELECT COUNT(*) AS cnt FROM operators;").fetchone()["cnt"]
    n_facilities = db.execute("SELECT COUNT(*) AS cnt FROM facilities;").fetchone()["cnt"]

    print(f"Entities in Database: {n_regions} Regions | {n_countries} Countries | {n_operators} Operators | {n_facilities} Facilities")

    if not gas_day:
        row = db.execute("SELECT MAX(gas_day) AS max_gas_day FROM country_storage_data;").fetchone()
        gas_day = row["max_gas_day"] if row and row["max_gas_day"] else None

    if not gas_day:
        print("No storage data records found.")
        print("=" * 70 + "\n")
        return

    # Convert date object to str if PostgreSQL returned a datetime.date
    gas_day_str = str(gas_day)
    print(f"Gas Day: {gas_day_str}")
    print("-" * 70)

    # Regional totals
    query_reg = """
        SELECT r.name, rs.gas_in_storage, rs.working_gas_volume, rs.full_percentage, rs.net_withdrawal
        FROM regions r
        JOIN region_storage_data rs ON r.code = rs.region_code
        WHERE rs.gas_day = :gas_day
        ORDER BY r.code;
    """
    cursor = db.execute(query_reg, {"gas_day": gas_day})
    reg_rows = cursor.fetchall()
    for row in reg_rows:
        gis = f"{row['gas_in_storage']:.2f} TWh" if row['gas_in_storage'] is not None else "N/A"
        wgv = f"{row['working_gas_volume']:.2f} TWh" if row['working_gas_volume'] is not None else "N/A"
        full = f"{row['full_percentage']:.2f}%" if row['full_percentage'] is not None else "N/A"
        print(f"Region: {row['name']:10s} | Gas in Storage: {gis:12s} | Capacity: {wgv:12s} | Full: {full}")

    # Top 10 Countries by Storage Volume
    print("-" * 70)
    print(f"{'Country':20s} | {'Storage (TWh)':14s} | {'Capacity':12s} | {'Full %':8s} | {'Coverage %':10s}")
    print("-" * 70)
    query_country = """
        SELECT c.name, cs.gas_in_storage, cs.working_gas_volume, cs.full_percentage, cs.covered_capacity
        FROM countries c
        JOIN country_storage_data cs ON c.code = cs.country_code
        WHERE cs.gas_day = :gas_day
        ORDER BY cs.gas_in_storage DESC NULLS LAST
        LIMIT 10;
    """
    cursor = db.execute(query_country, {"gas_day": gas_day})
    for row in cursor.fetchall():
        gis = f"{row['gas_in_storage']:.2f}" if row['gas_in_storage'] is not None else "-"
        wgv = f"{row['working_gas_volume']:.2f}" if row['working_gas_volume'] is not None else "-"
        full = f"{row['full_percentage']:.2f}%" if row['full_percentage'] is not None else "-"
        cov = f"{row['covered_capacity']:.1f}%" if row['covered_capacity'] is not None else "-"
        print(f"{row['name']:20s} | {gis:14s} | {wgv:12s} | {full:8s} | {cov:10s}")

    print("=" * 70 + "\n")


def main():
    parser = argparse.ArgumentParser(description="Mine gas storage data from AGSI into SQLite or PostgreSQL.")
    parser.add_argument("--db-type", choices=["sqlite", "postgres"], default="sqlite", help="Database engine (default: sqlite)")
    parser.add_argument("--postgres", "--db-url", dest="db_url", type=str, help="PostgreSQL connection string/URL (e.g. postgresql://user:pass@localhost:5432/dbname)")
    parser.add_argument("--db", type=str, default=DEFAULT_DB_FILE, help=f"SQLite database file (default: {DEFAULT_DB_FILE})")
    parser.add_argument("--init-db", action="store_true", help="Initialize database schema and views")
    parser.add_argument("--live", action="store_true", help="Scrape live data directly from https://agsi.gie.eu/")
    parser.add_argument("--file", type=str, help=f"Path to local HTML file (default: {DEFAULT_HTML_FILE})")
    parser.add_argument("--date", type=str, help="Target gas day for live scraping (YYYY-MM-DD)")
    parser.add_argument("--summary", action="store_true", help="Print summary report after mining")

    args = parser.parse_args()

    # Determine database type
    db_type = "postgres" if args.db_url or args.db_type == "postgres" else "sqlite"
    db = get_db(db_type=db_type, db_path=args.db, db_url=args.db_url)

    # Schema initialization CLI option
    if args.init_db:
        print(f"[*] Initializing database schema on {db_type.upper()}...")
        init_db(db)
        print(f"[+] Database schema, tables, indexes, and views initialized successfully on {db_type.upper()}!")
        # If user ONLY ran --init-db without requesting scraping, exit here
        if not (args.live or args.file):
            db.close()
            return

    # Ensure schema is ready before ingestion
    init_db(db)

    parsed_data = None
    source_name = ""

    # Mode selection: Live vs Local File
    if args.live:
        target_date = args.date
        if not target_date:
            target_date = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%d")
        raw_json = fetch_live_data(date=target_date)
        parsed_data = parse_live_api(raw_json)
        source_name = f"Live AGSI website ({target_date})"
    else:
        file_to_parse = args.file or (DEFAULT_HTML_FILE if os.path.exists(DEFAULT_HTML_FILE) else None)
        if not file_to_parse:
            print(f"[!] No file specified and '{DEFAULT_HTML_FILE}' not found. Attempting live scrape instead...", file=sys.stderr)
            raw_json = fetch_live_data(date=args.date)
            parsed_data = parse_live_api(raw_json)
            source_name = "Live AGSI website (fallback)"
        else:
            print(f"[*] Parsing local HTML snapshot: {file_to_parse}...")
            parsed_data = parse_html_file(file_to_parse)
            source_name = f"Local HTML snapshot ({file_to_parse})"

    # Save to database
    target_info = args.db_url if db_type == "postgres" else args.db
    print(f"[*] Saving parsed entities and time-series records to {db_type.upper()}: {target_info}...")
    counts = save_parsed_dataset(db, parsed_data)

    print("\n[+] Extraction and Ingestion Successful!")
    print(f"    Source: {source_name}")
    print(f"    Database ({db_type.upper()}): {target_info}")
    print("    Records upserted:")
    for key, count in counts.items():
        print(f"      - {key}: {count}")

    print_summary(db)
    db.close()


if __name__ == "__main__":
    main()
