"""
Authentication behaviour: registration, immediate login, wrong password,
lockout, and the removal of the mandatory-verification gate.
"""
from datetime import datetime, timedelta

import pytest

from app.models import User, db
from app.security import FAILED_ATTEMPTS_BEFORE_LOCKOUT
from tests.conftest import TEST_PASSWORD

CLIENT_ROLES = ['tenant', 'landlord']


# ─────────────────────────────────────────────────────────────────────────────
# Register, then log in immediately (no email verification step)
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize('role', CLIENT_ROLES)
def test_register_then_login_immediately(client, unique_email, role):
    email = unique_email(role)

    resp = client.post('/auth/register', data={
        'full_name': 'Alpha Tester',
        'email':     email,
        'password':  TEST_PASSWORD,
        'role':      role,
    }, follow_redirects=False)
    assert resp.status_code == 302, 'registration should redirect on success'
    assert '/auth/login' in resp.headers['Location']

    user = User.query.filter_by(email=email).first()
    assert user is not None
    assert user.role == role
    assert user.is_verified is False, 'verification must NOT be required'
    assert user.is_active is True

    # The whole point: log in straight away, without clicking any email link.
    resp = client.post('/auth/login',
                       data={'email': email, 'password': TEST_PASSWORD},
                       follow_redirects=False)
    assert resp.status_code == 302
    assert '/dashboard' in resp.headers['Location']

    assert client.get('/dashboard').status_code == 200


def test_register_lawyer_then_login_via_lawyer_portal(client, unique_email):
    """A lawyer must be sent to the lawyer portal, not the client login."""
    email = unique_email('lawyer')

    resp = client.post('/auth/register', data={
        'full_name': 'Alpha Advocate',
        'email':     email,
        'password':  TEST_PASSWORD,
        'role':      'lawyer',
    }, follow_redirects=False)
    assert resp.status_code == 302
    assert '/lawyers/login' in resp.headers['Location'], (
        'lawyers used to be redirected to the client login, which rejects them'
    )

    user = User.query.filter_by(email=email).first()
    assert user.is_verified is False

    resp = client.post('/lawyers/login',
                       data={'email': email, 'password': TEST_PASSWORD},
                       follow_redirects=False)
    assert resp.status_code == 302
    assert '/lawyers/' in resp.headers['Location']


def test_admin_can_log_in_at_manage_login(client, make_user):
    admin = make_user(role='admin')
    resp = client.post('/manage/login',
                       data={'email': admin.email, 'password': TEST_PASSWORD},
                       follow_redirects=False)
    assert resp.status_code == 302
    assert '/manage' in resp.headers['Location']
    assert client.get('/manage/').status_code == 200


def test_unverified_user_can_log_in(client, make_user):
    """Regression: is_verified=False used to block login entirely."""
    user = make_user(role='tenant', is_verified=False)
    resp = client.post('/auth/login',
                       data={'email': user.email, 'password': TEST_PASSWORD},
                       follow_redirects=True)
    assert resp.status_code == 200
    assert b'verify your email before logging in' not in resp.data.lower()


# ─────────────────────────────────────────────────────────────────────────────
# Failure paths
# ─────────────────────────────────────────────────────────────────────────────

def test_login_with_wrong_password_is_rejected(client, make_user):
    user = make_user(role='tenant')
    resp = client.post('/auth/login',
                       data={'email': user.email, 'password': 'totally-wrong'},
                       follow_redirects=False)
    assert resp.status_code == 200, 'should re-render the form, not redirect'
    assert b'Incorrect email or password' in resp.data
    assert client.get('/dashboard').status_code == 302, 'must not be signed in'


def test_login_with_unknown_email_is_rejected(client):
    resp = client.post('/auth/login',
                       data={'email': 'pytest-nobody@example.com',
                             'password': TEST_PASSWORD})
    assert resp.status_code == 200
    assert b'Incorrect email or password' in resp.data


