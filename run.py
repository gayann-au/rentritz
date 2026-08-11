import logging
import os
import socket
import sys

from dotenv import load_dotenv

# ── Which env file? ──────────────────────────────────────────────────────────
# Defaults to .env (production). Set ENV_FILE=.env.test to point the app at the
# isolated test database instead:
#
#     ENV_FILE=.env.test python run.py
#
# The file is loaded before anything imports config.settings, which reads
# DATABASE_URL and SECRET_KEY at class-definition time.
ENV_FILE = os.environ.get('ENV_FILE', '.env')
if not os.path.exists(ENV_FILE):
    print(f'FATAL: env file {ENV_FILE!r} not found')
    sys.exit(1)
load_dotenv(ENV_FILE, override=True)

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
