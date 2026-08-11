"""
CSRF protection.

The rest of the suite runs with WTF_CSRF_ENABLED=False for convenience, so
these tests turn it back on and assert that state-changing POSTs are actually
rejected without a valid token - and accepted with one.
"""
import re

import pytest

from tests.conftest import TEST_PASSWORD

CSRF_INPUT_RE = re.compile(rb'name="csrf_token"[^>]*value="([^"]+)"')


@pytest.fixture
def csrf_app(app):
    """Enable CSRF for the duration of one test."""
    app.config['WTF_CSRF_ENABLED'] = True
    yield app
    app.config['WTF_CSRF_ENABLED'] = False


@pytest.fixture
def csrf_client(csrf_app):
    return csrf_app.test_client()


def _token_from(html):
    match = CSRF_INPUT_RE.search(html)
    return match.group(1).decode() if match else None


@pytest.mark.parametrize('url,payload', [
    ('/auth/login',    {'email': 'pytest-csrf@example.com', 'password': TEST_PASSWORD}),
    ('/auth/register', {'full_name': 'CSRF Probe',
                        'email': 'pytest-csrf-reg@example.com',
                        'password': TEST_PASSWORD, 'role': 'tenant'}),
    ('/lawyers/login', {'email': 'pytest-csrf@example.com', 'password': TEST_PASSWORD}),
    ('/manage/login',  {'email': 'pytest-csrf@example.com', 'password': TEST_PASSWORD}),
    ('/auth/forgot-password', {'email': 'pytest-csrf@example.com'}),
])
def test_post_without_csrf_token_is_rejected(csrf_client, url, payload):
    resp = csrf_client.post(url, data=payload)
    assert resp.status_code == 400, (
        f'{url} accepted a POST with no CSRF token (got {resp.status_code})'
    )


def test_post_with_bogus_csrf_token_is_rejected(csrf_client):
    resp = csrf_client.post('/auth/login', data={
        'email': 'pytest-csrf@example.com',
        'password': TEST_PASSWORD,
        'csrf_token': 'not-a-real-token',
    })
    assert resp.status_code == 400


def test_login_form_serves_a_usable_csrf_token(csrf_client, make_user):
    """The token embedded in the real form must be accepted."""
    user = make_user(role='tenant')

    page = csrf_client.get('/auth/login')
    assert page.status_code == 200
    token = _token_from(page.data)
    assert token, 'login page did not render a csrf_token input'

    # PREFERRED_URL_SCHEME is https, so the test client issues HTTPS requests
    # and Flask-WTF's SSL-strict mode also requires a Referer - exactly what a
    # real browser sends under the app's strict-origin-when-cross-origin policy.
    resp = csrf_client.post('/auth/login', data={
        'email': user.email,
        'password': TEST_PASSWORD,
        'csrf_token': token,
    }, headers={'Referer': 'https://localhost/auth/login'},
       follow_redirects=False)
    assert resp.status_code == 302, 'valid token should let the login through'


def test_csrf_survives_a_stale_page(csrf_client, make_user):
    """
    WTF_CSRF_TIME_LIMIT is disabled, so a token minted long before submission
    is still accepted as long as the session cookie holds. Without that, a
    login page left open for an hour 400s on submit.
    """
    user = make_user(role='tenant')
    token = _token_from(csrf_client.get('/auth/login').data)

    # Several unrelated requests later, the same token must still work.
    for _ in range(3):
        csrf_client.get('/auth/register')

    resp = csrf_client.post('/auth/login', data={
        'email': user.email,
        'password': TEST_PASSWORD,
        'csrf_token': token,
    }, headers={'Referer': 'https://localhost/auth/login'},
       follow_redirects=False)
    assert resp.status_code == 302


def test_csrf_failure_renders_the_400_page(csrf_client):
    resp = csrf_client.post('/auth/login', data={'email': 'a@b.com',
                                                 'password': 'x' * 10})
    assert resp.status_code == 400
    # Custom error template, not a Werkzeug stack trace.
    assert b'<html' in resp.data.lower()
