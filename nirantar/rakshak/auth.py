"""RAKSHAK: user accounts, roles, sessions and personal signing keys for the console.

Standard library plus ``cryptography`` (already a dependency), so it works on an
air-gapped node.

* **Passwords** are hashed with scrypt (salted, memory-hard); at least 12
  characters (a passphrase).
* **Each user has their own Ed25519 signing key.** The private key is stored
  encrypted with AES-GCM under a key derived from the user's password, so it
  can sign only while that user is logged in. Their decisions enter the ledger
  under their own name and key, not the server's.
* **Roles** follow the Action Authority Matrix (who may approve what) plus
  operational roles (technician, data steward, exercise control, administrator,
  viewer). The server checks them on every request; the browser only reflects them.
* **Sessions** live in server memory: a random token in an HttpOnly,
  SameSite=Strict cookie, 30 minutes idle and 10 hours absolute. A restart logs
  everyone out (and forgets the unlocked keys).
* **Lockout**: five failed logins lock the account for 15 minutes. Logins,
  failures, lockouts and account changes are kept in an audit table.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import sqlite3
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from nirantar.chanakya.plan_service import ROLES as DESK_ROLES
from nirantar.chitragupta.ledger import Signer

OTHER_ROLES = ("Technician", "Data steward", "Exercise control", "Administrator", "Viewer")
ALL_ROLES = tuple(DESK_ROLES) + OTHER_ROLES
# what each permission needs (any one of the roles)
PERMISSIONS = {
    "view": ALL_ROLES,
    "simulate": ALL_ROLES,
    "snag": ("Technician", "Logistics officer", "CEngO", "Exercise control"),
    "decide": tuple(DESK_ROLES),
    "plan": tuple(DESK_ROLES) + ("Exercise control",),
    "clock": ("Exercise control",),
    "data": ("Data steward", "Administrator"),
    "admin": ("Administrator",),
}
MIN_PASSWORD = 12
MAX_FAILS, LOCK_SECONDS = 5, 15 * 60
IDLE_SECONDS, ABSOLUTE_SECONDS = 30 * 60, 10 * 3600
SCRYPT = {"n": 2 ** 14, "r": 8, "p": 1, "dklen": 32}

DDL = """
CREATE TABLE IF NOT EXISTS users (
  username TEXT PRIMARY KEY, display TEXT NOT NULL, roles TEXT NOT NULL,
  pw_salt BLOB NOT NULL, pw_hash BLOB NOT NULL, key_salt BLOB NOT NULL, key_nonce BLOB NOT NULL,
  key_enc BLOB NOT NULL, key_pub TEXT NOT NULL, disabled INTEGER NOT NULL DEFAULT 0,
  failed INTEGER NOT NULL DEFAULT 0, locked_until REAL NOT NULL DEFAULT 0,
  created REAL NOT NULL, pw_changed REAL NOT NULL);
CREATE TABLE IF NOT EXISTS audit (
  id INTEGER PRIMARY KEY, ts REAL NOT NULL, username TEXT, event TEXT NOT NULL, detail TEXT, ip TEXT);
