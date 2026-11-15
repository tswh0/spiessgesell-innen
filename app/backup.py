import asyncio
import logging
import os
import sqlite3
import zipfile
from datetime import datetime, timedelta
from pathlib import Path

try:
    import fcntl
except ImportError:  # pragma: no cover - the app runs on Linux
    fcntl = None

logger = logging.getLogger("spiessgesell.backup")


def _latest(backup_dir: Path) -> Path | None:
    files = sorted(backup_dir.glob("spiessgesell-innen-*.zip"))
    return files[-1] if files else None


def _is_stale(backup_dir: Path, max_age_hours: int = 24) -> bool:
    latest = _latest(backup_dir)
    if not latest:
        return True
    return (datetime.now() - datetime.fromtimestamp(latest.stat().st_mtime)) > timedelta(hours=max_age_hours)


def run(data_dir: Path, backup_dir: Path, keep: int = 14) -> Path | None:
    data_dir = data_dir.resolve()
    backup_dir = backup_dir.resolve()
    db_path = data_dir / "spiessgesell-innen.sqlite3"
    if not db_path.is_file():
        raise FileNotFoundError(f"database not found: {db_path}")

    backup_dir.mkdir(parents=True, exist_ok=True)
    lock_path = backup_dir / ".backup.lock"
    with lock_path.open("w") as lock:
        if fcntl is not None:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                logger.warning("backup already running")
                return None
        try:
            return _write_archive(data_dir, backup_dir, db_path, keep)
        finally:
            if fcntl is not None:
                fcntl.flock(lock, fcntl.LOCK_UN)


def _write_archive(data_dir: Path, backup_dir: Path, db_path: Path, keep: int) -> Path:
    stamp = datetime.now().strftime("%Y-%m-%d-%H%M%S")
    tmp_db = backup_dir / f".{stamp}.sqlite3.tmp"
    tmp_zip = backup_dir / f".{stamp}.zip.tmp"
    archive_path = backup_dir / f"spiessgesell-innen-{stamp}.zip"
    try:
        source = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        target = sqlite3.connect(tmp_db)
        try:
            source.backup(target)
        finally:
            source.close()
            target.close()

        with zipfile.ZipFile(tmp_zip, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.write(tmp_db, db_path.name)
            uploads = data_dir / "uploads"
            if uploads.is_dir():
                for path in sorted(uploads.rglob("*")):
                    if path.is_file():
                        archive.write(path, f"uploads/{path.relative_to(uploads)}")
        os.replace(tmp_zip, archive_path)
    finally:
        tmp_db.unlink(missing_ok=True)
        tmp_zip.unlink(missing_ok=True)

    for old in sorted(backup_dir.glob("spiessgesell-innen-*.zip"))[:-max(1, keep)]:
        old.unlink()
    logger.info("backup written: %s", archive_path)
    return archive_path


def _seconds_until(value: str) -> float:
    try:
        hour, minute = (int(part) for part in value.split(":", 1))
    except (ValueError, AttributeError):
        hour, minute = 3, 15
    now = datetime.now()
    target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if target <= now:
        target += timedelta(days=1)
    return (target - now).total_seconds()


async def scheduler(data_dir: Path, backup_dir: Path, keep: int, at: str, stop: asyncio.Event) -> None:
    try:
        if _is_stale(backup_dir):
            logger.info("no recent backup; creating one now")
            await asyncio.to_thread(run, data_dir, backup_dir, keep)
    except Exception:
        logger.exception("startup backup failed")

    while not stop.is_set():
        try:
            await asyncio.wait_for(stop.wait(), timeout=max(1, _seconds_until(at)))
            return
        except asyncio.TimeoutError:
            try:
                await asyncio.to_thread(run, data_dir, backup_dir, keep)
            except Exception:
                logger.exception("scheduled backup failed")
