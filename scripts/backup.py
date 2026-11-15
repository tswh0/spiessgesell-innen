#!/usr/bin/env python3
"""Create a backup archive from the command line."""

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.backup import run  # noqa: E402

if __name__ == "__main__":
    data_dir = Path(os.environ.get("DATA_DIR", ROOT / "data")).resolve()
    backup_dir = Path(os.environ.get("BACKUP_DIR", data_dir / "backups")).resolve()
    keep = max(1, int(os.environ.get("BACKUP_KEEP", "14")))
    archive = run(data_dir, backup_dir, keep)
    if archive:
        print(f"backup written: {archive} ({archive.stat().st_size} bytes)")
