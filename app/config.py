import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    secret_key: str
    shared_password: str
    base_url: str
    categories_file: Path
    backup_enabled: bool = False
    backup_dir: Path | None = None
    backup_keep: int = 14
    backup_at: str = "03:15"

    @property
    def db_path(self) -> Path:
        return self.data_dir / "spiessgesell-innen.sqlite3"

    @property
    def uploads_dir(self) -> Path:
        return self.data_dir / "uploads"

    @property
    def effective_backup_dir(self) -> Path:
        return self.backup_dir or self.data_dir / "backups"

    @property
    def secure_cookies(self) -> bool:
        return self.base_url.startswith("https://")


def load() -> Settings:
    root = Path(__file__).resolve().parent.parent
    data_dir = Path(os.environ.get("DATA_DIR", root / "data")).resolve()
    categories_file = Path(
        os.environ.get("CATEGORIES_FILE", root / "seed" / "categories.yaml")
    ).resolve()
    secret_key = os.environ.get("SECRET_KEY", "dev-only-change-me")
    shared_password = os.environ.get("SHARED_PASSWORD", "doener")
    base_url = os.environ.get("BASE_URL", "http://127.0.0.1:8090")
    if base_url.startswith("https://") and (
        secret_key == "dev-only-change-me" or shared_password == "doener"
    ):
        raise RuntimeError("Set SECRET_KEY and SHARED_PASSWORD before serving over HTTPS.")
    backup_enabled = os.environ.get("BACKUP_ENABLED", "").lower() in ("1", "true", "yes", "on")
    backup_dir = Path(os.environ.get("BACKUP_DIR", data_dir / "backups")).resolve()
    try:
        backup_keep = max(1, int(os.environ.get("BACKUP_KEEP", "14")))
    except ValueError:
        backup_keep = 14
    return Settings(
        data_dir=data_dir,
        secret_key=secret_key,
        shared_password=shared_password,
        base_url=base_url,
        categories_file=categories_file,
        backup_enabled=backup_enabled,
        backup_dir=backup_dir,
        backup_keep=backup_keep,
        backup_at=os.environ.get("BACKUP_AT", "03:15"),
    )
