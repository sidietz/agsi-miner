"""
Unit and integration tests for AGSI Gas Storage Miner.
"""

import os
import unittest
import sqlite3
from db import get_db, init_db, save_parsed_dataset
from parser import parse_html_file, parse_live_api, to_float, parse_date_string


class TestAGSIMiner(unittest.TestCase):
    def setUp(self):
        # Use an in-memory SQLite database via get_db
        self.db = get_db(db_type="sqlite", db_path=":memory:")
        init_db(self.db)

    def tearDown(self):
        self.db.close()

    def test_schema_creation(self):
        """Verifies that all 4 dimension tables, 4 facts tables, and views exist."""
        cursor = self.db.cursor()
        cursor.execute("SELECT name, type FROM sqlite_master WHERE type IN ('table', 'view');")
        objects = {row[0]: row[1] for row in cursor.fetchall()}

        expected_tables = [
            "regions", "countries", "operators", "facilities",
            "region_storage_data", "country_storage_data",
            "operator_storage_data", "facility_storage_data"
        ]
        expected_views = [
            "v_operator_rollup", "v_country_rollup",
            "v_country_audit", "v_facility_overview"
        ]

        for tbl in expected_tables:
            self.assertIn(tbl, objects, f"Missing table: {tbl}")
            self.assertEqual(objects[tbl], "table")

        for vw in expected_views:
            self.assertIn(vw, objects, f"Missing view: {vw}")
            self.assertEqual(objects[vw], "view")

    def test_helpers(self):
        """Tests parsing helpers."""
        self.assertEqual(to_float("123.45"), 123.45)
        self.assertEqual(to_float("-"), None)
        self.assertEqual(to_float(""), None)
        self.assertEqual(to_float(None), None)
        self.assertEqual(to_float("1 234.56"), 1234.56)

        date_str = "Saturday 26th September, 2026 - Sunday 27th September, 2026"
        self.assertEqual(parse_date_string(date_str), "2026-09-26")
        self.assertEqual(parse_date_string("2026-09-26"), "2026-09-26")

    def test_parse_local_html_and_ingest(self):
        """Tests parsing the local HTML snapshot and saving to database."""
        html_file = "Gas Infrastructure Europe - AGSI.html"
        if not os.path.exists(html_file):
            self.skipTest(f"{html_file} not found")

        parsed = parse_html_file(html_file)
        self.assertEqual(len(parsed["regions"]), 2)
        self.assertEqual(len(parsed["countries"]), 23)
        self.assertGreater(len(parsed["operators"]), 10)
        self.assertGreater(len(parsed["facilities"]), 0)

        # Ingest into in-memory DB
        counts = save_parsed_dataset(self.db, parsed)
        self.assertEqual(counts["regions"], 2)
        self.assertEqual(counts["countries"], 23)

        cursor = self.db.cursor()
        cursor.execute("SELECT * FROM country_storage_data WHERE country_code = 'DE';")
        de_row = cursor.fetchone()
        self.assertIsNotNone(de_row)
        self.assertGreater(de_row["gas_in_storage"], 100.0)

        # Test view execution
        cursor.execute("SELECT * FROM v_country_audit WHERE country_code = 'DE';")
        audit_row = cursor.fetchone()
        self.assertIsNotNone(audit_row)
        self.assertEqual(audit_row["country_name"], "Germany")

    def test_mock_live_api_ingest(self):
        """Tests parsing a synthetic API JSON response."""
        mock_payload = {
            "data": [
                {
                    "name": "EU",
                    "gasDayStart": "2026-09-25",
                    "gasDayEnd": "2026-09-26",
                    "gasInStorage": "100.0",
                    "workingGasVolume": "120.0",
                    "full": "83.33",
                    "injection": "10.0",
                    "withdrawal": "2.0",
                    "netWithdrawal": "-8.0",
                    "status": "C",
                    "children": [
                        {
                            "code": "DE",
                            "name": "Germany",
                            "gasInStorage": "50.0",
                            "workingGasVolume": "60.0",
                            "full": "83.33",
                            "injection": "5.0",
                            "withdrawal": "1.0",
                            "netWithdrawal": "-4.0",
                            "consumption": "850.0",
                            "consumptionFull": "5.88",
                            "coveredCapacity": "100.0",
                            "status": "C",
                            "children": [
                                {
                                    "code": "OP1",
                                    "name": "Operator One",
                                    "gasInStorage": "50.0",
                                    "workingGasVolume": "60.0",
                                    "full": "83.33",
                                    "status": "C",
                                    "children": [
                                        {
                                            "code": "FAC1",
                                            "name": "Facility One",
                                            "gasInStorage": "50.0",
                                            "workingGasVolume": "60.0",
                                            "full": "83.33",
                                            "status": "C",
                                            "type": "DSR",
                                            "latitude": "52.5",
                                            "longitude": "13.4"
                                        }
                                    ]
                                }
                            ]
                        }
                    ]
                }
            ]
        }

        parsed = parse_live_api(mock_payload)
        self.assertEqual(len(parsed["regions"]), 1)
        self.assertEqual(len(parsed["countries"]), 1)
        self.assertEqual(len(parsed["operators"]), 1)
        self.assertEqual(len(parsed["facilities"]), 1)

        counts = save_parsed_dataset(self.db, parsed)
        self.assertEqual(counts["regions"], 1)
        self.assertEqual(counts["countries"], 1)
        self.assertEqual(counts["operators"], 1)
        self.assertEqual(counts["facilities"], 1)

        cursor = self.db.cursor()
        cursor.execute("SELECT * FROM v_facility_overview WHERE facility_code = 'FAC1';")
        fac_row = cursor.fetchone()
        self.assertIsNotNone(fac_row)
        self.assertEqual(fac_row["country_name"], "Germany")
        self.assertEqual(fac_row["operator_name"], "Operator One")
        self.assertEqual(fac_row["facility_type"], "DSR")
        self.assertEqual(fac_row["gas_in_storage"], 50.0)

    def test_bulk_import_date_parsing(self):
        """Tests date parsing helper in bulk_import."""
        from datetime import date
        import bulk_import
        d = bulk_import.parse_date("2026-09-24")
        self.assertEqual(d, date(2026, 9, 24))
        with self.assertRaises(Exception):
            bulk_import.parse_date("invalid-date")


if __name__ == "__main__":
    unittest.main()
