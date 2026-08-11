"""
Route smoke tests.

Walks every rule in the URL map as an anonymous visitor and as a logged-in
tenant, landlord, lawyer and admin, and asserts nothing returns a 5xx.

Redirects (302), forbidden (403) and not-found (404) are all acceptable
outcomes - the point is that no route blows up, no template is missing, and
no template references an undefined variable.
"""
import pytest

from app.models import Category, LawyerProfile, LawyerSpecialisation, db

ROLES = ['anonymous', 'tenant', 'landlord', 'lawyer', 'admin']

# Routes that would end the session mid-sweep, so they get targeted tests.
SKIP_ENDPOINTS = {
    'static',
    'auth.logout',
    'admin.logout',
}

# Admin endpoints that mutate shared reference data rather than pytest-owned
# rows. Sweeping them with an empty body deactivates real users and creates
# blank categories in the test database, which then leaks into later runs.
# They are covered deliberately in test_journeys.py instead.
SKIP_POST_ENDPOINTS = SKIP_ENDPOINTS | {
    'admin.toggle_user',
    'admin.add_credits',
    'admin.new_category',
    'admin.edit_category',
    'admin.toggle_category',
    'admin.new_specialisation',
    'admin.edit_specialisation',
    'admin.toggle_specialisation',
    'admin.new_scenario',
    'admin.tree_clear',
}


def _concrete_url(rule):
    """Substitute plausible values for URL converters, or None if unsupported."""
    url = rule.rule
    for name, converter in rule._converters.items():
        conv = type(converter).__name__
        if conv == 'IntegerConverter':
            value = '1'
        elif conv in ('UnicodeConverter', 'PathConverter', 'AnyConverter'):
            value = 'smoke-test-value'
        else:
            return None
        for token in (f'<{name}>', f'<int:{name}>', f'<string:{name}>',
                      f'<path:{name}>', f'<float:{name}>'):
            url = url.replace(token, value)
    if '<' in url:
        return None
    return url


def _all_rules(app, method):
    skip = SKIP_POST_ENDPOINTS if method == 'POST' else SKIP_ENDPOINTS
    out = set()
    for rule in app.url_map.iter_rules():
        if rule.endpoint in skip or method not in rule.methods:
            continue
        url = _concrete_url(rule)
        if url:
            out.add((rule.endpoint, url))
    return sorted(out)


@pytest.fixture
def seeded(app_ctx):
    """Guarantee the reference data the pages expect actually exists."""
    if not Category.query.first():
        db.session.add(Category(slug='smoke-cat', title='Smoke', for_role='both',
                                order=1, is_active=True))
    if not LawyerSpecialisation.query.first():
        db.session.add(LawyerSpecialisation(name='Smoke', slug='smoke', order=1))
    db.session.commit()


@pytest.mark.parametrize('role', ROLES)
def test_no_get_route_returns_500(app, client, make_user, login, seeded, role):
    if role != 'anonymous':
        login(make_user(role=role))

    failures = []
    for endpoint, url in _all_rules(app, 'GET'):
        try:
            resp = client.get(url)
        except Exception as e:                       # noqa: BLE001
            failures.append(f'{endpoint} {url} -> raised {type(e).__name__}: {e}')
            continue
        if resp.status_code >= 500:
            failures.append(f'{endpoint} {url} -> {resp.status_code}')

    assert not failures, (
        f'{len(failures)} GET route(s) returned 5xx as {role}:\n  '
        + '\n  '.join(failures)
    )


@pytest.mark.parametrize('role', ROLES)
def test_no_post_route_returns_500_on_empty_body(app, client, make_user, login,
                                                 seeded, role):
    """
    POST every endpoint with an empty form.

    A missing or malformed field must produce a 4xx or a redirect, never an
    unhandled 500.
    """
    if role != 'anonymous':
        login(make_user(role=role))

    failures = []
    for endpoint, url in _all_rules(app, 'POST'):
        try:
            resp = client.post(url, data={})
        except Exception as e:                       # noqa: BLE001
            failures.append(f'{endpoint} {url} -> raised {type(e).__name__}: {e}')
            continue
        if resp.status_code >= 500:
            failures.append(f'{endpoint} {url} -> {resp.status_code}')

    assert not failures, (
        f'{len(failures)} POST route(s) returned 5xx as {role}:\n  '
        + '\n  '.join(failures)
    )


# ─────────────────────────────────────────────────────────────────────────────
# Public pages must render for anonymous visitors
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize('url', [
    '/', '/terms', '/privacy', '/for-lawyers',
    '/auth/login', '/auth/register', '/auth/forgot-password',
    '/lawyers/login',
    '/manage/login',
])
def test_public_pages_render(client, url):
    resp = client.get(url)
    assert resp.status_code == 200, f'{url} returned {resp.status_code}'


@pytest.mark.parametrize('url', [
    '/dashboard', '/history', '/credits', '/lawyers/',
])
def test_protected_pages_redirect_anonymous(client, url):
    resp = client.get(url)
    assert resp.status_code == 302, f'{url} should redirect anonymous users'


def test_bare_admin_path_is_hidden(client):
    """/admin is deliberately a 404; the real panel lives at /manage."""
    assert client.get('/admin').status_code == 404
    assert client.get('/admin/').status_code == 404


def test_admin_panel_requires_admin(client, make_user, login):
    login(make_user(role='tenant'))
    resp = client.get('/manage/')
    assert resp.status_code == 302
    assert '/manage/login' in resp.headers['Location']


def test_lawyer_cannot_reach_client_dashboard(client, make_user, login):
    login(make_user(role='lawyer'))
    resp = client.get('/dashboard')
    assert resp.status_code == 303
    assert '/lawyers/' in resp.headers['Location']


def test_admin_is_not_offered_lawyer_registration(client, make_user, login):
    """
    Regression: an admin landing on /lawyers/register could submit the form,
    which set role='lawyer' and silently demoted the admin account.
    """
    admin = make_user(role='admin')
    login(admin)

    resp = client.get('/lawyers/register')
    assert resp.status_code == 302
    assert '/manage' in resp.headers['Location']

    resp = client.get('/lawyers/dashboard')
    assert resp.status_code == 302
    assert '/manage' in resp.headers['Location']

    db.session.refresh(admin)
    assert admin.role == 'admin', 'admin role must survive the lawyer portal'


def test_lawyer_without_profile_reaches_registration_without_looping(
        client, make_user, login):
    """Defect check: dashboard -> register must terminate, not ping-pong."""
    lawyer = make_user(role='lawyer')
    login(lawyer)
    assert LawyerProfile.query.filter_by(user_id=lawyer.id).first() is None

    resp = client.get('/lawyers/dashboard')
    assert resp.status_code == 302
    assert '/lawyers/register' in resp.headers['Location']

    # The next hop must render a page, not redirect again.
    assert client.get('/lawyers/register').status_code == 200
