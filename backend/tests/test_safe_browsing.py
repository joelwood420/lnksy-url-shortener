import sys
import os
import pytest
import requests as req_module

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import url_validation


@pytest.fixture(autouse=True)
def set_api_key(monkeypatch):
    """Set a fake API key for every test by default.
    Tests that need no key can override with monkeypatch.setattr directly."""
    monkeypatch.setattr(url_validation, "GOOGLE_SAFE_BROWSING_API_KEY", "fake-key")


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
    monkeypatch.setattr(url_validation, "GOOGLE_SAFE_BROWSING_API_KEY", None)
    assert url_validation.is_safe_browsing_url("https://example.com") == "unavailable"



def test_clean_url_allowed(mocker):
    mocker.patch("url_validation.requests.post", return_value=mocker.Mock(status_code=200, json=lambda: {}))
    assert url_validation.is_safe_browsing_url("https://example.com") == "safe"




@pytest.mark.parametrize("threat_type, url", [
    ("SOCIAL_ENGINEERING",           "https://phishing.example.com/login"),
    ("MALWARE",                      "https://malware.example.com/download"),
    ("UNWANTED_SOFTWARE",            "https://pua.example.com/installer.exe"),
    ("POTENTIALLY_HARMFUL_APPLICATION", "https://harmful.example.com/app"),
])
def test_flagged_url_blocked(mocker, threat_type, url):
    mocker.patch(
        "url_validation.requests.post",
        return_value=mocker.Mock(status_code=200, json=lambda b=_threat_body(threat_type, url): b),
    )
    assert url_validation.is_safe_browsing_url(url) == "dangerous"



@pytest.mark.parametrize("status_code", [400, 403, 429, 500, 503])
def test_api_error_fails_open(mocker, status_code):
    mocker.patch("url_validation.requests.post", return_value=mocker.Mock(status_code=status_code, json=lambda: {}))
    assert url_validation.is_safe_browsing_url("https://example.com") == "unavailable"



@pytest.mark.parametrize("exc", [
    req_module.exceptions.ConnectionError("unreachable"),
    req_module.exceptions.Timeout("timed out"),
    req_module.exceptions.RequestException("generic"),
])
def test_network_exception_fails_open(mocker, exc):
    mocker.patch("url_validation.requests.post", side_effect=exc)
    assert url_validation.is_safe_browsing_url("https://example.com") == "unavailable"



def test_validate_url_rejects_flagged_url(mocker):
    mocker.patch("url_validation.is_safe_url", return_value="1.2.3.4")
    mocker.patch(
        "url_validation.requests.post",
        return_value=mocker.Mock(
            status_code=200,
            json=lambda: _threat_body("SOCIAL_ENGINEERING", "https://phishing.example.com/login"),
        ),
    )
    mock_get = mocker.patch("url_validation.requests.get")

    result = url_validation.validate_url_and_get_title("https://phishing.example.com/login")
    assert result.valid is False
    assert result.error_reason == "dangerous"
    mock_get.assert_not_called()
