#!/usr/bin/env python3
"""Delete fleet_health rows older than 7 days."""

import sqlite3
import os

DB_PATH = os.path.expanduser("~/agent-stack/data/metrics.db")

def cleanup():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.execute(
        "DELETE FROM fleet_health WHERE timestamp < datetime('now', '-7 days')"
    )
    deleted = cursor.rowcount
    conn.commit()
    conn.close()
    if deleted > 0:
        print(f"Deleted {deleted} fleet_health rows older than 7 days")

if __name__ == "__main__":
    cleanup()
