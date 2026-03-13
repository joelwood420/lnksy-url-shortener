"""Unit tests for url_validation.py"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import url_validation



def test_is_safe_url_rejects_private_ip():
    """192.168.x.x is a private address and should be blocked."""
    assert url_validation.is_safe_url("http://192.168.1.1/page") is None


def test_is_safe_url_rejects_loopback():
    """localhost / 127.0.0.1 should be blocked."""
    assert url_validation.is_safe_url("http://127.0.0.1") is None


def test_is_safe_url_rejects_no_hostname():
    """A URL with no hostname should return None."""
    assert url_validation.is_safe_url("notaurl") is None






def test_validate_url_invalid_host():
    """A URL whose hostname resolves to a private/invalid IP fails validation."""
    result = url_validation.validate_url_and_get_title("http://192.168.1.1")
    assert result.valid is False
    assert result.error_reason == "invalid_url"


def test_validate_url_returns_title(mocker):
    """A clean URL should return valid=True and the page title."""
    mocker.patch("url_validation.is_safe_url", return_value="93.184.216.34")
    mocker.patch("url_validation.is_safe_browsing_url", return_value="safe")
    mock_response = mocker.Mock()
    mock_response.is_redirect = False
    mock_response.status_code = 200
    mock_response.text = "<html><head><title>Example Domain</title></head></html>"
    mocker.patch("url_validation.requests.get", return_value=mock_response)

    result = url_validation.validate_url_and_get_title("https://example.com")
    assert result.valid is True
    assert result.title == "Example Domain"
    assert result.error_reason is None


def test_validate_url_blocks_dangerous_url(mocker):
    """A URL flagged by Safe Browsing should return valid=False with reason 'dangerous'."""
    mocker.patch("url_validation.is_safe_url", return_value="1.2.3.4")
    mocker.patch("url_validation.is_safe_browsing_url", return_value="dangerous")

    result = url_validation.validate_url_and_get_title("https://malware.example.com")
    assert result.valid is False
    assert result.error_reason == "dangerous"





def test_validate_url_server_error(mocker):
    """A URL that returns a 5xx response should fail validation."""
    mocker.patch("url_validation.is_safe_url", return_value="93.184.216.34")
    mocker.patch("url_validation.is_safe_browsing_url", return_value="safe")
    mock_response = mocker.Mock()
    mock_response.is_redirect = False
    mock_response.status_code = 500
    mocker.patch("url_validation.requests.get", return_value=mock_response)

    result = url_validation.validate_url_and_get_title("https://example.com")
    assert result.valid is False
    assert result.error_reason == "invalid_url"

