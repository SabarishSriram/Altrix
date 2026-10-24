"""Vercel entrypoint for the Altrix API (staged by scripts/stage_api_deploy.py).

Vercel looks for a FastAPI `app` in a root index.py. The deployment is
read-only: the constituent list comes from the bundled snapshot (NSE often
blocks cloud IPs) and downloads are disabled, because the filesystem does not
persist. New market data arrives with each redeploy.
"""

import os

os.environ.setdefault("ALTRIX_OFFLINE", "1")
os.environ.setdefault("ALTRIX_DISABLE_DOWNLOAD", "1")

from api.main import app  # noqa: E402,F401
