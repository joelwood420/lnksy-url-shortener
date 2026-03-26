from dataclasses import dataclass
from typing import Optional
import secrets
import sqlite3
import io
import base64

import qrcode
from flask import request

from db import execute_query, transaction
from url_validation import validate_url_and_get_title, UrlCheckResult



_CHARS = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
_SHORTCODE_LENGTH = 5



@dataclass(frozen=True)
class ShortenedUrl:
    short_url: str
    qr_code_base64: str
    is_new: bool


@dataclass(frozen=True)
class UrlEntry:
    original_url: str
    short_code: str
    click_count: int
    title: Optional[str]



def _generate_shortcode() -> str:
    return "".join(secrets.choice(_CHARS) for _ in range(_SHORTCODE_LENGTH))


def _build_short_url(shortcode: str, user_id: Optional[int] = None) -> str:
    if user_id is not None:
        return f"{request.host_url}{user_id}/{shortcode}"
    return f"{request.host_url}{shortcode}"


def _generate_qr_code(short_url: str) -> str:
    qr = qrcode.QRCode(version=1, box_size=12, border=5)
    qr.add_data(short_url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="#6ecfb0", back_color="#2d2d2d")
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    buffer.seek(0)
    return base64.b64encode(buffer.getvalue()).decode("utf-8")


def _normalise_url(url: str) -> str:
    if not url.startswith(("http://", "https://")):
        return "https://" + url
    return url


def _find_existing_shortcode(url: str, user_id: Optional[int]) -> Optional[str]:
    if user_id is not None:
        row = execute_query(
            """
            SELECT urls.short_code FROM urls
            JOIN user_urls ON urls.id = user_urls.url_id
            WHERE urls.original_url = ? AND user_urls.user_id = ?
            """,
            (url, user_id),
            fetchone=True,
        )
    else:
        row = execute_query(
            "SELECT short_code FROM urls WHERE original_url = ?",
            (url,),
            fetchone=True,
        )
    return row["short_code"] if row else None


def _save_url(url: str, shortcode: str, user_id: Optional[int], title: Optional[str]) -> None:
    with transaction() as conn:
        cursor = conn.execute(
            "INSERT INTO urls (original_url, short_code, title) VALUES (?, ?, ?)",
            (url, shortcode, title),
        )
        if user_id is not None:
            conn.execute(
                "INSERT INTO user_urls (user_id, url_id) VALUES (?, ?)",
                (user_id, cursor.lastrowid),
            )




def validate_and_normalise(raw_url: str) -> tuple[str, UrlCheckResult]:
    url = _normalise_url(raw_url)
    result = validate_url_and_get_title(url)
    return url, result


def shorten(url: str, user_id: Optional[int] = None, custom_title: Optional[str] = None,
            page_title: Optional[str] = None) -> ShortenedUrl:
    existing = _find_existing_shortcode(url, user_id)
    if existing:
        short_url = _build_short_url(existing, user_id)
        return ShortenedUrl(
            short_url=short_url,
            qr_code_base64=_generate_qr_code(short_url),
            is_new=False,
        )

    title = custom_title or page_title
    while True:
        shortcode = _generate_shortcode()
        try:
            _save_url(url, shortcode, user_id, title)
            break
        except sqlite3.IntegrityError:
            continue 

    short_url = _build_short_url(shortcode, user_id)
    return ShortenedUrl(
        short_url=short_url,
        qr_code_base64=_generate_qr_code(short_url),
        is_new=True,
    )


def resolve(shortcode: str) -> Optional[str]:
    row = execute_query(
        "SELECT original_url FROM urls WHERE short_code = ?",
        (shortcode,),
        fetchone=True,
    )
    return row["original_url"] if row else None


def record_click(shortcode: str) -> None:
    execute_query(
        "UPDATE urls SET click_count = click_count + 1 WHERE short_code = ?",
        (shortcode,),
        commit=True,
        fetchone=False,
    )


def list_urls_for_user(user_id: int) -> list[UrlEntry]:
    rows = execute_query(
        """
        SELECT urls.original_url, urls.short_code, urls.click_count, urls.title
        FROM urls
        JOIN user_urls ON urls.id = user_urls.url_id
        WHERE user_urls.user_id = ?
        """,
        (user_id,),
        fetchall=True,
    )
    return [
        UrlEntry(
            original_url=r["original_url"],
            short_code=r["short_code"],
            click_count=r["click_count"],
            title=r["title"],
        )
        for r in rows
    ]


def delete_url(shortcode: str, user_id: int) -> bool:
    row = execute_query(
        """
        SELECT urls.id FROM urls
        JOIN user_urls ON urls.id = user_urls.url_id
        WHERE urls.short_code = ? AND user_urls.user_id = ?
        """,
        (shortcode, user_id),
        fetchone=True,
    )
    if not row:
        return False

    url_id = row["id"]
    execute_query("DELETE FROM user_urls WHERE url_id = ?", (url_id,), commit=True, fetchone=False)
    execute_query("DELETE FROM urls WHERE id = ?", (url_id,), commit=True, fetchone=False)
    return True


def qr_code_for(shortcode: str) -> Optional[str]:
    if resolve(shortcode) is None:
        return None
    short_url = _build_short_url(shortcode)
    return _generate_qr_code(short_url)
