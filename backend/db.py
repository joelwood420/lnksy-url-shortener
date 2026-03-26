import os
import sqlite3
from contextlib import contextmanager
from flask import g

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, 'db', 'urls.db')


def initialize_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    with open(os.path.join(BASE_DIR, 'schema.sql'), 'r') as f:
        conn.executescript(f.read())
    conn.close()


def get_db_connection():
    """Return the per-request database connection, creating it if needed."""
    if 'db' not in g:
        g.db = sqlite3.connect(DB_PATH, timeout=30)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA journal_mode=WAL")
        g.db.execute("PRAGMA busy_timeout=30000")
    return g.db


def close_db(exception=None):
    """Close the per-request database connection."""
    db = g.pop('db', None)
    if db is not None:
        db.close()


def execute_query(query, params=(), commit=False, fetchone=True, fetchall=False):
    """Execute a single SQL statement and return results.

    This is the primary interface for all database access.  Callers choose
    exactly one return mode via the keyword flags:

    * ``fetchone=True`` (default) — return a single ``sqlite3.Row`` or ``None``
    * ``fetchall=True`` — return a list of rows
    * ``commit=True`` with both fetch flags ``False`` — execute a write and
      commit, returning the cursor (useful for ``lastrowid``)
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(query, params)
    if commit:
        conn.commit()
    if fetchall:
        return cursor.fetchall()
    if fetchone:
        return cursor.fetchone()
    return cursor


@contextmanager
def transaction():
    """Context manager that wraps multiple writes in a single transaction.

    Usage::

        with transaction() as conn:
            conn.execute("INSERT ...", (...))
            conn.execute("INSERT ...", (...))
        # automatically committed on clean exit, rolled back on exception
    """
    conn = get_db_connection()
    conn.execute("BEGIN")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
