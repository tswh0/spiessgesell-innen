#!/usr/bin/env python3
"""Create a consistent SQLite + uploads archive and keep the newest copies."""

import os
import sqlite3
import sys
import time
import zipfile
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def run() -> Path:
    data_dir = Path(os.environ.get("DATA_DIR", ROOT / "data")).resolve()
    backup_dir = Path(os.environ.get("BACKUP_DIR", data_dir / "backups")).resolve()
    keep = max(1, int(os.environ.get("BACKUP_KEEP", "14")))
    db_path = data_dir / "spiessgesell-innen.sqlite3"
    if not db_path.is_file():
        raise SystemExit(f"database not found: {db_path}")

    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%d-%H%M%S")
    tmp_db = backup_dir / f".{stamp}.sqlite3.tmp"
    archive_path = backup_dir / f"spiessgesell-innen-{stamp}.zip"

    try:
        source = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        target = sqlite3.connect(tmp_db)
        try:
            source.backup(target)
        finally:
            source.close()
            target.close()

        with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.write(tmp_db, db_path.name)
            uploads = data_dir / "uploads"
            if uploads.is_dir():
                for path in sorted(uploads.rglob("*")):
                    if path.is_file():
                        archive.write(path, f"uploads/{path.relative_to(uploads)}")
    finally:
        tmp_db.unlink(missing_ok=True)

    for old in sorted(backup_dir.glob("spiessgesell-innen-*.zip"))[:-keep]:
        old.unlink()
    print(f"backup written: {archive_path} ({archive_path.stat().st_size} bytes)")
    return archive_path


def loop() -> None:
    while True:
        try:
            run()
        except Exception as exc:
            print(f"backup failed: {exc}", file=sys.stderr)
        now = datetime.now()
        next_run = now.replace(hour=3, minute=15, second=0, microsecond=0)
        if next_run <= now:
            next_run += timedelta(days=1)
        time.sleep((next_run - now).total_seconds())


if __name__ == "__main__":
    if "--loop" in sys.argv:
        loop()
    else:
        run()
