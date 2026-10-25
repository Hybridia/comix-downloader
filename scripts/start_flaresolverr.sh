#!/bin/sh
# Start FlareSolverr by hand (the app normally starts it automatically on
# the first Cloudflare human check — see src/utils/flaresolverr_launcher.py).
#
# Installed from source at ~/Documents/FlareSolverr (v3.5.2) because there
# is no macOS release build. Notes:
#   HEADLESS=false + flaresolverr_hidden.py — FlareSolverr's own HEADLESS
#                     means Xvfb (Linux-only); instead Chrome gets
#                     --headless=new, so no window appears.
#                     Set FS_EXTRA_CHROME_ARGS= (empty) to watch it work.
#   HOST=127.0.0.1  — only this Mac can use it (the default listens on the
#                     whole network).
here="$(cd "$(dirname "$0")" && pwd)"
cd "${FLARESOLVERR_DIR:-$HOME/Documents/FlareSolverr}" || exit 1
FS_EXTRA_CHROME_ARGS="${FS_EXTRA_CHROME_ARGS---headless=new}" \
HOST=127.0.0.1 HEADLESS=false LOG_LEVEL=info \
exec .venv/bin/python -u "$here/flaresolverr_hidden.py"
