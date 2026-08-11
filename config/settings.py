import os
import sys
from datetime import timedelta
from sqlalchemy.engine.url import make_url


def _get_database_url():
    url = os.environ.get('DATABASE_URL', '')
    if not url:
        print('FATAL: DATABASE_URL not set in .env')
        sys.exit(1)
    if url.startswith('postgres://'):
        url = url.replace('postgres://', 'postgresql://', 1)
    try:
        make_url(url)
    except Exception:
        print('FATAL: DATABASE_URL is not a valid PostgreSQL connection string.')
        sys.exit(1)
    return url


def _get_secret_key():
    key = os.environ.get('SECRET_KEY', '')
    if not key:
        print('FATAL: SECRET_KEY not set in .env')
        sys.exit(1)
    if len(key) < 32:
        print('FATAL: SECRET_KEY must be at least 32 characters.')
        sys.exit(1)
    return key


class Config:
    SECRET_KEY               = _get_secret_key()
    SQLALCHEMY_DATABASE_URI  = _get_database_url()
    DEBUG                    = os.environ.get('DEBUG', 'false').lower() == 'true'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        'pool_size':         10,
        'max_overflow':      20,
        'pool_recycle':      300,
        'pool_pre_ping':     True,
    }

    # ── External URL generation ──────────────────────────────────────────────
    # Verification and password-reset links are built with _external=True. Behind
    # Render's proxy the request arrives as plain HTTP, so without this the links
    # come out as http://. ProxyFix (app/__init__.py) supplies the real host and
    # scheme for in-request URL building; PREFERRED_URL_SCHEME covers the rest.
    #
    # SERVER_NAME is deliberately opt-in: when set, Flask refuses any request
    # whose Host header does not match, which silently 404s health checks and
    # custom domains. Set it only if you need url_for() outside a request.
    PREFERRED_URL_SCHEME = os.environ.get('PREFERRED_URL_SCHEME', 'https')
    _server_name         = (os.environ.get('SERVER_NAME') or '').strip()
    if _server_name:
        SERVER_NAME = _server_name

    MAIL_SERVER         = 'smtp.gmail.com'
    MAIL_PORT           = 587
    MAIL_USE_TLS        = True
    MAIL_USERNAME       = os.environ.get('MAIL_USERNAME')
    MAIL_PASSWORD       = (os.environ.get('MAIL_PASSWORD') or '').replace(' ', '')
    MAIL_DEFAULT_SENDER = os.environ.get('MAIL_USERNAME')
    MAIL_SUPPRESS_SEND  = os.environ.get('MAIL_SUPPRESS_SEND', 'false').lower() == 'true'

    # Admin address used for lawyer-registration notifications.
    ADMIN_EMAIL = os.environ.get('ADMIN_EMAIL', '')

    # Trust exactly one proxy hop (Render). Disable only when running with no
    # reverse proxy in front, otherwise X-Forwarded-For could be spoofed.
    TRUST_PROXY = os.environ.get('TRUST_PROXY', 'true').lower() == 'true'

    LOG_DIR = os.environ.get('LOG_DIR', '')

    NGENIUS_OUTLET_ID = os.environ.get('NGENIUS_OUTLET_ID')
    NGENIUS_API_KEY   = os.environ.get('NGENIUS_API_KEY')
    NGENIUS_ENV       = os.environ.get('NGENIUS_ENV', 'TEST')

    SESSION_COOKIE_HTTPONLY   = True
    SESSION_COOKIE_SAMESITE   = 'Lax'
    SESSION_COOKIE_NAME       = '_rs'
    PERMANENT_SESSION_LIFETIME = timedelta(hours=24)

    # CSRF stays on. What is switched off is the token's separate 1-hour clock:
    # by default a login or wizard page left open for an hour submits with an
    # "expired" token and the user gets an opaque 400. The token is still bound
    # to the session cookie, which is what actually stops cross-site forgery,
    # and that cookie expires on its own schedule above.
    WTF_CSRF_TIME_LIMIT = None

    FREE_CREDITS_ON_SIGNUP = 2

    UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'uploads')

    CREDIT_PACKS = [
        {
            'id':          'starter',
            'name':        'Starter',
            'credits':     3,
            'price_aed':   '24.99',
            'price_fils':  2499,
            'per_consult': '8.33',
            'popular':     False,
        },
        {
            'id':          'standard',
            'name':        'Standard',
            'credits':     7,
            'price_aed':   '48.99',
            'price_fils':  4899,
            'per_consult': '6.99',
            'popular':     True,
        },
        {
            'id':          'pro',
            'name':        'Pro',
            'credits':     15,
            'price_aed':   '88.99',
            'price_fils':  8899,
            'per_consult': '5.93',
            'popular':     False,
        },
    ]


class DevelopmentConfig(Config):
    SESSION_COOKIE_SECURE = False


class ProductionConfig(Config):
    DEBUG                 = False
    SESSION_COOKIE_SECURE = True  # always require HTTPS in production


config = {
    'development': DevelopmentConfig,
    'production':  ProductionConfig,
    'default':     ProductionConfig,
}