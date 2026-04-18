"""At-rest encryption for sensitive config values."""

from __future__ import annotations

import base64
import os
import secrets
from pathlib import Path

try:
    from cryptography.fernet import Fernet, InvalidToken

    _HAS_CRYPTO = True
except ImportError:
    Fernet = None  # type: ignore[assignment]
    InvalidToken = Exception  # type: ignore[assignment]
    _HAS_CRYPTO = False

_PREFIX = "rh:enc:v1:"


def _key_path(config_dir: Path) -> Path:
    return config_dir / ".secret_box.key"


def _ensure_key(config_dir: Path) -> bytes:
    """Read or create the per-config-directory encryption key."""
    path = _key_path(config_dir)
    if path.exists():
        return path.read_bytes()
    config_dir.mkdir(parents=True, exist_ok=True)
    raw = secrets.token_bytes(32)
    key = base64.urlsafe_b64encode(raw)
    path.write_bytes(key)
    try:
        os.chmod(path, 0o600)
    except (OSError, NotImplementedError):
        pass
    return key


def encrypt(plaintext: str, config_dir: Path) -> str:
    """Encrypt plaintext for config storage."""
    if not _HAS_CRYPTO:
        return plaintext
    key = _ensure_key(config_dir)
    token = Fernet(key).encrypt(plaintext.encode("utf-8")).decode("ascii")
    return _PREFIX + token


def decrypt(value: str, config_dir: Path) -> str:
    """Decrypt an encrypted config value or pass plaintext through."""
    if not value.startswith(_PREFIX):
        return value
    if not _HAS_CRYPTO:
        raise RuntimeError("cryptography package required to decrypt this value")
    key = _ensure_key(config_dir)
    token = value[len(_PREFIX) :]
    try:
        return Fernet(key).decrypt(token.encode("ascii")).decode("utf-8")
    except InvalidToken as exc:
        raise RuntimeError(f"could not decrypt config value: {exc}") from exc


def is_encrypted(value: str) -> bool:
    return isinstance(value, str) and value.startswith(_PREFIX)
