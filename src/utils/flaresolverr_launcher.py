"""
Start a local FlareSolverr on demand, so the user doesn't have to.

``SessionManager._solve_cloudflare`` calls ``ensure_running`` the first
time a site answers with a Cloudflare human check. If nothing is
listening on the configured URL and a FlareSolverr source install is
found (default ``~/Documents/FlareSolverr``, see
``scripts/start_flaresolverr.sh``), we launch it, wait for it to come
up, and let the solve proceed. Lazy on purpose: a session that never
meets a challenge never starts Chrome.

The process we start is ours to stop — it's killed (with its Chrome
children, via the process group) when the app exits. A FlareSolverr the
user started themselves is left alone.

macOS specifics (same as the script): FlareSolverr's ``HEADLESS=true``
means Xvfb, which doesn't exist there. So we run it with
``HEADLESS=false`` through ``scripts/flaresolverr_hidden.py``, which adds
Chrome's ``--headless=new`` flag — no window, and Cloudflare still
passes. ``hidden=False`` shows the window again (debugging). We bind to
127.0.0.1 so it isn't reachable from the rest of the network.
"""

import atexit
import os
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

import requests

from .logger import get_logger

logger = get_logger(__name__)

DEFAULT_INSTALL_DIR = Path.home() / "Documents" / "FlareSolverr"
_HIDDEN_WRAPPER = Path(__file__).resolve().parents[2] / "scripts" / "flaresolverr_hidden.py"

# After a failed launch, don't try again on every request — but do
# retry eventually (the user may have just finished installing it).
_RETRY_AFTER_FAILURE = 300.0
_STARTUP_TIMEOUT = 60.0
_LAUNCH_ATTEMPTS = 3

_lock = threading.Lock()
_proc: Optional[subprocess.Popen] = None
_failed_at: float = 0.0


def _ping(base_url: str) -> bool:
    try:
        return requests.get(base_url, timeout=2).ok
    except requests.RequestException:
        return False


def _python_in(install_dir: Path) -> Path:
    if os.name == "nt":
        return install_dir / ".venv" / "Scripts" / "python.exe"
    return install_dir / ".venv" / "bin" / "python"


def ensure_running(
    api_url: str, install_dir: Optional[str] = None, hidden: bool = True,
) -> bool:
    """
    True if FlareSolverr answers at ``api_url`` — starting our local
    install first if needed. Only ever launches for a localhost URL.
    """
    global _proc, _failed_at

    parsed = urlparse(api_url)
    base = f"{parsed.scheme}://{parsed.netloc}/"
    if _ping(base):
        return True
    if parsed.hostname not in ("localhost", "127.0.0.1"):
        return False

    with _lock:
        if _ping(base):
            return True
        if _failed_at and time.monotonic() - _failed_at < _RETRY_AFTER_FAILURE:
            return False

        root = Path(install_dir).expanduser() if install_dir else DEFAULT_INSTALL_DIR
        python, script = _python_in(root), root / "src" / "flaresolverr.py"
        if not (python.exists() and script.exists()):
            logger.info("No FlareSolverr install at %s — can't auto-start it.", root)
            _failed_at = time.monotonic()
            return False

        env = dict(
            os.environ,
            HOST="127.0.0.1",
            PORT=str(parsed.port or 8191),
            HEADLESS="false" if sys.platform == "darwin" else "true",
            LOG_LEVEL="info",
        )
        entry = script
        if hidden and sys.platform == "darwin" and _HIDDEN_WRAPPER.exists():
            env["FS_EXTRA_CHROME_ARGS"] = "--headless=new"
            entry = _HIDDEN_WRAPPER

        print("[flaresolverr] starting local FlareSolverr for a Cloudflare "
              "check…", flush=True)
        # FlareSolverr's startup self-test opens Chrome and intermittently
        # dies with "no such window: target window already closed"
        # (~1 in 6 launches with Chrome 155) — just launch again.
        for attempt in range(_LAUNCH_ATTEMPTS):
            if _proc is None or _proc.poll() is not None:
                log = open(root / "flaresolverr-autostart.log", "ab")
                _proc = subprocess.Popen(
                    [str(python), "-u", str(entry)],
                    cwd=str(root), env=env, stdout=log, stderr=subprocess.STDOUT,
                    start_new_session=True,  # own process group → stop() reaches Chrome too
                )
                log.close()
                atexit.register(stop)

            deadline = time.monotonic() + _STARTUP_TIMEOUT
            while time.monotonic() < deadline:
                if _ping(base):
                    print("[flaresolverr] ready.", flush=True)
                    _failed_at = 0.0
                    return True
                if _proc.poll() is not None:
                    break
                time.sleep(0.5)
            if _proc.poll() is None:
                break  # still running but not answering — don't stack processes

        print(f"[flaresolverr] failed to start — see "
              f"{root / 'flaresolverr-autostart.log'}", flush=True)
        stop()
        _failed_at = time.monotonic()
        return False


def stop() -> None:
    """Stop the FlareSolverr we started (no-op if we didn't start one)."""
    global _proc
    proc, _proc = _proc, None
    if proc is None or proc.poll() is not None:
        return
    try:
        if os.name == "nt":
            proc.terminate()
        else:
            os.killpg(proc.pid, signal.SIGTERM)
        proc.wait(timeout=5)
    except Exception:
        try:
            if os.name != "nt":
                os.killpg(proc.pid, signal.SIGKILL)
            else:
                proc.kill()
        except Exception:
            pass
