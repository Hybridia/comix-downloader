"""
Run FlareSolverr with extra Chrome flags — used to keep its browser in
the background (``--headless=new``) on macOS.

FlareSolverr has no setting for browser flags, and its own HEADLESS mode
means Xvfb on macOS (Linux-only), so out of the box Chrome pops up a
window on every solve. Rather than editing the FlareSolverr checkout,
this wrapper adds the flags from ``FS_EXTRA_CHROME_ARGS`` (``|``-separated)
to every ``ChromeOptions`` it creates, then runs FlareSolverr unchanged.
Verified 2026-10-21: manhwaread's Cloudflare check is solved in the new
headless mode, and FlareSolverr's reported User-Agent stays a normal
Chrome one.

Must be run with FlareSolverr's own interpreter, from its install dir:

    cd ~/Documents/FlareSolverr && .venv/bin/python /path/to/flaresolverr_hidden.py

``src/utils/flaresolverr_launcher.py`` and ``scripts/start_flaresolverr.sh``
both do exactly that.
"""

import os
import runpy
import sys

src = os.path.join(os.getcwd(), "src")
sys.path.insert(0, src)

import undetected_chromedriver as uc  # noqa: E402  (FlareSolverr's dependency)

_EXTRA = [a for a in os.environ.get("FS_EXTRA_CHROME_ARGS", "").split("|") if a]
_orig_init = uc.ChromeOptions.__init__


def _init_with_extra_args(self, *args, **kwargs):
    _orig_init(self, *args, **kwargs)
    for arg in _EXTRA:
        self.add_argument(arg)


uc.ChromeOptions.__init__ = _init_with_extra_args

sys.argv = [os.path.join(src, "flaresolverr.py")]
runpy.run_path(sys.argv[0], run_name="__main__")
