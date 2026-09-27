#!/usr/bin/env python3
"""
Query and audit utility for AGSI Gas Storage Database (SQLite and PostgreSQL).
Allows inspecting countries, operators, facilities, and the audit view.
"""

import sys
import argparse
from db import get_db, DatabaseBackend


def show_audit(db: DatabaseBackend, limit: int = 25):
    """Displays the v_country_audit view comparing reported numbers with facility rollups."""
    query = """
        SELECT 
            country_name,
            gas_day,
            reported_gis,
            rollup_gas_in_storage,
            gis_delta,
            reported_full_pct,
            rollup_full_percentage,
            consumption,
            consumption_full,
            covered_capacity,
            reporting_facilities_count
        FROM v_country_audit
        ORDER BY reported_gis DESC NULLS LAST
        LIMIT :limit;
    """
    cursor = db.execute(query, {"limit": limit})
    rows = cursor.fetchall()
    
    print("\n" + "=" * 110)
    print(f"               COUNTRY STORAGE AUDIT & ROLLUP VIEW ({db.db_type.upper()})")
    print("=" * 110)
    header = f"{'Country':18s} | {'Day':10s} | {'Rep GiS':9s} | {'Rollup':9s} | {'Delta':7s} | {'Rep%':6s} | {'Roll%':6s} | {'Consump':8s} | {'Stock/C%':8s} | {'Facs':4s}"
    print(header)
    print("-" * 110)
    for r in rows:
        rep_gis = f"{r['reported_gis']:.2f}" if r['reported_gis'] is not None else "-"
        rol_gis = f"{r['rollup_gas_in_storage']:.2f}" if r['rollup_gas_in_storage'] is not None else "-"
        delta = f"{r['gis_delta']:.2f}" if r['gis_delta'] is not None else "-"
        rep_pct = f"{r['reported_full_pct']:.1f}%" if r['reported_full_pct'] is not None else "-"
        rol_pct = f"{r['rollup_full_percentage']:.1f}%" if r['rollup_full_percentage'] is not None else "-"
        cons = f"{r['consumption']:.1f}" if r['consumption'] is not None else "-"
        cons_f = f"{r['consumption_full']:.1f}%" if r['consumption_full'] is not None else "-"
        facs = str(r['reporting_facilities_count'])
        gas_day_str = str(r['gas_day'])
        print(f"{r['country_name']:18s} | {gas_day_str:10s} | {rep_gis:9s} | {rol_gis:9s} | {delta:7s} | {rep_pct:6s} | {rol_pct:6s} | {cons:8s} | {cons_f:8s} | {facs:4s}")
    print("=" * 110 + "\n")


def show_facilities(db: DatabaseBackend, country_code: str = None, limit: int = 25):
    """Displays facility level overview."""
    query = """
        SELECT 
            facility_code,
            facility_name,
            facility_type,
            operator_name,
            country_name,
            gas_day,
            gas_in_storage,
            full_percentage,
            working_gas_volume
        FROM v_facility_overview
    """
    params = {}
    if country_code:
        query += " WHERE country_code = :country_code "
        params["country_code"] = country_code
    query += " ORDER BY gas_in_storage DESC NULLS LAST LIMIT :limit;"
    params["limit"] = limit

    cursor = db.execute(query, params)
    rows = cursor.fetchall()

    print("\n" + "=" * 105)
    print(f"                      FACILITY OVERVIEW ({db.db_type.upper()})" + (f" ({country_code})" if country_code else ""))
    print("=" * 105)
    header = f"{'Facility':28s} | {'Operator':24s} | {'Country':12s} | {'Type':5s} | {'GiS (TWh)':9s} | {'Full %':7s} | {'Capacity':8s}"
    print(header)
    print("-" * 105)
    for r in rows:
        gis = f"{r['gas_in_storage']:.2f}" if r['gas_in_storage'] is not None else "-"
        full = f"{r['full_percentage']:.1f}%" if r['full_percentage'] is not None else "-"
        wgv = f"{r['working_gas_volume']:.2f}" if r['working_gas_volume'] is not None else "-"
        ftype = r['facility_type'] or "-"
        print(f"{r['facility_name'][:28]:28s} | {r['operator_name'][:24]:24s} | {r['country_name'][:12]:12s} | {ftype:5s} | {gis:9s} | {full:7s} | {wgv:8s}")
    print("=" * 105 + "\n")


def main():
    parser = argparse.ArgumentParser(description="Query AGSI database views (SQLite or PostgreSQL).")
    parser.add_argument("--db-type", choices=["sqlite", "postgres"], default="sqlite", help="Database engine (default: sqlite)")
    parser.add_argument("--postgres", "--db-url", dest="db_url", type=str, help="PostgreSQL connection string/URL")
    parser.add_argument("--db", type=str, default="agsi_storage.db", help="Path to SQLite database")
    parser.add_argument("--audit", action="store_true", help="Show country audit view")
    parser.add_argument("--facilities", action="store_true", help="Show facility overview")
    parser.add_argument("--country", type=str, help="Filter by country code (e.g. DE, FR)")
    parser.add_argument("--limit", type=int, default=25, help="Number of rows to show")

    args = parser.parse_args()
    db_type = "postgres" if args.db_url or args.db_type == "postgres" else "sqlite"
    db = get_db(db_type=db_type, db_path=args.db, db_url=args.db_url)

    try:
        if args.facilities:
            show_facilities(db, country_code=args.country, limit=args.limit)
        else:
            show_audit(db, limit=args.limit)
    finally:
        db.close()


if __name__ == "__main__":
    main()
