"""
Harmonoid Wrapped — Reset stats
Clears all listening history but keeps the database file/structure intact.
Run: python reset_stats.py
"""
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent / "harmonoid_stats.db"

if not DB_PATH.exists():
    print("No database found — nothing to reset.")
else:
    confirm = input("This will permanently delete ALL your listening stats. Type 'yes' to confirm: ")
    if confirm.strip().lower() == "yes":
        conn = sqlite3.connect(DB_PATH)
        conn.execute("DELETE FROM plays")
        conn.commit()
        conn.execute("VACUUM")
        conn.close()
        print("✓ Stats reset. Starting fresh!")
    else:
        print("Cancelled. Your stats are untouched.")
