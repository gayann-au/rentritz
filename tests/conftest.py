"""
Shared pytest fixtures.

SAFETY: this module refuses to run unless DATABASE_URL points at the isolated
`rentritz_test` database. Nothing here may ever touch production (`neondb`).

Every user created by a test gets a `pytest-<uuid>@example.com` email, and the
session teardown deletes every `pytest-%` user together with its dependent
rows, so repeated runs stay clean without needing a fresh database.
"""
import os
import sys
import uuid

import pytest
from dotenv import load_dotenv
from flask import g

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# ── Load the test environment BEFORE importing anything that reads config ────
_ENV_FILE = os.environ.get('ENV_FILE', '.env.test')
_ROOT     = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_ENV_PATH = os.path.join(_ROOT, _ENV_FILE)

if not os.path.exists(_ENV_PATH):
    raise RuntimeError(
        f'{_ENV_FILE} not found. Tests must run against the isolated test '
        f'database, never against .env (production).'
    )
load_dotenv(_ENV_PATH, override=True)

_DB_URL = os.environ.get('DATABASE_URL', '')
if 'rentritz_test' not in _DB_URL:
    raise RuntimeError(
        'REFUSING TO RUN: DATABASE_URL does not point at rentritz_test. '
        f'Got: ...{_DB_URL[-60:]}'
    )

os.environ.setdefault('MAIL_SUPPRESS_SEND', 'true')

from app import create_app, limiter                     # noqa: E402
from app.models import (                                # noqa: E402
    CreditLog, CreditReservation, LawyerBooking, LawyerProfile, LawyerReview,
    Payment, Question, User, db,
)

TEST_PASSWORD = 'AlphaTest!2026'
EMAIL_PREFIX  = 'pytest-'


def _purge_test_users(session):
    """Delete every pytest-created user and everything that depends on it."""
    ids = [r[0] for r in session.query(User.id)
           .filter(User.email.like(f'{EMAIL_PREFIX}%')).all()]
    if not ids:
        return
    _delete_users(session, ids)


def _delete_users(session, ids):
    """
    Delete users and their dependants in foreign-key-safe order.

    Deleting a User through the ORM is not enough: LawyerProfile.user has no
    delete cascade configured, so SQLAlchemy tries to NULL
    lawyer_profiles.user_id and trips its NOT NULL constraint.
    """
    profile_ids = [r[0] for r in session.query(LawyerProfile.id)
                   .filter(LawyerProfile.user_id.in_(ids)).all()]
    booking_ids = [r[0] for r in session.query(LawyerBooking.id).filter(
        db.or_(
            LawyerBooking.client_id.in_(ids),
            LawyerBooking.lawyer_profile_id.in_(profile_ids or [-1]),
        )
    ).all()]

    if booking_ids:
        LawyerReview.query.filter(
            LawyerReview.booking_id.in_(booking_ids)
        ).delete(synchronize_session=False)
    LawyerReview.query.filter(
        LawyerReview.client_id.in_(ids)
    ).delete(synchronize_session=False)
    if booking_ids:
        LawyerBooking.query.filter(
            LawyerBooking.id.in_(booking_ids)
        ).delete(synchronize_session=False)
    if profile_ids:
        LawyerProfile.query.filter(
            LawyerProfile.id.in_(profile_ids)
        ).delete(synchronize_session=False)

    CreditReservation.query.filter(
        CreditReservation.user_id.in_(ids)
    ).delete(synchronize_session=False)
    Question.query.filter(Question.user_id.in_(ids)).delete(synchronize_session=False)
    Payment.query.filter(Payment.user_id.in_(ids)).delete(synchronize_session=False)
    CreditLog.query.filter(CreditLog.user_id.in_(ids)).delete(synchronize_session=False)
    User.query.filter(User.id.in_(ids)).delete(synchronize_session=False)
    session.commit()


@pytest.fixture(scope='session')
def app():
    application = create_app('development')
    application.config.update(
        TESTING=True,
        WTF_CSRF_ENABLED=False,     # re-enabled explicitly in test_csrf.py
        MAIL_SUPPRESS_SEND=True,
    )
    # Must be set to None, not removed: Flask reads config["SERVER_NAME"]
    # unconditionally when building URLs.
    application.config['SERVER_NAME'] = None
    # Rate limits get their own test; they would otherwise make the smoke
    # suite flaky once it issues 70+ requests per role.
    limiter.enabled = False

    # In production every request gets its own app context, so Flask-Login's
    # per-context user cache starts empty. Tests hold an app context open
    # around the request, so without this the cached user survives from one
    # request to the next - a logged-out client still looked authenticated,
    # and state bled from one test into the next.
    @application.before_request
    def _drop_cached_login_user():
        g.pop('_login_user', None)

    with application.app_context():
        _purge_test_users(db.session)

    yield application

    with application.app_context():
        _purge_test_users(db.session)


@pytest.fixture(autouse=True)
def app_ctx(app):
    """
    One app context per test.

    Session-scoped would let `g` (and therefore the cached login user) leak
    between tests.
    """
    with app.app_context():
        yield


@pytest.fixture
def client(app, app_ctx):
    return app.test_client()


@pytest.fixture
def unique_email():
    def _make(prefix='user'):
        return f'{EMAIL_PREFIX}{prefix}-{uuid.uuid4().hex[:10]}@example.com'
    return _make


@pytest.fixture
def make_user(app, app_ctx, unique_email):
    """Create a committed user directly in the DB and return it."""
    created = []

    def _make(role='tenant', password=TEST_PASSWORD, is_active=True,
              is_verified=False, credits=10, full_name=None):
        user = User(
            full_name   = full_name or f'Pytest {role.title()}',
            email       = unique_email(role),
            role        = role,
            is_active   = is_active,
            is_verified = is_verified,
            credits     = credits,
        )
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        created.append(user.id)
        return user

    yield _make

    db.session.rollback()
    if created:
        _delete_users(db.session, created)


@pytest.fixture
def login(client):
    """Log a user in through the real login form for their role."""
    def _login(user, password=TEST_PASSWORD, follow_redirects=False):
        if user.role == 'lawyer':
            url = '/lawyers/login'
        elif user.role == 'admin':
            url = '/manage/login'
        else:
            url = '/auth/login'
        return client.post(url,
                           data={'email': user.email, 'password': password},
                           follow_redirects=follow_redirects)
    return _login


@pytest.fixture
def logged_in(make_user, login):
    """Create a user of the given role and authenticate the shared client."""
    def _make(role='tenant', **kwargs):
        user = make_user(role=role, **kwargs)
        login(user)
        return user
    return _make
