"""Create a consistent SQLite backup in the persistent game volume.

Run inside the server container: python backup_db.py
The backup contains player data and must stay private.
"""

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from main import DB


def backup(source: Path = DB) -> Path:
    if not source.is_file():
        raise FileNotFoundError(f"Game database does not exist: {source}")
    folder = source.parent / "backups"
    folder.mkdir(mode=0o700, exist_ok=True)
    destination = folder / f"chaos-{datetime.now(timezone.utc):%Y%m%d-%H%M%S-%f}.db"
    with sqlite3.connect(source) as active, sqlite3.connect(destination) as copy:
        active.backup(copy)
        if copy.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise RuntimeError("Backup integrity check failed")
        cities = copy.execute("SELECT COUNT(*) FROM cities").fetchone()[0]
    destination.chmod(0o600)
    print(f"Backup ready: {destination} ({cities} cities)")
    return destination


if __name__ == "__main__":
    backup()
