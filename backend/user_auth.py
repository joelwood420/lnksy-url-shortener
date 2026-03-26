from dataclasses import dataclass
from typing import Optional
import bcrypt
from flask import session
from db import execute_query


@dataclass(frozen=True)
class User:
    id: int
    email: str




def _hash_password(password: str) -> bytes:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt())


def _check_password(password: str, password_hash: bytes) -> bool:
    return bcrypt.checkpw(password.encode("utf-8"), password_hash)


def _row_to_user(row) -> Optional[User]:
    if row is None:
        return None
    return User(id=row["id"], email=row["email"])


def create_user(email: str, password: str) -> User:
    """Caller does not need to hash the password — this module handles it."""
    password_hash = _hash_password(password)
    execute_query(
        "INSERT INTO USERS (email, password_hash) VALUES (?, ?)",
        (email, password_hash),
        commit=True,
    )
    row = execute_query("SELECT * FROM USERS WHERE email = ?", (email,), fetchone=True)
    return _row_to_user(row)


def get_user_by_email(email: str) -> Optional[User]:
    row = execute_query("SELECT * FROM USERS WHERE email = ?", (email,), fetchone=True)
    return _row_to_user(row)


def authenticate(email: str, password: str) -> Optional[User]:
    row = execute_query("SELECT * FROM USERS WHERE email = ?", (email,), fetchone=True)
    if row is None or not _check_password(password, row["password_hash"]):
        return None
    return _row_to_user(row)




def login_session(user: User) -> None:
    session["email"] = user.email


def logout_session() -> None:
    session.pop("email", None)


def get_current_user() -> Optional[User]:
    email = session.get("email")
    if not email:
        return None
    return get_user_by_email(email)







