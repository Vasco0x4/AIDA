"""OTP schema additions are present and startup reconciliation is repeatable."""
from sqlalchemy import inspect, text

import database
from models.otp import OTPChallenge, RecoveryCode
from models.user import User


def test_otp_columns_and_tables_survive_repeated_ensure(db, engine, monkeypatch):
    user = User(username="schema-survivor", hashed_password="x", role="viewer")
    db.add(user)
    db.commit()
    user_id = user.id
    db.rollback()
    monkeypatch.setattr(database, "engine", engine)

    database._ensure_columns()
    database._ensure_columns()

    inspector = inspect(engine)
    user_columns = {column["name"] for column in inspector.get_columns("users")}
    assert {
        "auth_provider", "otp_enabled", "otp_secret_encrypted",
        "otp_pending_secret_encrypted", "otp_last_timestep",
    } <= user_columns
    assert {OTPChallenge.__tablename__, RecoveryCode.__tablename__} <= set(inspector.get_table_names())
    with engine.connect() as connection:
        challenge_columns = {
            row[0] for row in connection.execute(text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = 'otp_challenges'"
            ))
        }
    assert {"id", "user_id", "expires_at", "attempts", "consumed_at", "created_at"} <= challenge_columns
    db.expire_all()
    assert db.get(User, user_id).username == "schema-survivor"
