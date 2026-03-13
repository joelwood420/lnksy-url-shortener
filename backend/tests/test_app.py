import sys
import os
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from backend.tests.fixtures import client, test_db
import app
from url_validation import UrlCheckResult


def test_generate_shortcode():
    gen_shortcode = app.generate_shortcode()
    assert len(gen_shortcode) == 5
    assert gen_shortcode.isalnum()


def test_existing_shortcode(test_db):
    app.execute_query("INSERT INTO urls (original_url, short_code) VALUES (?, ?)", ("http://example.com", "abc"))
    result = app.execute_query("SELECT 1 FROM urls WHERE short_code = ?", ("abc",))
    assert result is not None



def test_shorten_url(client, mocker):
    mocker.patch("app.validate_url_and_get_title", return_value=UrlCheckResult(valid=True, title="YouTube", error_reason=None))
    response = client.post('/shorten', json={"url": "youtube.com"})
    assert response.status_code == 201

    data = response.get_json()
    assert data is not None
    assert "short_url" in data

    short_url = data["short_url"]
    shortcode = short_url.split("/")[-1]

    assert short_url == f"http://localhost/{shortcode}"

    result = app.execute_query("SELECT * FROM urls WHERE short_code = ?", (shortcode,))
    assert result is not None

    assert result["original_url"] == "https://youtube.com"


def test_register_user(client):
    response = client.post('/register', json={"email": "testuser@test.com", "password": "testpass"})
    assert response.status_code == 201

    data = response.get_json()
    assert data is not None
    assert "message" in data
    assert data["message"] == "User created successfully"


def test_login_user(client):
    client.post('/register', json={"email": "testuser@test.com", "password": "testpass"})
    response = client.post('/login', json={"email": "testuser@test.com", "password": "testpass"})
    assert response.status_code == 200

    data = response.get_json()
    assert data is not None
    assert "message" in data
    assert data["message"] == "Login successful"

def test_logout_user(client):
    client.post('/register', json={"email": "testuser@test.com", "password": "testpass"})
    client.post('/login', json={"email": "testuser@test.com", "password": "testpass"})
    response = client.post('/logout')
    assert response.status_code == 200

    data = response.get_json()
    assert data is not None
    assert "message" in data
    assert data["message"] == "Logged out"


def test_redirect(client, mocker):
    mocker.patch("app.validate_url_and_get_title", return_value=UrlCheckResult(valid=True, title="YouTube", error_reason=None))
    shorten_response = client.post('/shorten', json={"url": "youtube.com"})
    short_url = shorten_response.get_json()["short_url"]
    shortcode = short_url.split("/")[-1]

    response = client.get(f'/{shortcode}')
    assert response.headers['Location'] == "https://youtube.com"


def test_invalid_url(client, test_db):
    response = client.post('/shorten', json={"url": "invalid-url"})
    assert response.status_code == 400

    data = response.get_json()
    assert data is not None
    assert "error" in data
    assert data["error"] == "Please input a valid URL"


def test_missing_url(client, test_db):
    response = client.post('/shorten', json={})
    assert response.status_code == 400

    data = response.get_json()
    assert data is not None
    assert "error" in data
    assert data["error"] == "No URL provided"


def test_handle_user_redirect_success(client, test_db, mocker):
    mocker.patch("app.validate_url_and_get_title", return_value=UrlCheckResult(valid=True, title="YouTube", error_reason=None))
    client.post('/register', json={"email": "testuser@test.com", "password": "testpass"})
    client.post('/login', json={"email": "testuser@test.com", "password": "testpass"})

    shorten_response = client.post('/shorten', json={"url": "youtube.com"})
    assert shorten_response.status_code == 201

    short_url = shorten_response.get_json()["short_url"]
    
    parts = short_url.rstrip("/").split("/")
    user_id, shortcode = parts[-2], parts[-1]

    response = client.get(f'/{user_id}/{shortcode}')
    assert response.status_code == 302
    assert response.headers['Location'] == "https://youtube.com"


def test_handle_user_redirect_not_found(client, test_db):
    response = client.get('/1/zzz')
    assert response.status_code == 404

    data = response.get_json()
    assert data is not None
    assert "error" in data
    assert data["error"] == "Shortcode not found"






