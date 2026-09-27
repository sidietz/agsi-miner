# AGSI Gas Storage Miner

A Python transparency miner and parser for European Gas Storage data from the **AGSI (Aggregated Gas Storage Inventory)** platform: [https://agsi.gie.eu/](https://agsi.gie.eu/).

Supports both **SQLite** and **PostgreSQL (via psycopg 3)**.

---

## Architecture & Database Schema

The database explicitly models European gas storage into 4 distinct entity tiers and tailored time-series metrics tables, alongside bottom-up rollup and audit views:

```
regions  --->  countries  --->  operators  --->  facilities
   |               |                |                 |
region_data  country_data    operator_data    facility_data
```

### Tables
- **`regions`** / **`region_storage_data`**: Regional aggregates (`EU`, `Non-EU`).
- **`countries`** / **`country_storage_data`**: National storage metrics + national annual gas consumption (`consumption`) and stock-to-consumption ratio (`consumption_full`).
- **`operators`** / **`operator_storage_data`**: Storage System Operators (SSOs) with EIC X-codes and transparency links.
- **`facilities`** / **`facility_storage_data`**: Individual underground storage sites with EIC W/Z-codes, facility types (e.g. `DSR`, `ASF`), and GPS coordinates.

### Views
- **`v_country_audit`**: Compares official GIE reported country numbers against bottom-up facility aggregates, highlighting coverage % and deltas.
- **`v_country_rollup`**: Dynamic bottom-up aggregation of facility data to country level.
- **`v_operator_rollup`**: Dynamic bottom-up aggregation of facility data to operator level.
- **`v_facility_overview`**: Dimensional query joining facilities with their operator, country, and region.

---

## Installation

```bash
pip install -r requirements.txt
```
*(Dependencies: `requests`, `beautifulsoup4`, `psycopg[binary]`)*

---

## Usage

### 1. Initialize Database Schema
You can initialize the tables, indexes, and views explicitly:
```bash
# SQLite (default)
python miner.py --init-db

# PostgreSQL
python miner.py --init-db --db-type postgres --postgres "postgresql://user:pass@localhost:5432/dbname"
```

### 2. Single-Day Ingestion
Fetch the complete European tree (all countries, operators, and facilities):
```bash
# Ingest into SQLite (default)
python miner.py --live

# Ingest into PostgreSQL
python miner.py --live --db-type postgres --postgres "postgresql://user:pass@localhost:5432/dbname"

# Fetch a specific gas day
python miner.py --live --date 2026-09-25
```

### 3. Bulk Date Range Import (`bulk_import.py`)
Import historical gas storage data across a date range `[start, end)` (start date inclusive, end date exclusive). All parameters of `miner.py` are forwarded:
```bash
# Ingest date range into SQLite:
python bulk_import.py --start 2026-09-01 --end 2026-09-27

# Ingest date range into PostgreSQL with schema initialization:
python bulk_import.py --start 2026-09-01 --end 2026-09-27 --init-db --db-type postgres --postgres "postgresql://user:pass@localhost:5432/dbname"

# Ingest with custom delay (e.g. 1.0s) between requests:
python bulk_import.py --start 2026-09-10 --end 2026-09-20 --delay 1.0
```

### 4. Ingest from Local Offline Snapshot
Parse the local HTML file (`Gas Infrastructure Europe - AGSI.html`):
```bash
# Ingest into SQLite
python miner.py

# Ingest into PostgreSQL
python miner.py --db-type postgres --postgres "postgresql://user:pass@localhost:5432/dbname"
```

### 5. Query & Audit
Inspect country audit comparisons and facility metrics:
```bash
# View country storage audit vs. facility rollups (SQLite)
python query.py --audit

# View country storage audit on PostgreSQL
python query.py --audit --db-type postgres --postgres "postgresql://user:pass@localhost:5432/dbname"

# View individual storage facilities (e.g. Germany)
python query.py --facilities --country DE
```

### 6. Run Test Suite
```bash
python -m unittest discover tests
```
