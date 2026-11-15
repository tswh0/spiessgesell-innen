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

    @property
    def db_path(self) -> Path:
        return self.data_dir / "spiessgesell-innen.sqlite3"

    @property
    def uploads_dir(self) -> Path:
        return self.data_dir / "uploads"

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
    return Settings(
        data_dir=data_dir,
        secret_key=secret_key,
        shared_password=shared_password,
        base_url=base_url,
        categories_file=categories_file,
    )
