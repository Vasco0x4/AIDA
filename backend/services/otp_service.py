"""RFC 6238 TOTP and bounded, single-use login challenges.

No third-party OTP validator is needed: the implementation is deliberately small
and is covered by the RFC 6238 SHA-1 vectors. Secrets use the platform Fernet
envelope, but (unlike legacy optional secrets) plaintext fallback is forbidden.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import io
import os
import re
import secrets
import struct
import time
import uuid
from datetime import datetime, timedelta, timezone
from urllib.parse import quote, urlencode

from sqlalchemy.orm import Session

from config import settings
from models.otp import OTPChallenge, RecoveryCode
from models.user import User
from utils.crypto import decrypt_secret, encrypt_secret

OTP_PERIOD = 30
OTP_DIGITS = 6
OTP_WINDOW = 1
CHALLENGE_TTL_SECONDS = 300
CHALLENGE_MAX_ATTEMPTS = 5
RECOVERY_CODE_COUNT = 10


class OTPError(Exception):
    def __init__(self, detail: str, status_code: int = 401):
        super().__init__(detail)
        self.detail = detail
        self.status_code = status_code


def generate_secret() -> str:
    """Return a 160-bit RFC 3548 base32 secret without padding."""
    return base64.b32encode(secrets.token_bytes(20)).decode("ascii").rstrip("=")


def _decode_secret(secret: str) -> bytes:
    normalized = secret.strip().replace(" ", "").upper()
    try:
        return base64.b32decode(normalized + "=" * (-len(normalized) % 8), casefold=True)
    except Exception as exc:
        raise OTPError("Stored OTP secret is invalid", 500) from exc


def totp_at(secret: str, timestamp: float | int | None = None, *, timestep: int | None = None) -> str:
    """Generate a six-digit HMAC-SHA1 TOTP (RFC 6238, 30-second period)."""
    counter = timestep if timestep is not None else int((time.time() if timestamp is None else timestamp) // OTP_PERIOD)
    digest = hmac.new(_decode_secret(secret), struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    value = (struct.unpack(">I", digest[offset:offset + 4])[0] & 0x7FFFFFFF) % (10 ** OTP_DIGITS)
    return str(value).zfill(OTP_DIGITS)


def match_totp(
    secret: str,
    code: str,
    *,
    timestamp: float | int | None = None,
    last_timestep: int | None = None,
) -> int | None:
    """Return the matched timestep, rejecting malformed and replayed codes."""
    if not re.fullmatch(r"\d{6}", (code or "").strip()):
        return None
    now = time.time() if timestamp is None else timestamp
    current = int(now // OTP_PERIOD)
    for counter in range(current - OTP_WINDOW, current + OTP_WINDOW + 1):
        if counter < 0 or (last_timestep is not None and counter <= last_timestep):
            continue
        if hmac.compare_digest(totp_at(secret, timestep=counter), code.strip()):
            return counter
    return None


def _encrypt_required(value: str) -> str:
    stored = encrypt_secret(value)
    if not stored.startswith("enc::") or decrypt_secret(stored) != value:
        raise OTPError("OTP encryption is unavailable; check SECRET_KEY", 503)
    return stored


def _decrypt_required(stored: str | None) -> str:
    if not stored or not stored.startswith("enc::"):
        raise OTPError("OTP secret is not securely configured", 500)
    value = decrypt_secret(stored)
    if not value:
        raise OTPError("OTP secret cannot be decrypted", 500)
    return value


def provisioning_uri(user: User, secret: str) -> str:
    label = quote(f"AIDA:{user.username}", safe="")
    query = urlencode({
        "secret": secret,
        "issuer": "AIDA",
        "algorithm": "SHA1",
        "digits": OTP_DIGITS,
        "period": OTP_PERIOD,
    })
    return f"otpauth://totp/{label}?{query}"


def provisioning_qr_svg(uri: str) -> str:
    """Render the otpauth URI locally; no secret is sent to a QR service."""
    import qrcode
    import qrcode.image.svg

    image = qrcode.make(uri, image_factory=qrcode.image.svg.SvgPathImage, box_size=12)
    output = io.BytesIO()
    image.save(output)
    svg = output.getvalue().decode("utf-8")
    if svg.startswith("<?xml"):
        svg = svg.split("?>", 1)[-1].lstrip()
    return svg


def begin_enrollment(db: Session, user: User) -> tuple[str, str, str]:
    if user.otp_enabled:
        raise OTPError("OTP is already enabled; disable it before enrolling again", 409)
    secret = generate_secret()
    user.otp_pending_secret_encrypted = _encrypt_required(secret)
    db.commit()
    uri = provisioning_uri(user, secret)
    return secret, uri, provisioning_qr_svg(uri)


def confirm_enrollment(db: Session, user: User, code: str) -> list[str]:
    if not user.otp_pending_secret_encrypted:
        raise OTPError("No OTP enrollment is pending", 409)
    secret = _decrypt_required(user.otp_pending_secret_encrypted)
    matched = match_totp(secret, code)
    if matched is None:
        raise OTPError("Invalid authenticator code")
    user.otp_secret_encrypted = _encrypt_required(secret)
    user.otp_pending_secret_encrypted = None
    user.otp_enabled = True
    user.otp_last_timestep = None
    codes = replace_recovery_codes(db, user)
    db.commit()
    return codes


def _normalize_recovery(code: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", (code or "").upper())


def _recovery_hash(row_id: str, code: str) -> str:
    # Recovery codes have 80 bits of random entropy. A keyed hash prevents a
    # database-only disclosure from being used directly for offline validation.
    key = (os.getenv("SECRET_KEY") or settings.SECRET_KEY).encode("utf-8")
    return hmac.new(key, f"{row_id}:{_normalize_recovery(code)}".encode("ascii"), hashlib.sha256).hexdigest()


def generate_recovery_codes(db: Session, user: User) -> list[str]:
    codes = []
    for _ in range(RECOVERY_CODE_COUNT):
        raw = secrets.token_hex(10).upper()
        code = "-".join(raw[index:index + 5] for index in range(0, len(raw), 5))
        row_id = str(uuid.uuid4())
        db.add(RecoveryCode(id=row_id, user_id=user.id, code_hash=_recovery_hash(row_id, code)))
        codes.append(code)
    return codes


def replace_recovery_codes(db: Session, user: User) -> list[str]:
    # Flush a recovery code consumed for reauthentication before bulk deletion.
    db.flush()
    db.query(RecoveryCode).filter(RecoveryCode.user_id == user.id).delete(synchronize_session=False)
    db.flush()
    return generate_recovery_codes(db, user)


def verify_second_factor(db: Session, user: User, code: str) -> str | None:
    """Verify and consume a TOTP timestep or a one-time recovery code."""
    # Serialize self-service regeneration/disable with login verification so a
    # timestep or recovery code cannot be consumed by concurrent requests.
    user = db.query(User).filter(User.id == user.id).with_for_update().first()
    secret = _decrypt_required(user.otp_secret_encrypted)
    matched = match_totp(secret, code, last_timestep=user.otp_last_timestep)
    if matched is not None:
        user.otp_last_timestep = matched
        return "totp"

    normalized = _normalize_recovery(code)
    if len(normalized) != 20:
        return None
    rows = (
        db.query(RecoveryCode)
        .filter(RecoveryCode.user_id == user.id, RecoveryCode.used_at.is_(None))
        .with_for_update()
        .all()
    )
    for row in rows:
        if hmac.compare_digest(row.code_hash, _recovery_hash(row.id, normalized)):
            row.used_at = datetime.now(timezone.utc)
            return "recovery"
    return None


def create_challenge(db: Session, user: User) -> OTPChallenge:
    if not user.otp_enabled:
        raise OTPError("OTP is not enabled for this account", 409)
    now = datetime.now(timezone.utc)
    # One active challenge per account prevents parallel unlimited guessing.
    db.query(OTPChallenge).filter(
        OTPChallenge.user_id == user.id, OTPChallenge.consumed_at.is_(None)
    ).delete(synchronize_session=False)
    db.query(OTPChallenge).filter(
        OTPChallenge.expires_at < now - timedelta(days=1)
    ).delete(synchronize_session=False)
    challenge = OTPChallenge(
        id=str(uuid.uuid4()), user_id=user.id,
        expires_at=now + timedelta(seconds=CHALLENGE_TTL_SECONDS),
    )
    db.add(challenge)
    db.commit()
    return challenge


def invalidate_challenges(db: Session, user_id: int) -> None:
    db.query(OTPChallenge).filter(OTPChallenge.user_id == user_id).delete(synchronize_session=False)


def verify_challenge(db: Session, challenge_id: str, code: str) -> User:
    challenge = db.query(OTPChallenge).filter(OTPChallenge.id == challenge_id).with_for_update().first()
    if challenge is None:
        raise OTPError("Invalid or expired OTP challenge")
    if challenge.attempts >= CHALLENGE_MAX_ATTEMPTS:
        raise OTPError("Too many OTP attempts; sign in again", 429)
    if challenge.consumed_at is not None:
        raise OTPError("Invalid or expired OTP challenge")
    expires_at = challenge.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at <= datetime.now(timezone.utc):
        challenge.consumed_at = datetime.now(timezone.utc)
        db.commit()
        raise OTPError("Invalid or expired OTP challenge")
    if challenge.attempts >= CHALLENGE_MAX_ATTEMPTS:
        raise OTPError("Too many OTP attempts; sign in again", 429)

    user = db.query(User).filter(User.id == challenge.user_id).with_for_update().first()
    if user is None or not user.is_active or not user.otp_enabled:
        challenge.consumed_at = datetime.now(timezone.utc)
        db.commit()
        raise OTPError("Invalid or expired OTP challenge")
    if verify_second_factor(db, user, code) is None:
        challenge.attempts += 1
        if challenge.attempts >= CHALLENGE_MAX_ATTEMPTS:
            challenge.consumed_at = datetime.now(timezone.utc)
        db.commit()
        raise OTPError("Invalid authenticator or recovery code")

    challenge.consumed_at = datetime.now(timezone.utc)
    user.last_login_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(user)
    return user


def reset_otp(db: Session, user: User) -> None:
    """Administrative recovery: clear secrets, codes, replay state, challenges."""
    user.otp_enabled = False
    user.otp_secret_encrypted = None
    user.otp_pending_secret_encrypted = None
    user.otp_last_timestep = None
    db.flush()
    db.query(RecoveryCode).filter(RecoveryCode.user_id == user.id).delete(synchronize_session=False)
    invalidate_challenges(db, user.id)
    db.commit()
