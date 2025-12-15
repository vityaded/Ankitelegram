from __future__ import annotations
import sqlite3
from pathlib import Path

def iter_notes(collection_path: Path):
    conn = sqlite3.connect(str(collection_path))
    try:
        cur = conn.cursor()
        cur.execute("SELECT guid, flds FROM notes")
        for guid, flds in cur.fetchall():
            yield str(guid), str(flds)
    finally:
        conn.close()
