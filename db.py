"""
Database module for AGSI Gas Storage Miner.
Supports both SQLite and PostgreSQL (via psycopg 3) backends with schema initialization,
views, and idempotent upserts.
"""

import os
import re
import sqlite3
from typing import Dict, Any, List, Optional, Union, Tuple

try:
    import psycopg
    from psycopg.rows import dict_row
    PSYCOPG_AVAILABLE = True
except ImportError:
    PSYCOPG_AVAILABLE = False


class DatabaseBackend:
    """Unified abstraction for SQLite and PostgreSQL databases (using psycopg 3)."""

    def __init__(self, db_type: str = "sqlite", db_path: str = "agsi_storage.db", db_url: Optional[str] = None):
        self.db_type = db_type.lower()
        self.db_path = db_path
        self.db_url = db_url

        if self.db_type == "sqlite":
            self.conn = sqlite3.connect(self.db_path)
            self.conn.execute("PRAGMA foreign_keys = ON;")
            self.conn.execute("PRAGMA journal_mode = WAL;")
            self.conn.row_factory = sqlite3.Row
        elif self.db_type in ("postgres", "postgresql"):
            if not PSYCOPG_AVAILABLE:
                raise ImportError("psycopg (version 3) is required for PostgreSQL support. Install via 'pip install psycopg[binary]'.")
            pg_conn_str = self.db_url or os.getenv("DATABASE_URL") or os.getenv("PG_CONN_STRING") or "dbname=agsi"
            self.conn = psycopg.connect(pg_conn_str, row_factory=dict_row)
            self.conn.autocommit = False
        else:
            raise ValueError(f"Unsupported database type: '{self.db_type}'. Choose 'sqlite' or 'postgres'.")

    def _format_sql(self, sql: str) -> str:
        """Converts :param syntax to %(param)s for PostgreSQL if needed."""
        if self.db_type in ("postgres", "postgresql"):
            # Replace :param_name with %(param_name)s
            return re.sub(r':([a-zA-Z0-9_]+)', r'%(\1)s', sql)
        return sql

    def execute(self, sql: str, params: Optional[Union[Dict[str, Any], Tuple, List]] = None):
        """Executes a single SQL query."""
        formatted_sql = self._format_sql(sql)
        cursor = self.conn.cursor()
        if params is not None:
            cursor.execute(formatted_sql, params)
        else:
            cursor.execute(formatted_sql)
        return cursor

    def executemany(self, sql: str, param_list: List[Dict[str, Any]]):
        """Executes batch parameter list."""
        if not param_list:
            return
        formatted_sql = self._format_sql(sql)
        cursor = self.conn.cursor()
        cursor.executemany(formatted_sql, param_list)
        return cursor

    def commit(self):
        """Commits the current transaction."""
        self.conn.commit()

    def rollback(self):
        """Rolls back the current transaction."""
        self.conn.rollback()

    def close(self):
        """Closes the connection."""
        self.conn.close()

    def cursor(self):
        """Returns a cursor appropriate for the database type."""
        return self.conn.cursor()


def get_db(db_type: str = "sqlite", db_path: str = "agsi_storage.db", db_url: Optional[str] = None) -> DatabaseBackend:
    """Factory function to get a DatabaseBackend instance."""
    return DatabaseBackend(db_type=db_type, db_path=db_path, db_url=db_url)


def get_connection(db_path: str = "agsi_storage.db") -> DatabaseBackend:
    """Backward-compatible helper returning SQLite DatabaseBackend."""
    return get_db(db_type="sqlite", db_path=db_path)


