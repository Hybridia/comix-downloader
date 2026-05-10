"""
Email-password login for global.toomics.com.

Replaces the cookie-paste flow once the user has stored their credentials
in ``secrets.json``: we POST the same form the browser does (captured
from devtools — `/en/auth/layer_login` with `user_id` + `user_pw`), then
follow the homepage GET that toomics uses to "finalise" the session
cookie. Returns a ready-to-use ``Cookie:`` header string plus the
User-Agent that was on the wire (so subsequent provider requests stay
consistent with the UA toomics bound to the session).

If toomics ever wraps the login in a captcha or an MFA challenge this
will start failing with ``ToomicsLoginError`` and we fall back to
manual cookie paste (still supported by the provider).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import requests as _requests

from .logger import get_logger

logger = get_logger(__name__)


# A stable, plausible Chrome / macOS UA. The session toomics mints will
# be bound to whatever UA we send here — using a fixed string means
# every later provider request matches automatically.
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)

_LOGIN_URL = "https://global.toomics.com/en/auth/layer_login"
_HOME_URL = "https://global.toomics.com/en"
_SESSION_COOKIE = "GTOOMICScisession"


class ToomicsLoginError(RuntimeError):
    """Login attempt didn't yield a valid session cookie."""


@dataclass
class LoginResult:
    cookie: str          # flat "name=value; name=value" header
    user_agent: str
    user_type: Optional[str] = None  # GTOOMICSTOOMICS_USERTYPE if set


def _flatten_cookies(jar) -> str:
    """Render a CookieJar as a single ``Cookie:`` header string."""
    return "; ".join(f"{c.name}={c.value}" for c in jar)


def login(
    email: str,
    password: str,
    *,
    keep_login: bool = True,
    user_agent: Optional[str] = None,
    existing_cookies: Optional[str] = None,
    timeout: float = 30.0,
) -> LoginResult:
    """
    Authenticate against toomics' email login form and return the
    cookies the provider needs.

    If ``existing_cookies`` is supplied (typically the previously-saved
    cookie string from secrets.json), they are pre-loaded into the
    request jar so that:
      - persistent server-side state cookies the user had before
        (notably ``GTOOMICSTOOMICS_USERTYPE`` — the VIP marker — and
        ``tw_adultYN`` for adult-content acceptance) are preserved;
      - the login response's Set-Cookie just *overrides* volatile
        cookies (``GTOOMICScisession``) instead of starting from scratch.
    Without this merge, fresh sessions look "non-VIP" to the listing
    endpoint and most VIP episodes are dropped from the response.
    """
    if not email or not password:
        raise ToomicsLoginError("Email and password are required.")

    ua = (user_agent or DEFAULT_USER_AGENT).strip()
    sess = _requests.Session()
    sess.headers.update(
        {
            "User-Agent": ua,
            "Accept-Language": "en-US,en;q=0.9",
            "Accept": (
                "text/html,application/xhtml+xml,application/xml;q=0.9,"
                "*/*;q=0.8"
            ),
        }
    )

    # Pre-load the jar with whatever the user had before. The server's
    # Set-Cookie responses below will overwrite the entries it cares
    # about; the rest stay put.
    if existing_cookies:
        for piece in existing_cookies.split(";"):
            piece = piece.strip()
            if "=" not in piece:
                continue
            name, _, value = piece.partition("=")
            sess.cookies.set(
                name.strip(), value.strip(), domain=".toomics.com", path="/"
            )

    # 1) Prime anonymous cookies (some sites require a cookie set on
    #    GET / before the POST will be accepted).
    try:
        sess.get(_HOME_URL, timeout=timeout)
    except _requests.RequestException as e:
        raise ToomicsLoginError(f"Couldn't reach {_HOME_URL}: {e}") from e

    # 2) Submit the login form.
    payload = {
        "user_id": email,
        "user_pw": password,
    }
    if keep_login:
        payload["keep_login"] = "Y"
    try:
        r = sess.post(
            _LOGIN_URL,
            data=payload,
            headers={
                "Origin": "https://global.toomics.com",
                "Referer": "https://global.toomics.com/en",
                "X-Requested-With": "XMLHttpRequest",
            },
            timeout=timeout,
            allow_redirects=True,
        )
    except _requests.RequestException as e:
        raise ToomicsLoginError(f"Login POST failed: {e}") from e

    if r.status_code >= 400:
        raise ToomicsLoginError(
            f"Login POST returned HTTP {r.status_code}. "
            "Wrong email / password, or toomics changed the form."
        )

    # Toomics' XHR login often returns a tiny JSON body or just sets
    # cookies. Look for explicit failure markers but don't insist on
    # JSON — a 200 with the right cookie is the success signal.
    body = (r.text or "")[:2000]
    body_lower = body.lower()
    if any(
        marker in body_lower
        for marker in ("incorrect password", "wrong password", "invalid email")
    ):
        raise ToomicsLoginError(
            "Toomics rejected the credentials. "
            f"Server message: {body[:200]!r}"
        )

    # 3) Hit the homepage so toomics finalises the session cookie
    #    (the captured devtools trace shows GET /en re-emits
    #    GTOOMICScisession with the post-login session_id).
    try:
        sess.get(_HOME_URL, timeout=timeout)
    except _requests.RequestException as e:
        raise ToomicsLoginError(
            f"Post-login homepage GET failed: {e}"
        ) from e

    # 4) Verify the session cookie is present.
    cookie_names = {c.name for c in sess.cookies}
    if _SESSION_COOKIE not in cookie_names:
        raise ToomicsLoginError(
            "Login completed without setting "
            f"{_SESSION_COOKIE!r}. The form may have rejected the "
            "credentials silently, or toomics' login flow changed. "
            f"Cookies seen: {sorted(cookie_names)!r}."
        )

    user_type = None
    for c in sess.cookies:
        if c.name == "GTOOMICSTOOMICS_USERTYPE":
            user_type = c.value
            break

    cookie_header = _flatten_cookies(sess.cookies)
    logger.info(
        "toomics login OK — %d cookies, USERTYPE=%s",
        len(cookie_names),
        user_type or "?",
    )
    return LoginResult(cookie=cookie_header, user_agent=ua, user_type=user_type)
