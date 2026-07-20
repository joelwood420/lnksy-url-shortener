"""Unit tests for url_validation.py"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import url_validation
from url_validation import SafeBrowsingStatus



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
    mocker.patch("url_validation.is_safe_browsing_url", return_value=SafeBrowsingStatus.SAFE)
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
    mocker.patch("url_validation.is_safe_browsing_url", return_value=SafeBrowsingStatus.DANGEROUS)

    result = url_validation.validate_url_and_get_title("https://malware.example.com")
    assert result.valid is False
    assert result.error_reason == "dangerous"





def _response(mocker, *, redirect_to=None, status_code=200, text=""):
    """Build a mock response, optionally a redirect pointing at ``redirect_to``."""
    response = mocker.Mock()
    response.is_redirect = redirect_to is not None
    response.status_code = 302 if redirect_to else status_code
    response.headers = {"Location": redirect_to} if redirect_to else {}
    response.text = text
    return response


def test_validate_url_blocks_dangerous_redirect_target(mocker):
    """A clean URL that redirects to a flagged one must be rejected.

    The first hop passes Safe Browsing on its own merits; the danger only shows
    up when the destination is checked too.
    """
    mocker.patch("url_validation.is_safe_url", return_value="93.184.216.34")
    mocker.patch(
        "url_validation.is_safe_browsing_url",
        side_effect=[SafeBrowsingStatus.SAFE, SafeBrowsingStatus.DANGEROUS],
    )
    mocker.patch(
        "url_validation.requests.get",
        return_value=_response(mocker, redirect_to="https://malware.example.com"),
    )

    result = url_validation.validate_url_and_get_title("https://clean-redirector.example")
    assert result.valid is False
    assert result.error_reason == "dangerous"


def test_validate_url_blocks_redirect_to_internal_address(mocker):
    """A redirect pointing at a private address must be rejected."""
    mocker.patch("url_validation.is_safe_url", side_effect=["93.184.216.34", None])
    mocker.patch("url_validation.is_safe_browsing_url", return_value=SafeBrowsingStatus.SAFE)
    mocker.patch(
        "url_validation.requests.get",
        return_value=_response(mocker, redirect_to="http://169.254.169.254/latest/meta-data/"),
    )

    result = url_validation.validate_url_and_get_title("https://clean-redirector.example")
    assert result.valid is False
    assert result.error_reason == "invalid_url"


def test_validate_url_follows_redirect_to_title(mocker):
    """A safe redirect chain resolves to the final page's title."""
    mocker.patch("url_validation.is_safe_url", return_value="93.184.216.34")
    mocker.patch("url_validation.is_safe_browsing_url", return_value=SafeBrowsingStatus.SAFE)
    mocker.patch(
        "url_validation.requests.get",
        side_effect=[
            _response(mocker, redirect_to="https://example.com/final"),
            _response(mocker, text="<html><head><title>Final Page</title></head></html>"),
        ],
    )

    result = url_validation.validate_url_and_get_title("https://example.com/start")
    assert result.valid is True
    assert result.title == "Final Page"


def test_validate_url_resolves_relative_redirect(mocker):
    """A relative Location header is resolved against the current URL.

    Previously this was passed straight to the host check, which found no
    hostname and rejected the link, so ordinary sites using relative redirects
    were refused.
    """
    seen = []

    def record(url):
        seen.append(url)
        return "93.184.216.34"

    mocker.patch("url_validation.is_safe_url", side_effect=record)
    mocker.patch("url_validation.is_safe_browsing_url", return_value=SafeBrowsingStatus.SAFE)
    mocker.patch(
        "url_validation.requests.get",
        side_effect=[
            _response(mocker, redirect_to="/landing"),
            _response(mocker, text="<html><head><title>Landing</title></head></html>"),
        ],
    )

    result = url_validation.validate_url_and_get_title("https://example.com/start")
    assert result.valid is True
    assert seen[1] == "https://example.com/landing"


def test_validate_url_stops_on_redirect_loop(mocker):
    """An endless redirect chain is refused rather than followed forever."""
    mocker.patch("url_validation.is_safe_url", return_value="93.184.216.34")
    mocker.patch("url_validation.is_safe_browsing_url", return_value=SafeBrowsingStatus.SAFE)
    mocker.patch(
        "url_validation.requests.get",
        return_value=_response(mocker, redirect_to="https://example.com/loop"),
    )

    result = url_validation.validate_url_and_get_title("https://example.com/loop")
    assert result.valid is False
    assert result.error_reason == "invalid_url"


def test_validate_url_server_error(mocker):
    """A URL that returns a 5xx response should fail validation."""
    mocker.patch("url_validation.is_safe_url", return_value="93.184.216.34")
    mocker.patch("url_validation.is_safe_browsing_url", return_value=SafeBrowsingStatus.SAFE)
    mock_response = mocker.Mock()
    mock_response.is_redirect = False
    mock_response.status_code = 500
    mocker.patch("url_validation.requests.get", return_value=mock_response)

    result = url_validation.validate_url_and_get_title("https://example.com")
    assert result.valid is False
    assert result.error_reason == "invalid_url"