def init_db(db: DatabaseBackend) -> None:
    """Initializes tables, indexes, and analytical views for SQLite or PostgreSQL."""
    is_pg = db.db_type in ("postgres", "postgresql")
    pk_auto = "SERIAL PRIMARY KEY" if is_pg else "INTEGER PRIMARY KEY AUTOINCREMENT"

    ddl = f"""
    -- ====================================================================
    -- 1. DIMENSION TABLES (Explicit Entities)
    -- ====================================================================

    CREATE TABLE IF NOT EXISTS regions (
        code VARCHAR(16) PRIMARY KEY,
        name VARCHAR(100) NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS countries (
        code VARCHAR(16) PRIMARY KEY,
        name VARCHAR(100) NOT NULL,
        region_code VARCHAR(16) NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (region_code) REFERENCES regions(code) ON DELETE RESTRICT
    );
    CREATE INDEX IF NOT EXISTS idx_countries_region ON countries(region_code);

    CREATE TABLE IF NOT EXISTS operators (
        code VARCHAR(32) PRIMARY KEY,
        name VARCHAR(255) NOT NULL,
        country_code VARCHAR(16) NOT NULL,
        publication_link TEXT,
        transparency_template TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (country_code) REFERENCES countries(code) ON DELETE RESTRICT
    );
    CREATE INDEX IF NOT EXISTS idx_operators_country ON operators(country_code);

    CREATE TABLE IF NOT EXISTS facilities (
        code VARCHAR(32) PRIMARY KEY,
        name VARCHAR(255) NOT NULL,
        operator_code VARCHAR(32) NOT NULL,
        country_code VARCHAR(16) NOT NULL,
        facility_type VARCHAR(32),
        latitude REAL,
        longitude REAL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (operator_code) REFERENCES operators(code) ON DELETE RESTRICT,
        FOREIGN KEY (country_code) REFERENCES countries(code) ON DELETE RESTRICT
    );
    CREATE INDEX IF NOT EXISTS idx_facilities_operator ON facilities(operator_code);
    CREATE INDEX IF NOT EXISTS idx_facilities_country ON facilities(country_code);

    -- ====================================================================
    -- 2. TIME-SERIES STORAGE DATA TABLES (Per Entity Type)
    -- ====================================================================

    CREATE TABLE IF NOT EXISTS region_storage_data (
        id {pk_auto},
        region_code VARCHAR(16) NOT NULL,
        gas_day DATE NOT NULL,
        gas_day_start DATE,
        gas_day_end DATE,
        status CHAR(1),
        gas_in_storage REAL,
        full_percentage REAL,
        trend REAL,
        injection REAL,
        withdrawal REAL,
        net_withdrawal REAL,
        working_gas_volume REAL,
        injection_capacity REAL,
        withdrawal_capacity REAL,
        covered_capacity REAL,
        updated_at_source VARCHAR(64),
        scraped_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (region_code) REFERENCES regions(code) ON DELETE CASCADE,
        UNIQUE(region_code, gas_day)
    );
    CREATE INDEX IF NOT EXISTS idx_region_storage_date ON region_storage_data(gas_day);

    CREATE TABLE IF NOT EXISTS country_storage_data (
        id {pk_auto},
        country_code VARCHAR(16) NOT NULL,
        gas_day DATE NOT NULL,
        gas_day_start DATE,
        gas_day_end DATE,
        status CHAR(1),
        gas_in_storage REAL,
        full_percentage REAL,
        trend REAL,
        injection REAL,
        withdrawal REAL,
        net_withdrawal REAL,
        working_gas_volume REAL,
        injection_capacity REAL,
        withdrawal_capacity REAL,
        contracted_capacity REAL,
        available_capacity REAL,
        consumption REAL,
        consumption_full REAL,
        covered_capacity REAL,
        updated_at_source VARCHAR(64),
        scraped_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (country_code) REFERENCES countries(code) ON DELETE CASCADE,
        UNIQUE(country_code, gas_day)
    );
    CREATE INDEX IF NOT EXISTS idx_country_storage_date ON country_storage_data(gas_day);

    CREATE TABLE IF NOT EXISTS operator_storage_data (
        id {pk_auto},
        operator_code VARCHAR(32) NOT NULL,
        gas_day DATE NOT NULL,
        gas_day_start DATE,
        gas_day_end DATE,
        status CHAR(1),
        gas_in_storage REAL,
        full_percentage REAL,
        trend REAL,
        injection REAL,
        withdrawal REAL,
        net_withdrawal REAL,
        working_gas_volume REAL,
        injection_capacity REAL,
        withdrawal_capacity REAL,
        contracted_capacity REAL,
        available_capacity REAL,
        covered_capacity REAL,
        updated_at_source VARCHAR(64),
        scraped_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (operator_code) REFERENCES operators(code) ON DELETE CASCADE,
        UNIQUE(operator_code, gas_day)
    );
    CREATE INDEX IF NOT EXISTS idx_operator_storage_date ON operator_storage_data(gas_day);

    CREATE TABLE IF NOT EXISTS facility_storage_data (
        id {pk_auto},
        facility_code VARCHAR(32) NOT NULL,
        gas_day DATE NOT NULL,
        gas_day_start DATE,
        gas_day_end DATE,
        status CHAR(1),
        gas_in_storage REAL,
        full_percentage REAL,
        trend REAL,
        injection REAL,
        withdrawal REAL,
        net_withdrawal REAL,
        working_gas_volume REAL,
        injection_capacity REAL,
        withdrawal_capacity REAL,
        contracted_capacity REAL,
        available_capacity REAL,
        updated_at_source VARCHAR(64),
        scraped_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (facility_code) REFERENCES facilities(code) ON DELETE CASCADE,
        UNIQUE(facility_code, gas_day)
    );
    CREATE INDEX IF NOT EXISTS idx_facility_storage_date ON facility_storage_data(gas_day);
    """

    views_ddl = """
    DROP VIEW IF EXISTS v_facility_overview;
    DROP VIEW IF EXISTS v_country_audit;
    DROP VIEW IF EXISTS v_country_rollup;
    DROP VIEW IF EXISTS v_operator_rollup;

    CREATE VIEW v_operator_rollup AS
    SELECT 
        f.operator_code,
        o.name AS operator_name,
        f.country_code,
        fs.gas_day,
        COUNT(DISTINCT f.code) AS facility_count,
        ROUND(CAST(SUM(fs.gas_in_storage) AS NUMERIC), 4) AS rollup_gas_in_storage,
        ROUND(CAST(SUM(fs.injection) AS NUMERIC), 2) AS rollup_injection,
        ROUND(CAST(SUM(fs.withdrawal) AS NUMERIC), 2) AS rollup_withdrawal,
        ROUND(CAST(SUM(fs.net_withdrawal) AS NUMERIC), 2) AS rollup_net_withdrawal,
        ROUND(CAST(SUM(CASE WHEN fs.gas_in_storage IS NOT NULL THEN fs.working_gas_volume ELSE 0 END) AS NUMERIC), 4) AS rollup_active_wgv,
        ROUND(
            CAST(SUM(fs.gas_in_storage) / 
            NULLIF(SUM(CASE WHEN fs.gas_in_storage IS NOT NULL THEN fs.working_gas_volume ELSE 0 END), 0) * 100 AS NUMERIC), 
            2
        ) AS rollup_full_percentage
    FROM facilities f
    JOIN operators o ON f.operator_code = o.code
    JOIN facility_storage_data fs ON f.code = fs.facility_code
    GROUP BY f.operator_code, o.name, f.country_code, fs.gas_day;

    CREATE VIEW v_country_rollup AS
    SELECT 
        c.code AS country_code,
        c.name AS country_name,
        c.region_code,
        fs.gas_day,
        COUNT(DISTINCT f.code) AS facility_count,
        ROUND(CAST(SUM(fs.gas_in_storage) AS NUMERIC), 4) AS rollup_gas_in_storage,
        ROUND(CAST(SUM(fs.injection) AS NUMERIC), 2) AS rollup_injection,
        ROUND(CAST(SUM(fs.withdrawal) AS NUMERIC), 2) AS rollup_withdrawal,
        ROUND(CAST(SUM(fs.net_withdrawal) AS NUMERIC), 2) AS rollup_net_withdrawal,
        ROUND(CAST(SUM(CASE WHEN fs.gas_in_storage IS NOT NULL THEN fs.working_gas_volume ELSE 0 END) AS NUMERIC), 4) AS rollup_active_wgv,
        ROUND(
            CAST(SUM(fs.gas_in_storage) / 
            NULLIF(SUM(CASE WHEN fs.gas_in_storage IS NOT NULL THEN fs.working_gas_volume ELSE 0 END), 0) * 100 AS NUMERIC), 
            2
        ) AS rollup_full_percentage
    FROM countries c
    JOIN facilities f ON c.code = f.country_code
    JOIN facility_storage_data fs ON f.code = fs.facility_code
    GROUP BY c.code, c.name, c.region_code, fs.gas_day;

    CREATE VIEW v_country_audit AS
    SELECT 
        c.code AS country_code,
        c.name AS country_name,
        cs.gas_day,
        cs.status AS reported_status,
        cs.gas_in_storage AS reported_gis,
        vr.rollup_gas_in_storage,
        ROUND(CAST(cs.gas_in_storage - vr.rollup_gas_in_storage AS NUMERIC), 4) AS gis_delta,
        cs.full_percentage AS reported_full_pct,
        vr.rollup_full_percentage,
        cs.working_gas_volume AS reported_wgv,
        vr.rollup_active_wgv,
        cs.consumption,
        cs.consumption_full,
        cs.covered_capacity,
        COALESCE(vr.facility_count, 0) AS reporting_facilities_count
    FROM countries c
    JOIN country_storage_data cs ON c.code = cs.country_code
    LEFT JOIN v_country_rollup vr ON c.code = vr.country_code AND cs.gas_day = vr.gas_day;

    CREATE VIEW v_facility_overview AS
    SELECT 
        f.code AS facility_code,
        f.name AS facility_name,
        f.facility_type,
        f.latitude,
        f.longitude,
        o.code AS operator_code,
        o.name AS operator_name,
        c.code AS country_code,
        c.name AS country_name,
        r.name AS region_name,
        fs.gas_day,
        fs.status,
        fs.gas_in_storage,
        fs.full_percentage,
        fs.trend,
        fs.injection,
        fs.withdrawal,
        fs.net_withdrawal,
        fs.working_gas_volume
    FROM facilities f
    JOIN operators o ON f.operator_code = o.code
    JOIN countries c ON f.country_code = c.code
    JOIN regions r ON c.region_code = r.code
    JOIN facility_storage_data fs ON f.code = fs.facility_code;
    """

    try:
        if is_pg:
            with db.conn.cursor() as cur:
                cur.execute(ddl)
                cur.execute(views_ddl)
            db.commit()
        else:
            with db.conn:
                db.conn.executescript(ddl)
                db.conn.executescript(views_ddl)
    except Exception as e:
        db.rollback()
        raise RuntimeError(f"Database initialization failed: {e}") from e


