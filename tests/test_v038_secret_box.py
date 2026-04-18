from __future__ import annotations

from pathlib import Path

import pytest

from research_hub.security.secret_box import decrypt, encrypt, is_encrypted


def test_secret_box_round_trip(tmp_path: Path):
    ciphertext = encrypt("my-secret", tmp_path)
    assert decrypt(ciphertext, tmp_path) == "my-secret"


def test_secret_box_plaintext_passes_through(tmp_path: Path):
    assert decrypt("plain-text", tmp_path) == "plain-text"


def test_secret_box_encrypt_uses_randomized_ciphertext(tmp_path: Path):
    one = encrypt("same-secret", tmp_path)
    two = encrypt("same-secret", tmp_path)
    assert one != two


def test_secret_box_wrong_key_raises_runtime_error(tmp_path: Path):
    ciphertext = encrypt("locked", tmp_path / "a")
    with pytest.raises(RuntimeError, match="could not decrypt config value"):
        decrypt(ciphertext, tmp_path / "b")


def test_secret_box_is_encrypted_detects_prefix(tmp_path: Path):
    ciphertext = encrypt("check", tmp_path)
    assert is_encrypted(ciphertext) is True
    assert is_encrypted("check") is False
