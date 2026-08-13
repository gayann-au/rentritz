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

# ── Which mode? ──────────────────────────────────────────────────────────────
# Production stays the default, because this same module is what Render runs.
# Pass --dev for a local run:
#
#     python run.py --dev
#
# That selects DevelopmentConfig, which enables TEMPLATES_AUTO_RELOAD
# (app/__init__.py) and relaxes SESSION_COOKIE_SECURE so sessions survive over
# plain http on localhost. It does NOT switch on Flask's debugger -- DEBUG is
# still read from the DEBUG env var and defaults to false.
#
# Why the flag exists: without TEMPLATES_AUTO_RELOAD, Jinja compiles each
# template once, on first render, and caches it for the life of the process.
# Editing a template then changes nothing the server returns, and no amount of
# browser hard-reloading helps, because the staleness is server-side. That
# silently invalidated a run of visual checks during the design migration
# (F14 in DESIGN_MIGRATION.md). Explicit flag, so production is never switched
# on by accident.
DEV_MODE = '--dev' in sys.argv
DEFAULT_ENV = 'development' if DEV_MODE else 'production'

app = create_app(os.environ.get('FLASK_ENV', DEFAULT_ENV))

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    logging.getLogger(__name__).info(
        'Rentritz Dubai starting on port %s (env file: %s, mode: %s)',
        port, ENV_FILE, 'development' if DEV_MODE else 'production'
    )
    if DEV_MODE:
        print('DEV MODE: template auto-reload ON', flush=True)
    serve(app, host='0.0.0.0', port=port, threads=8)
