"""Tests for the Google Safe Browsing integration in is_safe_browsing_url()."""

import sys
import os
import pytest
import requests as req_module

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import app


@pytest.fixture(autouse=True)
def set_api_key(monkeypatch):
    """Set a fake API key for every test by default.
    Tests that need no key can override with monkeypatch.setattr directly."""
    monkeypatch.setattr(app, "GOOGLE_SAFE_BROWSING_API_KEY", "fake-key")


def _threat_body(threat_type, url):
    return {
        "matches": [
            {
                "threatType": threat_type,
                "platformType": "ANY_PLATFORM",
                "threatEntryType": "URL",
                "threat": {"url": url},
            }
        ]
    }



def test_no_api_key_allows_url(monkeypatch):
    monkeypatch.setattr(app, "GOOGLE_SAFE_BROWSING_API_KEY", None)
    assert app.is_safe_browsing_url("https://example.com") is True



def test_clean_url_allowed(mocker):
    mocker.patch("app.requests.post", return_value=mocker.Mock(status_code=200, json=lambda: {}))
    assert app.is_safe_browsing_url("https://example.com") is True




@pytest.mark.parametrize("threat_type, url", [
    ("SOCIAL_ENGINEERING",           "https://phishing.example.com/login"),
    ("MALWARE",                      "https://malware.example.com/download"),
    ("UNWANTED_SOFTWARE",            "https://pua.example.com/installer.exe"),
    ("POTENTIALLY_HARMFUL_APPLICATION", "https://harmful.example.com/app"),
])
def test_flagged_url_blocked(mocker, threat_type, url):
    mocker.patch(
        "app.requests.post",
        return_value=mocker.Mock(status_code=200, json=lambda b=_threat_body(threat_type, url): b),
    )
    assert app.is_safe_browsing_url(url) is False



@pytest.mark.parametrize("status_code", [400, 403, 429, 500, 503])
def test_api_error_fails_open(mocker, status_code):
    mocker.patch("app.requests.post", return_value=mocker.Mock(status_code=status_code, json=lambda: {}))
    assert app.is_safe_browsing_url("https://example.com") is True



@pytest.mark.parametrize("exc", [
    req_module.exceptions.ConnectionError("unreachable"),
    req_module.exceptions.Timeout("timed out"),
    req_module.exceptions.RequestException("generic"),
])
def test_network_exception_fails_open(mocker, exc):
    mocker.patch("app.requests.post", side_effect=exc)
    assert app.is_safe_browsing_url("https://example.com") is True



def test_is_valid_url_rejects_flagged_url(mocker):
    mocker.patch("app.is_safe_url", return_value=True)
    mocker.patch(
        "app.requests.post",
        return_value=mocker.Mock(
            status_code=200,
            json=lambda: _threat_body("SOCIAL_ENGINEERING", "https://phishing.example.com/login"),
        ),
    )
    mock_get = mocker.patch("app.requests.get")

    assert app.is_valid_url("https://phishing.example.com/login") is False
    mock_get.assert_not_called()
