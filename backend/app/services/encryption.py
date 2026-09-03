from __future__ import annotations

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import get_settings


class EncryptionService:
    """Application-side encryption for sensitive source URLs."""

    def __init__(self, key: str | None = None) -> None:
        raw = (key or get_settings().data_encryption_key).encode("utf-8")
        # Derive a stable Fernet key from any passphrase-like secret.
        digest = hashlib.sha256(raw).digest()
        self._fernet = Fernet(base64.urlsafe_b64encode(digest))

    def encrypt(self, plaintext: str) -> str:
        return self._fernet.encrypt(plaintext.encode("utf-8")).decode("utf-8")

    def decrypt(self, ciphertext: str) -> str:
        try:
            return self._fernet.decrypt(ciphertext.encode("utf-8")).decode("utf-8")
        except InvalidToken as exc:
            raise ValueError("Unable to decrypt value") from exc
