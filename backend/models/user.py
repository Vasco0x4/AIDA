"""
User model for authentication
"""
from sqlalchemy import BigInteger, Column, Integer, String, Boolean, DateTime, Text
from sqlalchemy.sql import func
from database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, nullable=False, index=True)
    email = Column(String(255), unique=True, nullable=True)
    hashed_password = Column(String(255), nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    role = Column(String(20), default="user", nullable=False)
    must_change_password = Column(Boolean, default=False, nullable=False)
    last_login_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # OIDC-only accounts have an unusable random local password. Accounts that
    # began locally remain "local" even when subsequently linked by SSO email.
    auth_provider = Column(String(20), nullable=False, default="local", server_default="local")
    otp_enabled = Column(Boolean, nullable=False, default=False, server_default="false")
    otp_secret_encrypted = Column(Text, nullable=True)
    otp_pending_secret_encrypted = Column(Text, nullable=True)
    otp_last_timestep = Column(BigInteger, nullable=True)