def upsert_regions(db: DatabaseBackend, regions: List[Dict[str, Any]]) -> int:
    """Inserts or updates regions."""
    sql = """
    INSERT INTO regions (code, name)
    VALUES (:code, :name)
    ON CONFLICT(code) DO UPDATE SET
        name = excluded.name;
    """
    db.executemany(sql, regions)
    return len(regions)


def upsert_countries(db: DatabaseBackend, countries: List[Dict[str, Any]]) -> int:
    """Inserts or updates countries."""
    sql = """
    INSERT INTO countries (code, name, region_code)
    VALUES (:code, :name, :region_code)
    ON CONFLICT(code) DO UPDATE SET
        name = excluded.name,
        region_code = excluded.region_code;
    """
    db.executemany(sql, countries)
    return len(countries)


def upsert_operators(db: DatabaseBackend, operators: List[Dict[str, Any]]) -> int:
    """Inserts or updates operators."""
    sql = """
    INSERT INTO operators (code, name, country_code, publication_link, transparency_template)
    VALUES (:code, :name, :country_code, :publication_link, :transparency_template)
    ON CONFLICT(code) DO UPDATE SET
        name = excluded.name,
        country_code = excluded.country_code,
        publication_link = excluded.publication_link,
        transparency_template = excluded.transparency_template;
    """
    db.executemany(sql, operators)
    return len(operators)


