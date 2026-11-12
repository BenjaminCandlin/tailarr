"""Optional login, and protection against requests from other websites.

**Login** (off by default): one username and password, set in Settings. Passwords are
stored only as a salted scrypt hash in the database. A successful login gets a random
session token in an HttpOnly, SameSite=Strict cookie (kept 30 days); only a hash of the
token is stored. Repeated wrong passwords from one address are slowed down.
If the owner forgets the password, starting the container once with
``TAILARR_DISABLE_LOGIN=1`` switches the login off.

**Cross-site protection** (always on): every request that changes something must carry
the ``X-Requested-With: tailarr`` header, which Tailarr's own page always sends and other
websites can't add without permission the server never gives. Radarr/Sonarr webhooks are
exempt: they carry their own secret instead.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import threading
import time
from dataclasses import dataclass, field

from pydantic import BaseModel
from sqlmodel import Field, Session, SQLModel, select

from .db import Setting

LOGIN_KEY = "login"
COOKIE = "tailarr_session"
SESSION_DAYS = 30
CSRF_HEADER = "x-requested-with"
CSRF_VALUE = "tailarr"
MAX_FAILURES = 5
FAILURE_WINDOW = 10 * 60
LOCKOUT = 5 * 60
MIN_PASSWORD = 8

# Addresses that never need a login: the Docker health check, webhooks (own secret),
# and logging in itself.
OPEN_PATHS = ("/api/ping", "/api/webhooks/", "/api/auth/")


class LoginSettings(BaseModel):
    enabled: bool = False
    username: str = ""
    password_hash: str = ""


class LoginSession(SQLModel, table=True):
    token_hash: str = Field(primary_key=True)
    created_at: float
    expires_at: float


def hash_password(password: str, salt: bytes | None = None) -> str:
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1, dklen=32)
    return f"scrypt${salt.hex()}${digest.hex()}"


def check_password(password: str, stored: str) -> bool:
    try:
        kind, salt, digest = stored.split("$")
    except ValueError:
        return False
    if kind != "scrypt":
        return False
    candidate = hash_password(password, bytes.fromhex(salt)).split("$")[2]
    return hmac.compare_digest(candidate, digest)


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def get_login(session: Session) -> LoginSettings:
    row = session.get(Setting, LOGIN_KEY)
    return LoginSettings() if row is None else LoginSettings.model_validate(json.loads(row.value))


def save_login(session: Session, settings: LoginSettings) -> LoginSettings:
    session.merge(Setting(key=LOGIN_KEY, value=settings.model_dump_json()))
    session.commit()
    return settings


def new_session(session: Session) -> str:
    token = secrets.token_urlsafe(32)
    now = time.time()
    session.add(
        LoginSession(
            token_hash=_token_hash(token), created_at=now, expires_at=now + SESSION_DAYS * 86400
        )
    )
    # Forget expired sessions while we're here.
    for old in session.exec(select(LoginSession).where(LoginSession.expires_at < now)).all():
        session.delete(old)
    session.commit()
    return token


def valid_session(session: Session, token: str | None) -> bool:
    if not token:
        return False
    row = session.get(LoginSession, _token_hash(token))
    return row is not None and row.expires_at > time.time()


def end_session(session: Session, token: str | None) -> None:
    if token:
        row = session.get(LoginSession, _token_hash(token))
        if row is not None:
            session.delete(row)
            session.commit()


def end_all_sessions(session: Session) -> None:
    for row in session.exec(select(LoginSession)).all():
        session.delete(row)
    session.commit()


@dataclass
class FailedLogins:
    """Wrong passwords per address, to slow down guessing."""

    _lock: threading.Lock = field(default_factory=threading.Lock)
    _failures: dict[str, list[float]] = field(default_factory=dict)

    def locked_for(self, address: str) -> int:
        """Seconds until this address may try again (0: it may try now)."""
        now = time.time()
        with self._lock:
            recent = [t for t in self._failures.get(address, []) if now - t < FAILURE_WINDOW]
            self._failures[address] = recent
            if len(recent) >= MAX_FAILURES:
                return max(0, int(recent[-1] + LOCKOUT - now) + 1)
        return 0

    def failed(self, address: str) -> None:
        with self._lock:
            self._failures.setdefault(address, []).append(time.time())

    def succeeded(self, address: str) -> None:
        with self._lock:
            self._failures.pop(address, None)
