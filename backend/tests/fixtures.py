import pytest
import sys
import os
import sqlite3


sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app import app

@pytest.fixture
def test_db():
    schema_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'schema.sql')
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    with open(schema_path, 'r') as f:
        conn.executescript(f.read())
    app.secret_key = 'test-secret-key'
    app.config['TESTING'] = True
    app.config['WTF_CSRF_ENABLED'] = False
    app.config['RATELIMIT_ENABLED'] = False

    with app.app_context():
        from flask import g
        g.db = conn
        yield conn

    conn.close()

@pytest.fixture
def client(test_db):
    app.config['TESTING'] = True
    app.config['WTF_CSRF_ENABLED'] = False
    with app.test_client() as client:
        yield client


