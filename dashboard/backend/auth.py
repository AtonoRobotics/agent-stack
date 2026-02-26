# Mission Control - Proprietary Software
# © 2026 Alpha. All rights reserved.
# Unauthorized use or distribution prohibited.
"""Authentication and authorization for Mission Control."""

import os
import json
import secrets
import sqlite3
import fcntl
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

DATA_DIR = os.path.expanduser("~/agent-stack/data")
CONFIG_DIR = os.path.expanduser("~/agent-stack/config")
USERS_FILE = os.path.join(DATA_DIR, "users.json")
API_KEYS_FILE = os.path.join(DATA_DIR, "api_keys.json")
SECRETS_FILE = os.path.join(CONFIG_DIR, "secrets.yml")
DB_PATH = os.path.join(DATA_DIR, "metrics.db")

ALGORITHM = "HS256"
TOKEN_EXPIRE_HOURS = 24
VALID_ROLES = ("admin", "operator", "viewer")

CREATE_AUDIT_TABLE = """
CREATE TABLE IF NOT EXISTS audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    event TEXT NOT NULL,
    username TEXT,
    ip TEXT,
    details TEXT
)
"""


class AuthManager:
    def __init__(self):
        os.makedirs(DATA_DIR, exist_ok=True)
        os.makedirs(CONFIG_DIR, exist_ok=True)
        self.jwt_secret = self._load_or_create_secret()
        self._revoked_tokens: set[str] = set()
        self._ensure_audit_table()

    # ── Secrets ──────────────────────────────────────────

    def _load_or_create_secret(self) -> str:
        if os.path.exists(SECRETS_FILE):
            with open(SECRETS_FILE) as f:
                for line in f:
                    if line.startswith("jwt_secret:"):
                        return line.split(":", 1)[1].strip()
        secret = secrets.token_hex(32)
        with open(SECRETS_FILE, "w") as f:
            f.write(f"jwt_secret: {secret}\n")
            f.write(f"created: {datetime.now(timezone.utc).isoformat()}\n")
        os.chmod(SECRETS_FILE, 0o600)
        return secret

    # ── Password hashing ─────────────────────────────────

    def hash_password(self, password: str) -> str:
        return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

    def verify_password(self, password: str, hashed: str) -> bool:
        return bcrypt.checkpw(password.encode(), hashed.encode())

    # ── JWT tokens ───────────────────────────────────────

    def create_token(self, username: str, role: str) -> str:
        now = datetime.now(timezone.utc)
        payload = {
            "sub": username,
            "role": role,
            "iat": now,
            "exp": now + timedelta(hours=TOKEN_EXPIRE_HOURS),
            "jti": secrets.token_hex(16),
        }
        return jwt.encode(payload, self.jwt_secret, algorithm=ALGORITHM)

    def verify_token(self, token: str) -> dict | None:
        try:
            payload = jwt.decode(token, self.jwt_secret, algorithms=[ALGORITHM])
            if payload.get("jti") in self._revoked_tokens:
                return None
            return {"username": payload["sub"], "role": payload["role"], "jti": payload["jti"]}
        except jwt.InvalidTokenError:
            return None

    def revoke_token(self, jti: str):
        self._revoked_tokens.add(jti)

    # ── User CRUD (JSON file) ────────────────────────────

    def _read_users(self) -> dict:
        if not os.path.exists(USERS_FILE):
            return {}
        with open(USERS_FILE) as f:
            fcntl.flock(f, fcntl.LOCK_SH)
            data = json.load(f)
            fcntl.flock(f, fcntl.LOCK_UN)
        return data

    def _write_users(self, users: dict):
        with open(USERS_FILE, "w") as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            json.dump(users, f, indent=2)
            fcntl.flock(f, fcntl.LOCK_UN)
        os.chmod(USERS_FILE, 0o600)

    def get_user(self, username: str) -> dict | None:
        users = self._read_users()
        return users.get(username)

    def list_users(self) -> list[dict]:
        users = self._read_users()
        return [
            {"username": u, "role": d["role"], "created": d.get("created", ""), "created_by": d.get("created_by", "")}
            for u, d in users.items()
        ]

    def create_user(self, username: str, password: str, role: str, created_by: str = "system") -> bool:
        if role not in VALID_ROLES:
            raise ValueError(f"Invalid role: {role}")
        users = self._read_users()
        if username in users:
            raise ValueError(f"User '{username}' already exists")
        users[username] = {
            "password_hash": self.hash_password(password),
            "role": role,
            "created": datetime.now(timezone.utc).isoformat(),
            "created_by": created_by,
        }
        self._write_users(users)
        return True

    def delete_user(self, username: str) -> bool:
        users = self._read_users()
        if username not in users:
            raise ValueError(f"User '{username}' not found")
        del users[username]
        self._write_users(users)
        return True

    def verify_credentials(self, username: str, password: str) -> dict | None:
        user = self.get_user(username)
        if user and self.verify_password(password, user["password_hash"]):
            return {"username": username, "role": user["role"]}
        return None

    # ── API keys ─────────────────────────────────────────

    def _read_api_keys(self) -> dict:
        if not os.path.exists(API_KEYS_FILE):
            return {}
        with open(API_KEYS_FILE) as f:
            return json.load(f)

    def _write_api_keys(self, keys: dict):
        with open(API_KEYS_FILE, "w") as f:
            json.dump(keys, f, indent=2)
        os.chmod(API_KEYS_FILE, 0o600)

    def create_api_key(self, name: str, role: str, created_by: str = "system") -> str:
        if role not in VALID_ROLES:
            raise ValueError(f"Invalid role: {role}")
        raw_key = "mc_ak_" + secrets.token_urlsafe(32)
        key_id = raw_key[6:14]  # first 8 chars after prefix for O(1) lookup
        keys = self._read_api_keys()
        keys[key_id] = {
            "hash": self.hash_password(raw_key),
            "name": name,
            "role": role,
            "created": datetime.now(timezone.utc).isoformat(),
            "created_by": created_by,
        }
        self._write_api_keys(keys)
        return raw_key

    def verify_api_key(self, key: str) -> dict | None:
        if not key.startswith("mc_ak_") or len(key) < 14:
            return None
        key_id = key[6:14]
        keys = self._read_api_keys()
        entry = keys.get(key_id)
        if entry and self.verify_password(key, entry["hash"]):
            return {"username": f"apikey:{entry['name']}", "role": entry["role"], "jti": None}
        return None

    # ── Audit logging ────────────────────────────────────

    def _ensure_audit_table(self):
        conn = sqlite3.connect(DB_PATH)
        conn.execute(CREATE_AUDIT_TABLE)
        conn.commit()
        conn.close()

    def log_audit(self, event: str, username: str = None, ip: str = None, details: str = None):
        conn = sqlite3.connect(DB_PATH)
        conn.execute(
            "INSERT INTO audit_log (timestamp, event, username, ip, details) VALUES (?, ?, ?, ?, ?)",
            (datetime.now(timezone.utc).isoformat(), event, username, ip, details),
        )
        conn.commit()
        conn.close()
