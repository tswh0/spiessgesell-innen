import hmac
import re
import secrets
import time

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
    def __init__(self, limit: int = 8, window: int = 600):
        self.limit = limit
        self.window = window
        self._hits: dict[str, tuple[int, float]] = {}

    def blocked(self, key: str) -> bool:
        count, reset = self._hits.get(key, (0, 0.0))
        if time.monotonic() > reset:
            return False
        return count >= self.limit

    def fail(self, key: str) -> None:
        count, reset = self._hits.get(key, (0, 0.0))
        now = time.monotonic()
        if now > reset:
            count, reset = 0, now + self.window
        self._hits[key] = (count + 1, reset)

    def reset(self, key: str) -> None:
        self._hits.pop(key, None)
