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

    MAIL_SERVER         = 'smtp.gmail.com'
    MAIL_PORT           = 587
    MAIL_USE_TLS        = True
    MAIL_USERNAME       = os.environ.get('MAIL_USERNAME')
    MAIL_PASSWORD       = (os.environ.get('MAIL_PASSWORD') or '').replace(' ', '')
    MAIL_DEFAULT_SENDER = os.environ.get('MAIL_USERNAME')

    NGENIUS_OUTLET_ID = os.environ.get('NGENIUS_OUTLET_ID')
    NGENIUS_API_KEY   = os.environ.get('NGENIUS_API_KEY')
    NGENIUS_ENV       = os.environ.get('NGENIUS_ENV', 'TEST')

    SESSION_COOKIE_HTTPONLY   = True
    SESSION_COOKIE_SAMESITE   = 'Lax'
    SESSION_COOKIE_NAME       = '_rs'
    PERMANENT_SESSION_LIFETIME = timedelta(hours=24)

    FREE_CREDITS_ON_SIGNUP = 3

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