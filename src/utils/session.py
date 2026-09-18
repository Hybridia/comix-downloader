"""
HTTP session manager.

Three layered defenses against blocks, in order:

1. **curl_cffi browser impersonation** — sends real Chrome TLS / HTTP-2 /
   header fingerprints, which is enough to defeat most Cloudflare
   fingerprint challenges in-process. No external service required.

2. **Adaptive per-host rate limiter** — token bucket per hostname; on
   429/403 we cut the rate in half, on a streak of 200s we slowly
   recover. Stops the "after N downloads my IP gets blocked" pattern.

3. **FlareSolverr fallback** — only invoked when curl_cffi still hits a
   real JS challenge. If the user isn't running FlareSolverr we log it
   at debug, not error.

None of the three help against a **network-level block**, where a
middlebox between us and the site kills the connection during the TLS
handshake based on the hostname in the ClientHello. That happens before
a single HTTP byte is exchanged, so impersonation, rate limiting and
FlareSolverr are all equally powerless. `NetworkBlockedError` detects
that case and fails fast with a message pointing at the real fix (a
VPN), instead of spending the retry budget on a wall.
"""

import time
import random
import threading
from urllib.parse import urlparse
from typing import Any
from .logger import get_logger
from .retry import NonRetryableError

logger = get_logger(__name__)

# Standard requests is always available — used as fallback HTTP client
# and for the FlareSolverr management API regardless of mode.
import requests as std_requests

try:
    from curl_cffi import requests as cffi_requests
    HAS_CURL_CFFI = True
except Exception:  # pragma: no cover - optional dep
    cffi_requests = None
    HAS_CURL_CFFI = False


# ---------------------------------------------------------------------------
# Rate limiting
# ---------------------------------------------------------------------------


class _TokenBucket:
    """Thread-safe token bucket with blocking acquire."""

    def __init__(self, rate: float, capacity: float | None = None):
        self.rate = float(rate)
        self.capacity = float(capacity) if capacity else max(1.0, self.rate)
        self.tokens = self.capacity
        self.last_refill = time.monotonic()
        self._lock = threading.Lock()

    def acquire(self, tokens: float = 1.0) -> None:
        while True:
            with self._lock:
                now = time.monotonic()
                self.tokens = min(
                    self.capacity,
                    self.tokens + (now - self.last_refill) * self.rate,
                )
                self.last_refill = now
                if self.tokens >= tokens:
                    self.tokens -= tokens
                    return
                deficit = tokens - self.tokens
                wait = deficit / self.rate if self.rate > 0 else 0.5
            jitter = random.uniform(0, min(0.1, wait * 0.2))
            time.sleep(wait + jitter)


class _AdaptiveLimiter:
    """Token bucket whose rate adapts to throttle / success signals."""

    # How many consecutive successes before nudging the rate back up
    _RECOVERY_AFTER = 25
    # Multiplicative decrease / increase factors
    _DECREASE = 0.5
    _INCREASE = 1.25

    def __init__(self, base_rate: float, min_rate: float, max_rate: float):
        self.base_rate = base_rate
        self.min_rate = min_rate
        self.max_rate = max_rate
        self.bucket = _TokenBucket(base_rate)
        self._success = 0
        self._lock = threading.Lock()

    @property
    def rate(self) -> float:
        return self.bucket.rate

    def acquire(self) -> None:
        self.bucket.acquire(1)

    def report_success(self) -> None:
        with self._lock:
            self._success += 1
            if self._success >= self._RECOVERY_AFTER and self.bucket.rate < self.max_rate:
                new_rate = min(self.max_rate, self.bucket.rate * self._INCREASE)
                if new_rate != self.bucket.rate:
                    logger.debug(
                        f"Rate recovering: {self.bucket.rate:.2f} -> {new_rate:.2f} req/s"
                    )
                    self.bucket.rate = new_rate
                self._success = 0

    def report_throttle(self) -> None:
        with self._lock:
            self._success = 0
            new_rate = max(self.min_rate, self.bucket.rate * self._DECREASE)
            if new_rate != self.bucket.rate:
                logger.warning(
                    f"Throttle detected — slowing down: "
                    f"{self.bucket.rate:.2f} -> {new_rate:.2f} req/s"
                )
                self.bucket.rate = new_rate