def test_login_with_locked_account_is_rejected(client, make_user):
    user = make_user(role='tenant')
    user.failed_login_count   = FAILED_ATTEMPTS_BEFORE_LOCKOUT
    user.failed_login_lockout = datetime.utcnow() + timedelta(minutes=5)
    db.session.commit()

    resp = client.post('/auth/login',
                       data={'email': user.email, 'password': TEST_PASSWORD})
    assert resp.status_code == 200
    assert b'Too many failed attempts' in resp.data
    assert client.get('/dashboard').status_code == 302


def test_lockout_is_self_clearing(client, make_user):
    """An expired lockout must reset the counter, not stay permanently tripped."""
    user = make_user(role='tenant')
    user.failed_login_count   = FAILED_ATTEMPTS_BEFORE_LOCKOUT
    user.failed_login_lockout = datetime.utcnow() - timedelta(minutes=1)  # expired
    db.session.commit()

    resp = client.post('/auth/login',
                       data={'email': user.email, 'password': TEST_PASSWORD},
                       follow_redirects=False)
    assert resp.status_code == 302, 'expired lockout must not block a correct password'

    db.session.refresh(user)
    assert user.failed_login_count == 0
    assert user.failed_login_lockout is None


def test_lockout_needs_ten_failures(client, make_user):
    """Three mistakes must not lock anyone out any more."""
    user = make_user(role='tenant')
    for _ in range(3):
        client.post('/auth/login',
                    data={'email': user.email, 'password': 'wrong'})
    db.session.refresh(user)
    assert user.failed_login_lockout is None

    resp = client.post('/auth/login',
                       data={'email': user.email, 'password': TEST_PASSWORD},
                       follow_redirects=False)
    assert resp.status_code == 302, 'correct password must still work after 3 typos'


def test_deactivated_account_is_rejected(client, make_user):
    user = make_user(role='tenant', is_active=False)
    resp = client.post('/auth/login',
                       data={'email': user.email, 'password': TEST_PASSWORD})
    assert resp.status_code == 200
    assert b'deactivated' in resp.data


# ─────────────────────────────────────────────────────────────────────────────
# Registration validation
# ─────────────────────────────────────────────────────────────────────────────

def test_apostrophe_in_name_is_accepted(client, unique_email):
    """Regression: the old SQLi-ish filter rejected every O'Brien."""
    email = unique_email('oh')
    resp = client.post('/auth/register', data={
        'full_name': "Siobhan O'Brien",
        'email':     email,
        'password':  TEST_PASSWORD,
        'role':      'tenant',
    }, follow_redirects=False)
    assert resp.status_code == 302
    assert User.query.filter_by(email=email).first() is not None


def test_duplicate_email_is_rejected(client, make_user):
    existing = make_user(role='tenant')
    resp = client.post('/auth/register', data={
        'full_name': 'Someone Else',
        'email':     existing.email,
        'password':  TEST_PASSWORD,
        'role':      'tenant',
    })
    assert resp.status_code == 200
    assert b'already exists' in resp.data


def test_short_password_is_rejected(client, unique_email):
    resp = client.post('/auth/register', data={
        'full_name': 'Shorty',
        'email':     unique_email('short'),
        'password':  'abc',
        'role':      'tenant',
    })
    assert resp.status_code == 200
    assert b'at least 8 characters' in resp.data


def test_invalid_role_is_rejected(client, unique_email):
    resp = client.post('/auth/register', data={
        'full_name': 'Sneaky',
        'email':     unique_email('role'),
        'password':  TEST_PASSWORD,
        'role':      'admin',          # must not be self-assignable
    })
    assert resp.status_code == 200
    assert b'valid role' in resp.data


def test_logout_clears_the_session(client, make_user, login):
    user = make_user(role='tenant')
    login(user)
    assert client.get('/dashboard').status_code == 200
    client.get('/auth/logout')
    assert client.get('/dashboard').status_code == 302
