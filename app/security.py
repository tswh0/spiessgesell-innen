import hmac
import re
import secrets
import sqlite3
import time
from pathlib import Path

from argon2 import PasswordHasher
from argon2.exceptions import VerificationError, VerifyMismatchError
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

NAME_RE = re.compile(r"^[\w .'’\-]{1,40}$", re.UNICODE)


class Auth:
    def __init__(self, password: str, secret: str):
        self._hasher = PasswordHasher()
        self._hash = self._hasher.hash(password)
        self._serializer = URLSafeTimedSerializer(secret, salt="spiessgesell-innen")

    def check_password(self, password: str) -> bool:
        try:
            return self._hasher.verify(self._hash, password)
        except (VerifyMismatchError, VerificationError):
            return False

    def sign(self, value) -> str:
        return self._serializer.dumps(value)

    def unsign(self, token: str, max_age: int):
        try:
            return self._serializer.loads(token, max_age=max_age)
        except (BadSignature, SignatureExpired):
            return None


def clean_name(raw: str) -> str | None:
    name = " ".join((raw or "").split())
    if not NAME_RE.fullmatch(name):
        return None
    if name.lower() in {"admin", "hermes"}:
        return None
    return name


def new_csrf() -> str:
    return secrets.token_urlsafe(24)


def csrf_ok(cookie: str | None, submitted: str | None) -> bool:
    if not cookie or not submitted:
        return False
    return hmac.compare_digest(cookie, submitted)


class LoginLimiter:
    def __init__(self, db_path: Path, limit: int = 8, window: int = 600):
        self.db_path = db_path
        self.limit = limit
        self.window = window
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS login_attempts (
                    key       TEXT PRIMARY KEY,
                    failures  INTEGER NOT NULL,
                    reset_at  REAL NOT NULL
                )
                """
            )

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=5)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA busy_timeout = 5000")
        return conn

    def blocked(self, key: str) -> bool:
        now = time.time()
        with self._connect() as conn:
            row = conn.execute(
                "SELECT failures, reset_at FROM login_attempts WHERE key = ?", (key,)
            ).fetchone()
            if not row:
                return False
            if row["reset_at"] <= now:
                conn.execute("DELETE FROM login_attempts WHERE key = ?", (key,))
                return False
            return row["failures"] >= self.limit

    def fail(self, key: str) -> None:
        now = time.time()
        with self._connect() as conn:
            row = conn.execute(
                "SELECT failures, reset_at FROM login_attempts WHERE key = ?", (key,)
            ).fetchone()
            if not row or row["reset_at"] <= now:
                conn.execute(
                    """
                    INSERT INTO login_attempts (key, failures, reset_at) VALUES (?, 1, ?)
                    ON CONFLICT(key) DO UPDATE SET failures = 1, reset_at = excluded.reset_at
                    """,
                    (key, now + self.window),
                )
            else:
                conn.execute(
                    "UPDATE login_attempts SET failures = failures + 1 WHERE key = ?", (key,)
                )

    def reset(self, key: str) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM login_attempts WHERE key = ?", (key,))
