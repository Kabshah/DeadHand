"""app/core/encryption.py — Fernet symmetric encryption for secret_message at rest.

Security rules (§11):
- Fernet key loaded from env only — never hardcoded.
- Plaintext NEVER stored in DB or passed over Celery broker.
- Decrypt only inside the task that needs it (Task 3), in-memory.
"""
import base64
import logging

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import settings

logger = logging.getLogger(__name__)


def _get_fernet() -> Fernet:
    """Return Fernet instance from env key.  Raises if key is missing or invalid."""
    key = settings.FERNET_KEY
    if not key:
        raise RuntimeError(
            "FERNET_KEY is not set. "
            "Generate one with: python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
        )
    return Fernet(key.encode() if isinstance(key, str) else key)


def encrypt_secret(plaintext: str) -> bytes:
    """Encrypt a plaintext secret message and return ciphertext bytes."""
    fernet = _get_fernet()
    ciphertext: bytes = fernet.encrypt(plaintext.encode())
    logger.debug("Secret encrypted (plaintext not logged)")
    return ciphertext


def decrypt_secret(ciphertext: bytes) -> str:
    """Decrypt ciphertext bytes back to plaintext. Raises on invalid token."""
    fernet = _get_fernet()
    try:
        plaintext: str = fernet.decrypt(ciphertext).decode()
        logger.debug("Secret decrypted in-memory (plaintext not logged)")
        return plaintext
    except InvalidToken as exc:
        logger.error("Failed to decrypt secret — invalid token or wrong key")
        raise ValueError("Secret decryption failed") from exc
