import logging
import os
import socket
import sys

from dotenv import load_dotenv

# ── Which env file? ──────────────────────────────────────────────────────────
# Defaults to .env (local development). Set ENV_FILE=.env.test to point the app
# at the isolated test database instead:
#
#     ENV_FILE=.env.test python run.py
#
# The file is loaded before anything imports config.settings, which reads
# DATABASE_URL and SECRET_KEY at class-definition time.
#
# A missing file is NOT fatal: on Render -- and any other platform that injects
# configuration straight into the process environment -- there is no .env on
# disk and os.environ is already populated. What matters is that the required
# variables are present afterwards, whatever supplied them, which is the check
# below.
REQUIRED_ENV_VARS = ('DATABASE_URL', 'SECRET_KEY', 'ADMIN_EMAIL', 'ADMIN_PASSWORD')

ENV_FILE = os.environ.get('ENV_FILE', '.env')
if os.path.exists(ENV_FILE):
    load_dotenv(ENV_FILE, override=True)
else:
    # flush: the long-running server below never returns, so a buffered pipe
    # (Render's log collector) would otherwise sit on this line indefinitely.
    print(
        f'WARNING: env file {ENV_FILE!r} not found; '
        'using the process environment instead',
        flush=True,
    )

missing = [name for name in REQUIRED_ENV_VARS if not os.environ.get(name)]
if missing:
    print(f'FATAL: required environment variable(s) not set: {", ".join(missing)}')
    sys.exit(1)

# ── Global socket timeout ────────────────────────────────────────────────────
# Flask-Mail gives no way to pass a timeout down to smtplib, so without this a
# wedged SMTP connection blocks its thread until the OS gives up (minutes on
# Linux). Email now runs on background threads (app/emailer.py); this caps how
# long one of those threads can stay stuck, and also bounds the outbound
# nGenius payment calls.
socket.setdefaulttimeout(10)

from waitress import serve          # noqa: E402
from app import create_app          # noqa: E402

app = create_app(os.environ.get('FLASK_ENV', 'production'))

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    logging.getLogger(__name__).info(
        'Rentritz Dubai starting on port %s (env file: %s)', port, ENV_FILE
    )
    serve(app, host='0.0.0.0', port=port, threads=8)
