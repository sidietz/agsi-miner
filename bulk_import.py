#!/usr/bin/env python3
"""
Bulk import utility for AGSI Gas Storage Miner.
Iterates over a date range [start, end) and calls miner.py for each day.
"""

import sys
import time
import argparse
import subprocess
from datetime import datetime, timedelta
from typing import List


def parse_date(date_str: str) -> datetime.date:
    """Parses date string in YYYY-MM-DD format."""
    try:
        return datetime.strptime(date_str.strip(), "%Y-%m-%d").date()
    except ValueError:
        raise argparse.ArgumentTypeError(f"Invalid date format: '{date_str}'. Expected 'YYYY-MM-DD'.")


def main():
    parser = argparse.ArgumentParser(
        description="Bulk import AGSI gas storage data for a date range [start, end) by invoking miner.py.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Ingest a 3-day range into SQLite:
  python bulk_import.py --start 2026-09-24 --end 2026-09-27

  # Ingest into PostgreSQL with schema initialization:
  python bulk_import.py --start 2026-09-01 --end 2026-09-27 --init-db --db-type postgres --postgres "postgresql://user:pass@localhost:5432/dbname"

  # Pass additional miner.py options (e.g. custom db path):
  python bulk_import.py --start 2026-09-20 --end 2026-09-25 --db my_storage.db
        """
    )

    # Date range options (start inclusive, end exclusive)
    parser.add_argument("--start", "-s", type=parse_date, required=True,
                        help="Start gas day date (inclusive), formatted as YYYY-MM-DD")
    parser.add_argument("--end", "-e", type=parse_date, required=True,
                        help="End gas day date (exclusive), formatted as YYYY-MM-DD")

    # Options specific to bulk_import
    parser.add_argument("--delay", type=float, default=0.5,
                        help="Delay in seconds between successive miner.py calls (default: 0.5)")
    parser.add_argument("--stop-on-error", action="store_true",
                        help="Stop bulk import immediately if any day fails")

    # Capture all other known and unknown arguments to pass to miner.py
    args, unknown_miner_args = parser.parse_known_args()

    start_date = args.start
    end_date = args.end

    if start_date >= end_date:
        print(f"[!] Error: Start date ({start_date}) must be before end date ({end_date}).", file=sys.stderr)
        sys.exit(1)

    # Compute list of days [start, end)
    days_to_process = []
    curr = start_date
    while curr < end_date:
        days_to_process.append(curr.strftime("%Y-%m-%d"))
        curr += timedelta(days=1)

    total_days = len(days_to_process)
    print("=" * 70)
    print("                     AGSI BULK IMPORT")
    print("=" * 70)
    print(f"Date Range       : {start_date} (inclusive) to {end_date} (exclusive)")
    print(f"Total Gas Days   : {total_days}")
    if unknown_miner_args:
        print(f"Miner Arguments  : {' '.join(unknown_miner_args)}")
    print("=" * 70 + "\n")

    # If --init-db was in arguments, initialize schema once first
    init_db_in_args = "--init-db" in unknown_miner_args
    filtered_miner_args = [arg for arg in unknown_miner_args if arg != "--init-db"]

    # Ensure --live is present if not reading from a file
    if "--live" not in filtered_miner_args and "--file" not in filtered_miner_args:
        filtered_miner_args.append("--live")

    python_executable = sys.executable

    if init_db_in_args:
        print("[*] Initializing database schema before starting bulk import...")
        init_cmd = [python_executable, "miner.py", "--init-db"] + filtered_miner_args
        # Remove --date if accidentally passed
        res = subprocess.run(init_cmd)
        if res.returncode != 0:
            print("[!] Database initialization failed. Aborting bulk import.", file=sys.stderr)
            sys.exit(res.returncode)
        print("[+] Database schema ready.\n")

    successful_days = []
    failed_days = []

    for idx, day_str in enumerate(days_to_process, start=1):
        print(f"\n>>> [{idx}/{total_days}] Processing gas day: {day_str} <<<")

        cmd = [python_executable, "miner.py", "--date", day_str] + filtered_miner_args
        start_time = time.time()
        res = subprocess.run(cmd)
        elapsed = time.time() - start_time

        if res.returncode == 0:
            successful_days.append(day_str)
            print(f"[+] Gas day {day_str} completed successfully in {elapsed:.2f}s")
        else:
            failed_days.append(day_str)
            print(f"[!] Error: Gas day {day_str} failed with return code {res.returncode}", file=sys.stderr)
            if args.stop_on_error:
                print("[!] Aborting due to --stop-on-error flag.", file=sys.stderr)
                break

        # Throttling delay between requests if not the last item
        if idx < total_days and args.delay > 0:
            time.sleep(args.delay)

    print("\n" + "=" * 70)
    print("                 BULK IMPORT SUMMARY")
    print("=" * 70)
    print(f"Total days requested : {total_days}")
    print(f"Successful           : {len(successful_days)}")
    print(f"Failed               : {len(failed_days)}")
    if failed_days:
        print(f"Failed dates         : {', '.join(failed_days)}")
    print("=" * 70 + "\n")

    if failed_days:
        sys.exit(1)


if __name__ == "__main__":
    main()
