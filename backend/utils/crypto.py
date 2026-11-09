"""
Symmetric encryption for secrets stored at rest (e.g. LLM provider API keys).

Keys are encrypted with Fernet using a key derived from the application's
bootstrapped SECRET_KEY, so ciphertext is bound to this deployment. This is a
deliberate improvement over the plaintext storage used by notification_configs.

If SECRET_KEY is unavailable for any reason, callers fall back to plaintext and
a warning is logged — the platform must never hard-crash on secret handling, but
the normal path always encrypts.
"""
import base64
import hashlib
import os

from cryptography.fernet import Fernet, InvalidToken

from utils.logger import get_logger

logger = get_logger(__name__)

# Marker prefix so we can distinguish encrypted values from any legacy plaintext
# that may already sit in the column.
_PREFIX = "enc::"


def _fernet() -> Fernet:
    """Build a Fernet from the app SECRET_KEY (env, set by bootstrap_secrets)."""
    secret = os.getenv("SECRET_KEY")
    if not secret:
        raise RuntimeError("SECRET_KEY not set; cannot derive encryption key")
    # Fernet needs a 32-byte urlsafe-base64 key; derive it deterministically.
    digest = hashlib.sha256(secret.encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt_secret(plaintext: str) -> str:
    """Encrypt a secret for storage. Returns an ``enc::<token>`` string."""
    if plaintext is None:
        return plaintext
    try:
        token = _fernet().encrypt(plaintext.encode("utf-8")).decode("utf-8")
        return _PREFIX + token
    except Exception as e:  # pragma: no cover - defensive
        logger.warning("encrypt_secret failed; storing plaintext", error=str(e))
        return plaintext


def decrypt_secret(stored: str) -> str:
    """Decrypt a stored secret. Transparently returns legacy plaintext as-is."""
    if not stored:
        return stored
    if not stored.startswith(_PREFIX):
        # Legacy/plaintext value — return unchanged.
        return stored
    token = stored[len(_PREFIX):]
    try:
        return _fernet().decrypt(token.encode("utf-8")).decode("utf-8")
    except (InvalidToken, Exception) as e:
        logger.warning("decrypt_secret failed", error=str(e))
        return ""


def mask_secret(plaintext: str, visible: int = 4) -> str:
    """Return a display-safe mask like ``sk-…AB12`` for API responses."""
    if not plaintext:
        return ""
    if len(plaintext) <= visible:
        return "•" * len(plaintext)
    return "…" + plaintext[-visible:]