def upsert_facilities(db: DatabaseBackend, facilities: List[Dict[str, Any]]) -> int:
    """Inserts or updates facilities."""
    sql = """
    INSERT INTO facilities (code, name, operator_code, country_code, facility_type, latitude, longitude)
    VALUES (:code, :name, :operator_code, :country_code, :facility_type, :latitude, :longitude)
    ON CONFLICT(code) DO UPDATE SET
        name = excluded.name,
        operator_code = excluded.operator_code,
        country_code = excluded.country_code,
        facility_type = excluded.facility_type,
        latitude = excluded.latitude,
        longitude = excluded.longitude;
    """
    db.executemany(sql, facilities)
    return len(facilities)


def upsert_region_storage(db: DatabaseBackend, records: List[Dict[str, Any]]) -> int:
    """Inserts or updates region storage time-series records."""
    sql = """
    INSERT INTO region_storage_data (
        region_code, gas_day, gas_day_start, gas_day_end, status,
        gas_in_storage, full_percentage, trend, injection, withdrawal,
        net_withdrawal, working_gas_volume, injection_capacity, withdrawal_capacity,
        covered_capacity, updated_at_source
    ) VALUES (
        :region_code, :gas_day, :gas_day_start, :gas_day_end, :status,
        :gas_in_storage, :full_percentage, :trend, :injection, :withdrawal,
        :net_withdrawal, :working_gas_volume, :injection_capacity, :withdrawal_capacity,
        :covered_capacity, :updated_at_source
    )
    ON CONFLICT(region_code, gas_day) DO UPDATE SET
        gas_day_start = excluded.gas_day_start,
        gas_day_end = excluded.gas_day_end,
        status = excluded.status,
        gas_in_storage = excluded.gas_in_storage,
        full_percentage = excluded.full_percentage,
        trend = excluded.trend,
        injection = excluded.injection,
        withdrawal = excluded.withdrawal,
        net_withdrawal = excluded.net_withdrawal,
        working_gas_volume = excluded.working_gas_volume,
        injection_capacity = excluded.injection_capacity,
        withdrawal_capacity = excluded.withdrawal_capacity,
        covered_capacity = excluded.covered_capacity,
        updated_at_source = excluded.updated_at_source,
        scraped_at = CURRENT_TIMESTAMP;
    """
    db.executemany(sql, records)
    return len(records)