class _HostRateLimiter:
    """Lazy per-host AdaptiveLimiter dictionary."""

    def __init__(self, base_rate: float, min_rate: float, max_rate: float):
        self.base_rate = base_rate
        self.min_rate = min_rate
        self.max_rate = max_rate
        self._limiters: dict[str, _AdaptiveLimiter] = {}
        self._lock = threading.Lock()

    def for_host(self, host: str) -> _AdaptiveLimiter:
        with self._lock:
            limiter = self._limiters.get(host)
            if limiter is None:
                limiter = _AdaptiveLimiter(self.base_rate, self.min_rate, self.max_rate)
                self._limiters[host] = limiter
            return limiter


def _hostname(url: str) -> str:
    return urlparse(url).hostname or url


# ---------------------------------------------------------------------------
# Network-level (SNI) block detection
# ---------------------------------------------------------------------------


# A filtering middlebox that matches the hostname in the ClientHello kills
# the connection by injecting a bogus packet, so the TLS stack reads
# garbage where a ServerHello belongs. Each stack words that differently:
#
#   BoringSSL (curl_cffi) : "...OPENSSL_internal:WRONG_VERSION_NUMBER"
#   OpenSSL   (openssl s_client) : "wrong version number"
#   LibreSSL  (system requests)  : "tlsv1 alert protocol version"
#
# All three mean the same thing and none of them is transient.
_TLS_BLOCK_MARKERS = (
    "wrong_version_number",
    "wrong version number",
    "alert protocol version",
)

# How long a host stays latched as blocked before we probe it again.
# Short enough that turning a VPN on self-heals without restarting the
# app, long enough that a 200-chapter run doesn't retry every request.
_BLOCK_LATCH_TTL = 60.0


def _looks_like_tls_block(exc: BaseException) -> bool:
    """True when an exception carries the injected-packet signature."""
    text = str(exc).lower()
    return any(marker in text for marker in _TLS_BLOCK_MARKERS)


class NetworkBlockedError(NonRetryableError):
    """
    Raised when a host is unreachable at the TLS layer, before HTTP.

    This is deliberately not a subclass of the HTTP client's error types:
    it is not a site problem or an app problem, and no amount of
    impersonation, backoff or FlareSolverr will change the outcome.
    """

    def __init__(self, host: str, original: BaseException | None = None):
        self.host = host
        self.original = original
        super().__init__(
            f"{host} appears to be blocked on this network — the TLS "
            f"handshake was rejected before any request was sent. This is "
            f"a network-level block (ISP or router), not a problem with "
            f"the site or the downloader. Connect a VPN and try again."
        )


# ---------------------------------------------------------------------------
# Session manager
# ---------------------------------------------------------------------------


