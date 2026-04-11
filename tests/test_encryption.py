"""Fernet encryption roundtrip and fail-closed tests."""

from __future__ import annotations

import pytest
from cryptography.fernet import Fernet

from src.database.encryption import decrypt_value, encrypt_value
from src.repositories.errors import EncryptionKeyMissingError

VALID_KEY = Fernet.generate_key().decode()


def test_encrypt_decrypt_roundtrip() -> None:
    """Encrypting then decrypting returns the original plaintext."""
    plaintext = "sk-secret-api-key-12345"
    ciphertext = encrypt_value(plaintext, key=VALID_KEY)

    assert ciphertext != plaintext
    assert decrypt_value(ciphertext, key=VALID_KEY) == plaintext


def test_ciphertext_is_not_plaintext() -> None:
    """Encrypted output does not contain the plaintext."""
    plaintext = "my-super-secret-key"
    ciphertext = encrypt_value(plaintext, key=VALID_KEY)

    assert plaintext not in ciphertext


def test_different_encryptions_differ() -> None:
    """Two encryptions of the same value produce different ciphertexts."""
    plaintext = "same-key-twice"
    ct1 = encrypt_value(plaintext, key=VALID_KEY)
    ct2 = encrypt_value(plaintext, key=VALID_KEY)

    # Fernet includes a timestamp, so ciphertexts differ
    assert ct1 != ct2
    # But both decrypt to the same value
    assert decrypt_value(ct1, key=VALID_KEY) == plaintext
    assert decrypt_value(ct2, key=VALID_KEY) == plaintext


def test_encrypt_fails_closed_without_key() -> None:
    """Encrypting with empty key raises EncryptionKeyMissingError."""
    with pytest.raises(EncryptionKeyMissingError):
        encrypt_value("anything", key="")


def test_decrypt_fails_closed_without_key() -> None:
    """Decrypting with empty key raises EncryptionKeyMissingError."""
    with pytest.raises(EncryptionKeyMissingError):
        decrypt_value("anything", key="")


def test_decrypt_with_wrong_key_fails() -> None:
    """Decrypting with a different key raises an error."""
    other_key = Fernet.generate_key().decode()
    ciphertext = encrypt_value("secret", key=VALID_KEY)

    with pytest.raises(Exception):  # noqa: B017
        decrypt_value(ciphertext, key=other_key)