"""


class AuthError(Exception):
    """Login or permission refused (the message is safe to show)."""


def _kdf(password: str, salt: bytes) -> bytes:
    return hashlib.scrypt(password.encode("utf-8"), salt=salt, **SCRYPT)


def _fingerprint(pub_b64: str) -> str:
    return hashlib.sha256(base64.b64decode(pub_b64)).hexdigest()[:8]


@dataclass
class Session:
    token: str
    username: str
    display: str
    roles: tuple[str, ...]
    signer: Signer
    created: float = field(default_factory=time.time)
    last_seen: float = field(default_factory=time.time)
    ip: str = ""

    def can(self, permission: str) -> bool:
        return any(r in PERMISSIONS[permission] for r in self.roles)

    def view(self) -> dict:
        return {"username": self.username, "display": self.display, "roles": list(self.roles),
                "actor": self.signer.actor,
                "permissions": sorted(p for p in PERMISSIONS if self.can(p))}


class UserStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.con = sqlite3.connect(self.path, check_same_thread=False, isolation_level=None)
        self.con.execute("PRAGMA journal_mode=WAL")
        self.con.execute("PRAGMA busy_timeout=5000")
        self.con.executescript(DDL)
        self._lock = threading.Lock()
        self._sessions: dict[str, Session] = {}       # sha256(token) -> session

    # ------------------------------------------------------------ accounts
    @staticmethod
    def _check_password(password: str) -> None:
        if len(password) < MIN_PASSWORD:
            raise AuthError(f"use a passphrase of at least {MIN_PASSWORD} characters")

    @staticmethod
    def _check_roles(roles) -> list[str]:
        roles = [r.strip() for r in roles if r and r.strip()]
        bad = [r for r in roles if r not in ALL_ROLES]
        if bad or not roles:
            raise AuthError(f"unknown or missing roles {bad}; choose from {', '.join(ALL_ROLES)}")
        return roles

    def _seal_key(self, password: str, key: Ed25519PrivateKey) -> tuple[bytes, bytes, bytes]:
        salt, nonce = os.urandom(16), os.urandom(12)
        raw = key.private_bytes(serialization.Encoding.Raw, serialization.PrivateFormat.Raw,
                                serialization.NoEncryption())
        return salt, nonce, AESGCM(_kdf(password, salt)).encrypt(nonce, raw, b"nirantar-user-key")

    def create_user(self, username: str, password: str, roles, display: str | None = None, by: str = "cli") -> dict:
        username = username.strip().lower()
        if not username or not username.replace(".", "").replace("-", "").replace("_", "").isalnum():
            raise AuthError("username: letters, digits, dot, dash or underscore")
        roles = self._check_roles(roles)
        self._check_password(password)
        key = Ed25519PrivateKey.generate()
        pub = base64.b64encode(key.public_key().public_bytes(serialization.Encoding.Raw,
                                                             serialization.PublicFormat.Raw)).decode()
        pw_salt = os.urandom(16)
        k_salt, nonce, enc = self._seal_key(password, key)
        now = time.time()
        with self._lock:
            try:
                self.con.execute("INSERT INTO users(username, display, roles, pw_salt, pw_hash, key_salt, key_nonce,"
                                 " key_enc, key_pub, created, pw_changed) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                                 (username, display or username, json.dumps(roles), pw_salt, _kdf(password, pw_salt),
                                  k_salt, nonce, enc, pub, now, now))
            except sqlite3.IntegrityError:
                raise AuthError(f"user {username} already exists") from None
        self.audit(by, "user_created", f"{username} roles={roles}")
        return self.user(username)

    def user(self, username: str) -> dict:
        r = self.con.execute("SELECT username, display, roles, key_pub, disabled, failed, locked_until, created, "
                             "pw_changed FROM users WHERE username = ?", (username,)).fetchone()
        if not r:
            raise AuthError(f"no user {username}")
        return {"username": r[0], "display": r[1], "roles": json.loads(r[2]), "actor": f"{r[0]}@{_fingerprint(r[3])}",
                "disabled": bool(r[4]), "failed": r[5], "locked": r[6] > time.time(), "created": r[7],
                "pw_changed": r[8]}

    def users(self) -> list[dict]:
        return [self.user(u) for (u,) in self.con.execute("SELECT username FROM users ORDER BY username")]

    def set_roles(self, username: str, roles, by: str = "cli") -> dict:
        roles = self._check_roles(roles)
        self.con.execute("UPDATE users SET roles = ? WHERE username = ?", (json.dumps(roles), username))
        self._drop_sessions(username)
        self.audit(by, "roles_changed", f"{username} roles={roles}")
        return self.user(username)

    def set_disabled(self, username: str, disabled: bool, by: str = "cli") -> dict:
        self.user(username)
        self.con.execute("UPDATE users SET disabled = ?, failed = 0, locked_until = 0 WHERE username = ?",
                         (int(disabled), username))
        if disabled:
            self._drop_sessions(username)
        self.audit(by, "disabled" if disabled else "enabled", username)
        return self.user(username)

    def change_password(self, username: str, old: str, new: str) -> None:
        """The user's own change: the same signing key, re-sealed under the new password."""
        key = self._unlock(username, old)
        self._check_password(new)
        pw_salt = os.urandom(16)
        k_salt, nonce, enc = self._seal_key(new, key)
        self.con.execute("UPDATE users SET pw_salt=?, pw_hash=?, key_salt=?, key_nonce=?, key_enc=?, pw_changed=? "
                         "WHERE username=?", (pw_salt, _kdf(new, pw_salt), k_salt, nonce, enc, time.time(), username))
        self.audit(username, "password_changed", "")

    def reset_password(self, username: str, new: str, by: str = "cli") -> dict:
        """An administrator's reset: the old key cannot be recovered, so the user gets a new key (and a new
        actor name in the ledger; entries signed with the old key still verify)."""
        self.user(username)
        self._check_password(new)
        key = Ed25519PrivateKey.generate()
        pub = base64.b64encode(key.public_key().public_bytes(serialization.Encoding.Raw,
                                                             serialization.PublicFormat.Raw)).decode()
        pw_salt = os.urandom(16)
        k_salt, nonce, enc = self._seal_key(new, key)
        self.con.execute("UPDATE users SET pw_salt=?, pw_hash=?, key_salt=?, key_nonce=?, key_enc=?, key_pub=?, "
                         "pw_changed=?, failed=0, locked_until=0 WHERE username=?",
                         (pw_salt, _kdf(new, pw_salt), k_salt, nonce, enc, pub, time.time(), username))
        self._drop_sessions(username)
        self.audit(by, "password_reset", f"{username}: new signing key {_fingerprint(pub)}")
        return self.user(username)

    def _unlock(self, username: str, password: str) -> Ed25519PrivateKey:
        r = self.con.execute("SELECT pw_salt, pw_hash, key_salt, key_nonce, key_enc FROM users WHERE username=?",
                             (username,)).fetchone()
        if not r or not hmac.compare_digest(_kdf(password, r[0]), r[1]):
            raise AuthError("wrong username or password")
        raw = AESGCM(_kdf(password, r[2])).decrypt(r[3], r[4], b"nirantar-user-key")
        return Ed25519PrivateKey.from_private_bytes(raw)

    # ------------------------------------------------------------ sessions
    def login(self, username: str, password: str, ip: str = "") -> tuple[str, Session]:
        username = (username or "").strip().lower()
        row = self.con.execute("SELECT display, roles, disabled, failed, locked_until, key_pub FROM users "
                               "WHERE username = ?", (username,)).fetchone()
        if row is None:
            _kdf(password or "", b"0" * 16)                 # same work as a real check: no user enumeration by timing
            self.audit(username, "login_failed", "unknown user", ip)
            raise AuthError("wrong username or password")
        display, roles, disabled, failed, locked_until, pub = row
        if disabled:
            self.audit(username, "login_refused", "disabled", ip)
            raise AuthError("this account is disabled")
        if locked_until > time.time():
            self.audit(username, "login_refused", "locked", ip)
            raise AuthError("too many failed attempts; try again later")
        try:
            key = self._unlock(username, password or "")
        except AuthError:
            failed += 1
            lock = time.time() + LOCK_SECONDS if failed >= MAX_FAILS else 0
            self.con.execute("UPDATE users SET failed = ?, locked_until = ? WHERE username = ?",
                             (0 if lock else failed, lock, username))
            self.audit(username, "locked" if lock else "login_failed", "", ip)
            raise
        self.con.execute("UPDATE users SET failed = 0, locked_until = 0 WHERE username = ?", (username,))
        token = secrets.token_urlsafe(32)
        s = Session(token, username, display, tuple(json.loads(roles)),
                    Signer(f"{username}@{_fingerprint(pub)}", key), ip=ip)
        with self._lock:
            self._sessions[hashlib.sha256(token.encode()).hexdigest()] = s
        self.audit(username, "login", "", ip)
        return token, s

    def session(self, token: str | None) -> Session | None:
        if not token:
            return None
        h = hashlib.sha256(token.encode()).hexdigest()
        now = time.time()
        with self._lock:
            s = self._sessions.get(h)
            if s is None:
                return None
            if now - s.last_seen > IDLE_SECONDS or now - s.created > ABSOLUTE_SECONDS:
                del self._sessions[h]
                return None
            s.last_seen = now
            return s

    def logout(self, token: str | None) -> None:
        if not token:
            return
        with self._lock:
            s = self._sessions.pop(hashlib.sha256(token.encode()).hexdigest(), None)
        if s:
            self.audit(s.username, "logout", "", s.ip)

    def _drop_sessions(self, username: str) -> None:
        with self._lock:
            for h in [h for h, s in self._sessions.items() if s.username == username]:
                del self._sessions[h]

    # ------------------------------------------------------------ audit
    def audit(self, username: str | None, event: str, detail: str = "", ip: str = "") -> None:
        self.con.execute("INSERT INTO audit(ts, username, event, detail, ip) VALUES (?,?,?,?,?)",
                         (time.time(), username, event, detail[:300], ip[:64]))

    def audit_log(self, limit: int = 200) -> list[dict]:
        rows = self.con.execute("SELECT ts, username, event, detail, ip FROM audit ORDER BY id DESC LIMIT ?", (limit,))
        return [{"ts": r[0], "username": r[1], "event": r[2], "detail": r[3], "ip": r[4]} for r in rows]