def upsert_country_storage(db: DatabaseBackend, records: List[Dict[str, Any]]) -> int:
    """Inserts or updates country storage time-series records."""
    sql = """
    INSERT INTO country_storage_data (
        country_code, gas_day, gas_day_start, gas_day_end, status,
        gas_in_storage, full_percentage, trend, injection, withdrawal,
        net_withdrawal, working_gas_volume, injection_capacity, withdrawal_capacity,
        contracted_capacity, available_capacity, consumption, consumption_full,
        covered_capacity, updated_at_source
    ) VALUES (
        :country_code, :gas_day, :gas_day_start, :gas_day_end, :status,
        :gas_in_storage, :full_percentage, :trend, :injection, :withdrawal,
        :net_withdrawal, :working_gas_volume, :injection_capacity, :withdrawal_capacity,
        :contracted_capacity, :available_capacity, :consumption, :consumption_full,
        :covered_capacity, :updated_at_source
    )
    ON CONFLICT(country_code, gas_day) DO UPDATE SET
        gas_day_start = excluded.gas_day_start,
        gas_day_end = excluded.gas_day_end,
        status = excluded.status,
        gas_in_storage = excluded.gas_in_storage,
        full_percentage = excluded.full_percentage,
        trend = excluded.trend,
        injection = excluded.injection,
        withdrawal = excluded.withdrawal,
        net_withdrawal = excluded.net_withdrawal,
        working_gas_volume = excluded.working_gas_volume,
        injection_capacity = excluded.injection_capacity,
        withdrawal_capacity = excluded.withdrawal_capacity,
        contracted_capacity = excluded.contracted_capacity,
        available_capacity = excluded.available_capacity,
        consumption = excluded.consumption,
        consumption_full = excluded.consumption_full,
        covered_capacity = excluded.covered_capacity,
        updated_at_source = excluded.updated_at_source,
        scraped_at = CURRENT_TIMESTAMP;
    """
    db.executemany(sql, records)
    return len(records)


