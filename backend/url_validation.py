import socket
import ipaddress
import requests
import os
from enum import Enum
from urllib.parse import urlparse, urljoin
from bs4 import BeautifulSoup
from dataclasses import dataclass


@dataclass
class UrlCheckResult:
    valid: bool
    title: str | None
    error_reason: str | None 


class SafeBrowsingStatus(Enum):
    SAFE = "safe"
    DANGEROUS = "dangerous"
    UNAVAILABLE = "unavailable"

GOOGLE_SAFE_BROWSING_API_KEY = os.environ.get('GOOGLE_SAFE_BROWSING_API_KEY')

USER_AGENT = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
}

MAX_REDIRECT_HOPS = 5

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
        return SafeBrowsingStatus.UNAVAILABLE
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
            return SafeBrowsingStatus.UNAVAILABLE
        return SafeBrowsingStatus.SAFE if resp.json() == {} else SafeBrowsingStatus.DANGEROUS
    except requests.exceptions.RequestException:
        return SafeBrowsingStatus.UNAVAILABLE


def _fetch_with_pinned_dns(url, resolved_ip):
    """Fetch ``url`` with DNS pinned to ``resolved_ip``, without following redirects.

    Pinning matters because validating a hostname and then fetching it are two
    separate lookups.  Without it, a host that answered with a harmless public
    address during validation can answer with a loopback address a moment later.
    """
    hostname = urlparse(url).hostname
    original_getaddrinfo = socket.getaddrinfo

    def pinned_getaddrinfo(host, *args, **kwargs):
        if host == hostname:
            return original_getaddrinfo(resolved_ip, *args, **kwargs)
        return original_getaddrinfo(host, *args, **kwargs)

    socket.getaddrinfo = pinned_getaddrinfo
    try:
        return requests.get(url, timeout=3, headers=USER_AGENT, allow_redirects=False)
    finally:
        socket.getaddrinfo = original_getaddrinfo


def validate_url_and_get_title(url):
    """Walk the redirect chain, checking every hop, and return the final page title.

    Each hop is checked twice: that it does not resolve to an internal address,
    and that Safe Browsing does not flag it.  Checking only the submitted URL is
    not enough, because a clean redirector can forward to a flagged destination.
    """
    current_url = url

    for _ in range(MAX_REDIRECT_HOPS + 1):
        resolved_ip = is_safe_url(current_url)
        if not resolved_ip:
            return UrlCheckResult(valid=False, title=None, error_reason="invalid_url")

        safe_browsing_result = is_safe_browsing_url(current_url)
        if safe_browsing_result == SafeBrowsingStatus.DANGEROUS:
            return UrlCheckResult(valid=False, title=None, error_reason="dangerous")
        if safe_browsing_result == SafeBrowsingStatus.UNAVAILABLE:
            return UrlCheckResult(valid=False, title=None, error_reason="service_unavailable")

        try:
            response = _fetch_with_pinned_dns(current_url, resolved_ip)
        except requests.exceptions.RequestException:
            return UrlCheckResult(valid=False, title=None, error_reason="invalid_url")

        if response.is_redirect:
            location = response.headers.get('Location', '')
            if not location:
                return UrlCheckResult(valid=False, title=None, error_reason="invalid_url")
            # Location is allowed to be relative, so resolve it against the URL
            # we just fetched rather than treating it as absolute.
            current_url = urljoin(current_url, location)
            continue

        if response.status_code >= 500:
            return UrlCheckResult(valid=False, title=None, error_reason="invalid_url")

        soup = BeautifulSoup(response.text, 'html.parser')
        title_tag = soup.find('title')
        title = title_tag.string.strip() if title_tag and title_tag.string else None
        return UrlCheckResult(valid=True, title=title, error_reason=None)

    # A chain longer than this is either a loop or deliberately evasive.
    return UrlCheckResult(valid=False, title=None, error_reason="invalid_url")
