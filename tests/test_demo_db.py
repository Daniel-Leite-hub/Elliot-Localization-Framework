"""
Unit tests for the Seed Demo Database and Schema
"""

import json
import sqlite3
import unittest
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]


class TestDemoDatabase(unittest.TestCase):
    def setUp(self):
        self.db_path = BASE_DIR / "data" / "demo_project.sqlite"
        if not self.db_path.exists():
            from data.seed_demo import create_demo_database

            create_demo_database()

    def test_database_integrity_pragma(self):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("PRAGMA integrity_check;")
        status = cursor.fetchone()[0]
        self.assertEqual(status.lower(), "ok")
        conn.close()

    def test_settings_populated(self):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT value FROM settings WHERE key = 'source_language'")
        val = cursor.fetchone()
        self.assertIsNotNone(val)
        self.assertEqual(json.loads(val[0]), "EN")
        conn.close()

    def test_entries_count_and_state(self):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM entries WHERE approved IS NOT NULL")
        count = cursor.fetchone()[0]
        self.assertGreater(count, 0)
        conn.close()


if __name__ == "__main__":
    unittest.main()
