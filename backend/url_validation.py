import socket
import ipaddress
import requests
import os
from urllib.parse import urlparse
from bs4 import BeautifulSoup
from dataclasses import dataclass


@dataclass
class UrlCheckResult:
    valid: bool
    title: str | None
    error_reason: str | None 

GOOGLE_SAFE_BROWSING_API_KEY = os.environ.get('GOOGLE_SAFE_BROWSING_API_KEY')

USER_AGENT = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
}

SAFE_BROWSING_THREAT_TYPES = [
    "MALWARE",
    "SOCIAL_ENGINEERING",
    "UNWANTED_SOFTWARE",
    "POTENTIALLY_HARMFUL_APPLICATION",
]


def is_safe_url(url):
    """Resolve the hostname and return the IP if it is a public address, else None."""
    try:
        hostname = urlparse(url).hostname
        if not hostname:
            return None
        resolved_ip = socket.gethostbyname(hostname)
        ip = ipaddress.ip_address(resolved_ip)
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
            return None
        return resolved_ip
    except Exception:
        return None


def is_safe_browsing_url(url):
    if not GOOGLE_SAFE_BROWSING_API_KEY:
        return "unavailable"
    try:
        resp = requests.post(
            "https://safebrowsing.googleapis.com/v4/threatMatches:find",
            params={"key": GOOGLE_SAFE_BROWSING_API_KEY},
            json={
                "client": {"clientId": "url-shortener", "clientVersion": "1.0"},
                "threatInfo": {
                    "threatTypes": SAFE_BROWSING_THREAT_TYPES,
                    "platformTypes": ["ANY_PLATFORM"],
                    "threatEntryTypes": ["URL"],
                    "threatEntries": [{"url": url}],
                },
            },
            timeout=5,
        )
        if resp.status_code != 200:
            return "unavailable"
        return "safe" if resp.json() == {} else "dangerous"
    except requests.exceptions.RequestException:
        return "unavailable"  # API error = fail closed, block the URL


def validate_url_and_get_title(url):
    resolved_ip = is_safe_url(url)
    if not resolved_ip:
        return UrlCheckResult(valid=False, title=None, error_reason="invalid_url")

    safe_browsing_result = is_safe_browsing_url(url)
    if safe_browsing_result == "dangerous":
        return UrlCheckResult(valid=False, title=None, error_reason="dangerous")
    if safe_browsing_result == "unavailable":
        return UrlCheckResult(valid=False, title=None, error_reason="service_unavailable")

    try:
        parsed = urlparse(url)
        hostname = parsed.hostname

        original_getaddrinfo = socket.getaddrinfo

        def pinned_getaddrinfo(host, *args, **kwargs):
            if host == hostname:
                return original_getaddrinfo(resolved_ip, *args, **kwargs)
            return original_getaddrinfo(host, *args, **kwargs)

        socket.getaddrinfo = pinned_getaddrinfo
        try:
            response = requests.get(url, timeout=3, headers=USER_AGENT, allow_redirects=False)
        finally:
            socket.getaddrinfo = original_getaddrinfo

        if response.is_redirect:
            redirect_url = response.headers.get('Location', '')
            if not is_safe_url(redirect_url):
                return UrlCheckResult(valid=False, title=None, error_reason="invalid_url")
            return UrlCheckResult(valid=True, title=None, error_reason=None)

        if response.status_code >= 500:
            return UrlCheckResult(valid=False, title=None, error_reason="invalid_url")

        soup = BeautifulSoup(response.text, 'html.parser')
        title_tag = soup.find('title')
        title = title_tag.string.strip() if title_tag and title_tag.string else None
        return UrlCheckResult(valid=True, title=title, error_reason=None)

    except requests.exceptions.RequestException:
        return UrlCheckResult(valid=False, title=None, error_reason="invalid_url")
