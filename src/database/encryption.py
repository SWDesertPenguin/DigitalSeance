# SPDX-License-Identifier: AGPL-3.0-or-later

"""Fernet encryption helpers for API key protection at rest."""

from __future__ import annotations

from cryptography.fernet import Fernet

from src.repositories.errors import EncryptionKeyMissingError


def _build_fernet(key: str) -> Fernet:
    """Build a Fernet instance from the configured key."""
    if not key:
        raise EncryptionKeyMissingError("SACP_ENCRYPTION_KEY is not set")
    return Fernet(key.encode())


def encrypt_value(plaintext: str, *, key: str) -> str:
    """Encrypt a plaintext string and return the ciphertext token."""
    fernet = _build_fernet(key)
    return fernet.encrypt(plaintext.encode()).decode()


def decrypt_value(ciphertext: str, *, key: str) -> str:
    """Decrypt a ciphertext token and return the plaintext string."""
    fernet = _build_fernet(key)
    return fernet.decrypt(ciphertext.encode()).decode()