class SessionManager:
    """
    Single HTTP session with browser fingerprinting + adaptive rate limiting.
    Falls back to FlareSolverr only when a real challenge is detected.
    """

    _CHALLENGE_MARKERS = (
        "Checking your browser",
        "Just a moment",
        "cf-browser-verification",
        "cf-mitigated",
        "Attention Required! | Cloudflare",
    )

    def __init__(self):
        from .config import ConfigManager

        self._config = ConfigManager()
        self.flaresolverr_url = self._config.get(
            "flaresolverr_url", "http://localhost:8191/v1"
        )
        self.use_curl_cffi = bool(self._config.get("use_curl_cffi", True)) and HAS_CURL_CFFI
        self.impersonate = self._config.get("impersonate", "chrome120")
        self.verify_ssl = bool(self._config.get("verify_ssl", True))

        base_rate = float(self._config.get("requests_per_second_per_host", 4.0))
        min_rate = float(self._config.get("min_requests_per_second", 0.5))
        max_rate = float(self._config.get("max_requests_per_second", base_rate * 2))
        self._rate = _HostRateLimiter(base_rate, min_rate, max_rate)

        self._lock = threading.Lock()
        self._fs_warned = False  # don't spam if FlareSolverr is offline
        # host -> monotonic timestamp of the last observed TLS-level block
        self._blocked_hosts: dict[str, float] = {}
        self._session = self._make_session()

        if self.use_curl_cffi:
            logger.info(f"HTTP client: curl_cffi (impersonate={self.impersonate})")
        elif self._config.get("use_curl_cffi", True) and not HAS_CURL_CFFI:
            logger.warning(
                "curl_cffi not installed — falling back to requests. "
                "Install with: pip install curl_cffi"
            )
        else:
            logger.info("HTTP client: requests")

    # -- session construction -----------------------------------------

    def _make_session(self):
        if self.use_curl_cffi:
            try:
                session = cffi_requests.Session(impersonate=self.impersonate)
            except Exception as e:
                logger.warning(
                    f"curl_cffi init failed ({e}); falling back to requests"
                )
                self.use_curl_cffi = False
                session = std_requests.Session()
        else:
            session = std_requests.Session()

        # Common defaults. With curl_cffi the impersonation provides a
        # matching User-Agent, so we don't override it there.
        defaults = {
            "Referer": "https://comix.to/",
            "Accept-Language": "en-US,en;q=0.9",
        }
        if not self.use_curl_cffi:
            defaults["User-Agent"] = (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            )
        session.headers.update(defaults)
        return session

    # -- public API ---------------------------------------------------

    def get(self, url: str, **kwargs: Any):
        """Execute a GET request with rate limiting + auto-bypass on blocks."""
        force_flare = kwargs.pop("force_flare", False)
        host = _hostname(url)
        limiter = self._rate.for_host(host)

        # A host we've just seen blocked at the TLS layer fails immediately —
        # no socket, no rate-limiter token, no FlareSolverr round-trip.
        if self._is_latched_blocked(host):
            raise NetworkBlockedError(host)

        if force_flare:
            with self._lock:
                logger.info(f"Forcing FlareSolverr bypass for {url}")
                if self._solve_cloudflare(url):
                    limiter.acquire()
                    return self._raw_get(url, **kwargs)
                logger.error("Forced FlareSolverr bypass failed; trying direct request.")

        limiter.acquire()
        try:
            response = self._raw_get(url, **kwargs)
        except Exception as e:
            if _looks_like_tls_block(e):
                raise self._latch_blocked(host, e) from e
            logger.error(f"Request failed: {e}")
            raise

        # --- analyze response --------------------------------------
        is_cloudflare = "cloudflare" in response.headers.get("Server", "").lower()
        is_throttle = response.status_code in (429, 503)
        is_blocked = response.status_code == 403
        is_error = response.status_code in (403, 429, 503)

        content_type = response.headers.get("Content-Type", "").lower()
        is_text = "text/html" in content_type or "application/json" in content_type
        has_challenge = False
        if is_text:
            try:
                if any(m in response.text for m in self._CHALLENGE_MARKERS):
                    has_challenge = True
            except Exception:
                pass

        is_empty_result = False
        if response.status_code == 200 and "application/json" in content_type:
            try:
                json_data = response.json()
                if json_data.get("result") is None and json_data.get("status") == "error":
                    is_empty_result = True
                    logger.warning(f"API soft-block detected for {url}")
            except Exception:
                pass

        # --- adaptive feedback -------------------------------------
        if is_throttle or is_blocked:
            limiter.report_throttle()
        elif response.status_code == 200 and not has_challenge and not is_empty_result:
            limiter.report_success()

        # --- escalation --------------------------------------------
        if is_error or has_challenge or is_empty_result:
            if is_cloudflare or has_challenge or is_empty_result:
                with self._lock:
                    logger.warning(
                        f"Block/challenge for {url} (status={response.status_code}); "
                        f"trying FlareSolverr fallback..."
                    )
                    if self._solve_cloudflare(url):
                        limiter.acquire()
                        response = self._raw_get(url, **kwargs)
            elif is_throttle:
                wait = random.uniform(3.0, 8.0)
                logger.warning(
                    f"Server throttled (status={response.status_code}); backing off {wait:.1f}s"
                )
                time.sleep(wait)
                limiter.acquire()
                response = self._raw_get(url, **kwargs)

        return response

    # -- internals ----------------------------------------------------

    def _raw_get(self, url: str, **kwargs: Any):
        """Plain GET against the underlying session, with no policy."""
        kwargs.setdefault("verify", self.verify_ssl)
        return self._session.get(url, **kwargs)

    # -- network-block latch ------------------------------------------

    def _is_latched_blocked(self, host: str) -> bool:
        """True while `host` is inside its post-block cooldown."""
        with self._lock:
            seen_at = self._blocked_hosts.get(host)
            if seen_at is None:
                return False
            if time.monotonic() - seen_at < _BLOCK_LATCH_TTL:
                return True
            # Cooldown elapsed — let one real attempt through so that
            # bringing a VPN up recovers without restarting the app.
            del self._blocked_hosts[host]
            return False

    def _latch_blocked(self, host: str, original: BaseException) -> "NetworkBlockedError":
        """Record a TLS-level block for `host` and build the error to raise."""
        with self._lock:
            first = host not in self._blocked_hosts
            self._blocked_hosts[host] = time.monotonic()
        error = NetworkBlockedError(host, original)
        # Only the first hit is loud; a bulk run would otherwise print this
        # once per chapter.
        if first:
            logger.error(str(error))
        else:
            logger.debug(f"{host} still blocked at the TLS layer")
        return error

    def clear_blocked_hosts(self) -> None:
        """Forget every latched block (e.g. after connecting a VPN)."""
        with self._lock:
            self._blocked_hosts.clear()

    def _solve_cloudflare(self, target_url: str) -> bool:
        """Use FlareSolverr to acquire clearance cookies."""
        try:
            session_res = std_requests.post(
                self.flaresolverr_url,
                json={"cmd": "sessions.create"},
                timeout=10,
            ).json()

            if session_res.get("status") != "ok":
                logger.error(f"FlareSolverr session.create failed: {session_res}")
                return False
            session_id = session_res.get("session")

            req_res = std_requests.post(
                self.flaresolverr_url,
                json={
                    "cmd": "request.get",
                    "url": target_url,
                    "session": session_id,
                    "maxTimeout": 60000,
                },
                timeout=65,
            ).json()

            success = False
            if req_res.get("status") == "ok":
                solution = req_res.get("solution", {})
                cookies = solution.get("cookies", [])
                for ck in cookies:
                    self._session.cookies.set(
                        ck["name"], ck["value"], domain=ck.get("domain", "")
                    )
                ua = solution.get("userAgent")
                if ua:
                    self._session.headers.update({"User-Agent": ua})
                logger.info(f"FlareSolverr bypass OK ({len(cookies)} cookies)")
                success = True
            else:
                logger.error(f"FlareSolverr request failed: {req_res}")

            std_requests.post(
                self.flaresolverr_url,
                json={"cmd": "sessions.destroy", "session": session_id},
                timeout=10,
            )
            return success

        except std_requests.exceptions.ConnectionError:
            # FlareSolverr not running — that's fine in the new model.
            # Warn once, then go quiet.
            if not self._fs_warned:
                logger.info(
                    "FlareSolverr not reachable at "
                    f"{self.flaresolverr_url}. "
                    "It's only needed if curl_cffi can't bypass a hard challenge."
                )
                self._fs_warned = True
            return False
        except Exception as e:
            logger.warning(f"FlareSolverr error: {e}")
            return False


# ---------------------------------------------------------------------------
# Singleton accessor
# ---------------------------------------------------------------------------


_session_manager: SessionManager | None = None
_session_lock = threading.Lock()


def get_session() -> SessionManager:
    """Get the singleton session manager."""
    global _session_manager
    if _session_manager is None:
        with _session_lock:
            if _session_manager is None:
                _session_manager = SessionManager()
    return _session_manager


def reset_session() -> None:
    """Drop the cached session — useful when settings change at runtime."""
    global _session_manager
    with _session_lock:
        _session_manager = None
