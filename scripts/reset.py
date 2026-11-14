#!/usr/bin/env python3
"""Clear demo data. --reviews deletes all reviews, --all also deletes shops."""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import db
from app.config import load


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--reviews", action="store_true")
    parser.add_argument("--all", action="store_true")
    args = parser.parse_args()
    if not (args.reviews or args.all):
        parser.error("choose --reviews or --all")

    settings = load()
    db.init_db(settings)
    conn = db.connect(settings.db_path)
    try:
        for row in conn.execute("SELECT file, thumb FROM review_images").fetchall():
            for path in (
                settings.uploads_dir / row["file"],
                settings.uploads_dir / "thumbs" / row["thumb"],
            ):
                if path.exists():
                    path.unlink()
        conn.execute("DELETE FROM reviews")
        if args.all:
            conn.execute("DELETE FROM shops")
        conn.commit()
        print("reviews cleared" + (" and shops removed" if args.all else ""))
    finally:
        conn.close()


if __name__ == "__main__":
    main()