def upsert_operator_storage(db: DatabaseBackend, records: List[Dict[str, Any]]) -> int:
    """Inserts or updates operator storage time-series records."""
    sql = """
    INSERT INTO operator_storage_data (
        operator_code, gas_day, gas_day_start, gas_day_end, status,
        gas_in_storage, full_percentage, trend, injection, withdrawal,
        net_withdrawal, working_gas_volume, injection_capacity, withdrawal_capacity,
        contracted_capacity, available_capacity, covered_capacity, updated_at_source
    ) VALUES (
        :operator_code, :gas_day, :gas_day_start, :gas_day_end, :status,
        :gas_in_storage, :full_percentage, :trend, :injection, :withdrawal,
        :net_withdrawal, :working_gas_volume, :injection_capacity, :withdrawal_capacity,
        :contracted_capacity, :available_capacity, :covered_capacity, :updated_at_source
    )
    ON CONFLICT(operator_code, gas_day) DO UPDATE SET
        gas_day_start = excluded.gas_day_start,
        gas_day_end = excluded.gas_day_end,
        status = excluded.status,
        gas_in_storage = excluded.gas_in_storage,
        full_percentage = excluded.full_percentage,
        trend = excluded.trend,
        injection = excluded.injection,
        withdrawal = excluded.withdrawal,
        net_withdrawal = excluded.net_withdrawal,
        working_gas_volume = excluded.working_gas_volume,
        injection_capacity = excluded.injection_capacity,
        withdrawal_capacity = excluded.withdrawal_capacity,
        contracted_capacity = excluded.contracted_capacity,
        available_capacity = excluded.available_capacity,
        covered_capacity = excluded.covered_capacity,
        updated_at_source = excluded.updated_at_source,
        scraped_at = CURRENT_TIMESTAMP;
    """
    db.executemany(sql, records)
    return len(records)


def upsert_facility_storage(db: DatabaseBackend, records: List[Dict[str, Any]]) -> int:
    """Inserts or updates facility storage time-series records."""
    sql = """
    INSERT INTO facility_storage_data (
        facility_code, gas_day, gas_day_start, gas_day_end, status,
        gas_in_storage, full_percentage, trend, injection, withdrawal,
        net_withdrawal, working_gas_volume, injection_capacity, withdrawal_capacity,
        contracted_capacity, available_capacity, updated_at_source
    ) VALUES (
        :facility_code, :gas_day, :gas_day_start, :gas_day_end, :status,
        :gas_in_storage, :full_percentage, :trend, :injection, :withdrawal,
        :net_withdrawal, :working_gas_volume, :injection_capacity, :withdrawal_capacity,
        :contracted_capacity, :available_capacity, :updated_at_source
    )
    ON CONFLICT(facility_code, gas_day) DO UPDATE SET
        gas_day_start = excluded.gas_day_start,
        gas_day_end = excluded.gas_day_end,
        status = excluded.status,
        gas_in_storage = excluded.gas_in_storage,
        full_percentage = excluded.full_percentage,
        trend = excluded.trend,
        injection = excluded.injection,
        withdrawal = excluded.withdrawal,
        net_withdrawal = excluded.net_withdrawal,
        working_gas_volume = excluded.working_gas_volume,
        injection_capacity = excluded.injection_capacity,
        withdrawal_capacity = excluded.withdrawal_capacity,
        contracted_capacity = excluded.contracted_capacity,
        available_capacity = excluded.available_capacity,
        updated_at_source = excluded.updated_at_source,
        scraped_at = CURRENT_TIMESTAMP;
    """
    db.executemany(sql, records)
    return len(records)


def save_parsed_dataset(db: DatabaseBackend, parsed: Dict[str, List[Dict[str, Any]]]) -> Dict[str, int]:
    """
    Persists all parsed dimensions and metrics in topological order.
    Returns a dictionary of counts per entity/table.
    """
    counts = {}
    try:
        # Dimensions in order: regions -> countries -> operators -> facilities
        if parsed.get("regions"):
            counts["regions"] = upsert_regions(db, parsed["regions"])
        if parsed.get("countries"):
            counts["countries"] = upsert_countries(db, parsed["countries"])
        if parsed.get("operators"):
            counts["operators"] = upsert_operators(db, parsed["operators"])
        if parsed.get("facilities"):
            counts["facilities"] = upsert_facilities(db, parsed["facilities"])

        # Metrics facts
        if parsed.get("region_storage"):
            counts["region_storage"] = upsert_region_storage(db, parsed["region_storage"])
        if parsed.get("country_storage"):
            counts["country_storage"] = upsert_country_storage(db, parsed["country_storage"])
        if parsed.get("operator_storage"):
            counts["operator_storage"] = upsert_operator_storage(db, parsed["operator_storage"])
        if parsed.get("facility_storage"):
            counts["facility_storage"] = upsert_facility_storage(db, parsed["facility_storage"])

        db.commit()
    except Exception as e:
        db.rollback()
        raise RuntimeError(f"Failed to save parsed dataset: {e}") from e

    return counts
