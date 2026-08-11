"""
End-to-end journeys for the four roles.

These follow the paths a real alpha user takes, using the actual HTTP
endpoints, and assert the money-relevant state (credits, bookings, reviews,
verification) ends up correct.
"""
import pytest

from app.models import (
    CreditLog, LawyerBooking, LawyerProfile, LawyerReview, LawyerSpecialisation,
    User, db,
)
from tests.conftest import TEST_PASSWORD

CLIENT_ROLES = ['tenant', 'landlord']


@pytest.fixture
def verified_lawyer(app_ctx, make_user):
    """A lawyer with a verified, contactable profile."""
    def _make(unlock_cost=5):
        user = make_user(role='lawyer', credits=0)
        profile = LawyerProfile(
            user_id                = user.id,
            display_name           = 'Pytest Advocate',
            bio                    = 'Tenancy disputes across Dubai.',
            phone                  = '+971500000000',
            whatsapp               = '+971500000000',
            contact_email          = 'advocate@example.com',
            office_city            = 'Dubai',
            verification_status    = 'verified',
            is_active              = True,
            is_available           = True,
            contact_unlock_credits = unlock_cost,
        )
        db.session.add(profile)
        db.session.commit()
        return user, profile
    return _make


# ─────────────────────────────────────────────────────────────────────────────
# TENANT / LANDLORD
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize('role', CLIENT_ROLES)
def test_client_core_pages(client, make_user, login, role):
    user = make_user(role=role, credits=10)
    login(user)

    for url in ('/dashboard', '/history', '/credits', '/lawyers/'):
        assert client.get(url).status_code == 200, f'{url} failed for {role}'

    assert client.get('/api/v1/credits/balance').get_json()['credits'] == 10


@pytest.mark.parametrize('role', CLIENT_ROLES)
def test_client_gets_signup_credits(client, unique_email, role):
    """Registration must grant the free credits and log them."""
    email = unique_email(role)
    client.post('/auth/register', data={
        'full_name': 'Credit Getter', 'email': email,
        'password': TEST_PASSWORD, 'role': role,
    })
    user = User.query.filter_by(email=email).first()
    assert user.credits == 2
    log = CreditLog.query.filter_by(user_id=user.id, action='signup_bonus').first()
    assert log is not None and log.amount == 2


def test_client_can_browse_and_view_a_lawyer(client, make_user, login,
                                             verified_lawyer):
    _, profile = verified_lawyer()
    login(make_user(role='tenant', credits=10))

    listing = client.get('/lawyers/')
    assert listing.status_code == 200
    assert b'Pytest Advocate' in listing.data

    assert client.get(f'/lawyers/{profile.id}').status_code == 200


def test_unlock_spends_credits_and_reveals_contact(client, make_user, login,
                                                   verified_lawyer):
    """The paid path: unlock costs credits and returns the contact details."""
    _, profile = verified_lawyer(unlock_cost=5)
    tenant = make_user(role='tenant', credits=10)
    login(tenant)

    resp = client.post(f'/lawyers/{profile.id}/unlock',
                       data={'client_note': 'Eviction notice received',
                             'contact_method': 'whatsapp'})
    assert resp.status_code == 200
    body = resp.get_json()
    assert body['success'] is True
    assert body['phone'] == '+971500000000'
    assert body['credits_remaining'] == 5

    db.session.refresh(tenant)
    assert tenant.credits == 5

    booking = LawyerBooking.query.filter_by(
        client_id=tenant.id, lawyer_profile_id=profile.id).first()
    assert booking is not None
    assert booking.status == 'contact_unlocked'
    assert booking.credits_charged == 5

    assert CreditLog.query.filter_by(
        user_id=tenant.id, action='lawyer_unlock').first() is not None


def test_unlocked_contact_stays_visible_on_the_profile_page(
        client, make_user, login, verified_lawyer):
    """
    Regression: contact_unlocked was hard-coded False, so a client who had
    already paid saw the "Unlock Contact" box again and never got the number.
    """
    _, profile = verified_lawyer()
    login(make_user(role='tenant', credits=10))

    client.post(f'/lawyers/{profile.id}/unlock', data={})

    page = client.get(f'/lawyers/{profile.id}')
    assert page.status_code == 200
    assert b'+971500000000' in page.data, 'paid-for contact details are not shown'


def test_unlock_is_idempotent(client, make_user, login, verified_lawyer):
    """A second unlock must not double-charge."""
    _, profile = verified_lawyer(unlock_cost=5)
    tenant = make_user(role='tenant', credits=10)
    login(tenant)

    client.post(f'/lawyers/{profile.id}/unlock', data={})
    resp = client.post(f'/lawyers/{profile.id}/unlock', data={})
    assert resp.get_json().get('already_unlocked') is True

    db.session.refresh(tenant)
    assert tenant.credits == 5, 'client was charged twice for one lawyer'


def test_unlock_without_enough_credits_is_refused(client, make_user, login,
                                                  verified_lawyer):
    _, profile = verified_lawyer(unlock_cost=5)
    tenant = make_user(role='tenant', credits=1)
    login(tenant)

    resp = client.post(f'/lawyers/{profile.id}/unlock', data={})
    assert resp.status_code == 402
    assert resp.get_json()['error'] == 'insufficient_credits'

    db.session.refresh(tenant)
    assert tenant.credits == 1, 'credits must not move on a refused unlock'


def test_client_can_review_after_unlocking(client, make_user, login,
                                           verified_lawyer):
    _, profile = verified_lawyer()
    tenant = make_user(role='tenant', credits=10)
    login(tenant)

    client.post(f'/lawyers/{profile.id}/unlock', data={})
    resp = client.post(f'/lawyers/{profile.id}/review',
                       data={'rating': '5', 'comment': 'Very helpful.'},
                       follow_redirects=False)
    assert resp.status_code == 302

    review = LawyerReview.query.filter_by(
        client_id=tenant.id, lawyer_profile_id=profile.id).first()
    assert review is not None
    assert review.rating == 5

    db.session.refresh(profile)
    assert profile.total_reviews == 1
    assert float(profile.average_rating) == 5.0


def test_review_without_a_booking_is_refused(client, make_user, login,
                                             verified_lawyer):
    _, profile = verified_lawyer()
    tenant = make_user(role='tenant', credits=10)
    login(tenant)

    client.post(f'/lawyers/{profile.id}/review', data={'rating': '5'})
    assert LawyerReview.query.filter_by(client_id=tenant.id).first() is None


def test_payment_route_reports_gateway_not_configured(client, make_user, login):
    """nGenius has no keys in the alpha; this must be a clean 503, not a crash."""
    login(make_user(role='tenant'))
    resp = client.post('/pay/create-order', json={'pack': 'starter'})
    assert resp.status_code in (503, 400)
    assert 'error' in resp.get_json()


# ─────────────────────────────────────────────────────────────────────────────
# LAWYER
# ─────────────────────────────────────────────────────────────────────────────

def test_lawyer_can_create_a_profile_and_await_verification(
        client, make_user, login, app_ctx):
    lawyer = make_user(role='lawyer')
    login(lawyer)

    spec = LawyerSpecialisation.query.filter_by(is_active=True).first()
    if spec is None:
        spec = LawyerSpecialisation(name='Tenancy J', slug='tenancy-j', order=1)
        db.session.add(spec)
        db.session.commit()

    assert client.get('/lawyers/register').status_code == 200

    resp = client.post('/lawyers/register', data={
        'display_name':           'New Advocate',
        'bio':                    'A' * 60,
        'years_experience':       '7',
        'phone':                  '+971501112222',
        'contact_email':          'new.advocate@example.com',
        'office_city':            'Dubai',
        'office_country':         'UAE',
        'contact_unlock_credits': '5',
        'specialisation_ids':     [str(spec.id)],
    }, follow_redirects=False)
    assert resp.status_code == 302

    profile = LawyerProfile.query.filter_by(user_id=lawyer.id).first()
    assert profile is not None
    assert profile.verification_status == 'pending_review', (
        'a new lawyer must not be self-verifying'
    )

    # Unverified lawyers must not appear in the public listing.
    client.get('/auth/logout')
    login(make_user(role='tenant', credits=5))
    assert b'New Advocate' not in client.get('/lawyers/').data


def test_lawyer_dashboard_shows_bookings_and_can_complete_them(
        client, make_user, login, verified_lawyer):
    lawyer_user, profile = verified_lawyer()

    tenant = make_user(role='tenant', credits=20)
    login(tenant)
    client.post(f'/lawyers/{profile.id}/unlock', data={})
    booking = LawyerBooking.query.filter_by(client_id=tenant.id).first()
    client.get('/auth/logout')

    login(lawyer_user)
    assert client.get('/lawyers/dashboard').status_code == 200

    resp = client.post(f'/lawyers/bookings/{booking.id}/respond')
    assert resp.status_code == 200
    assert resp.get_json()['success'] is True

    resp = client.post(f'/lawyers/bookings/{booking.id}/complete')
    assert resp.status_code == 200

    db.session.refresh(booking)
    assert booking.status == 'completed'
    assert booking.completed_at is not None

    db.session.refresh(profile)
    assert profile.total_completed_bookings == 1


def test_lawyer_cannot_touch_another_lawyers_booking(
        client, make_user, login, verified_lawyer):
    _, profile = verified_lawyer()
    tenant = make_user(role='tenant', credits=20)
    login(tenant)
    client.post(f'/lawyers/{profile.id}/unlock', data={})
    booking = LawyerBooking.query.filter_by(client_id=tenant.id).first()
    client.get('/auth/logout')

    intruder, _ = verified_lawyer()
    login(intruder)
    assert client.post(f'/lawyers/bookings/{booking.id}/complete').status_code == 403


def test_lawyer_can_toggle_availability(client, verified_lawyer, login):
    lawyer_user, profile = verified_lawyer()
    login(lawyer_user)
    resp = client.post('/lawyers/toggle-availability')
    assert resp.status_code == 200
    assert resp.get_json()['is_available'] is False


# ─────────────────────────────────────────────────────────────────────────────
# ADMIN
# ─────────────────────────────────────────────────────────────────────────────

ADMIN_PAGES = [
    '/manage/', '/manage/users', '/manage/questions', '/manage/payments',
    '/manage/categories', '/manage/scenarios', '/manage/lawyers/',
    '/manage/specialisations', '/manage/import',
]


@pytest.mark.parametrize('url', ADMIN_PAGES)
def test_admin_pages_render(client, make_user, login, url):
    login(make_user(role='admin'))
    assert client.get(url).status_code == 200, f'{url} failed'


def test_admin_pending_count_api(client, make_user, login):
    login(make_user(role='admin'))
    resp = client.get('/manage/api/pending-count')
    assert resp.status_code == 200
    assert {'pending', 'locked', 'lawyer_pending'} <= set(resp.get_json())


def test_admin_can_verify_a_lawyer(client, make_user, login, app_ctx):
    lawyer = make_user(role='lawyer')
    profile = LawyerProfile(
        user_id=lawyer.id, display_name='Awaiting Review',
        bio='Pending.', phone='+971509998888',
        verification_status='pending_review', is_active=True,
    )
    db.session.add(profile)
    db.session.commit()

    admin = make_user(role='admin')
    login(admin)

    assert client.get(f'/manage/lawyers/{profile.id}').status_code == 200

    resp = client.post(f'/manage/lawyers/{profile.id}/verify',
                       data={'admin_notes': 'Bar card checked.'},
                       follow_redirects=False)
    assert resp.status_code == 302

    db.session.refresh(profile)
    assert profile.verification_status == 'verified'
    assert profile.verified_at is not None
    assert profile.verified_by_admin_id == admin.id


def test_admin_can_reject_a_lawyer_with_a_reason(client, make_user, login, app_ctx):
    lawyer = make_user(role='lawyer')
    profile = LawyerProfile(user_id=lawyer.id, display_name='To Reject',
                            verification_status='pending_review', is_active=True)
    db.session.add(profile)
    db.session.commit()

    login(make_user(role='admin'))

    # A rejection with no reason must be refused.
    client.post(f'/manage/lawyers/{profile.id}/reject', data={})
    db.session.refresh(profile)
    assert profile.verification_status == 'pending_review'

    client.post(f'/manage/lawyers/{profile.id}/reject',
                data={'reason': 'Bar number could not be confirmed.'})
    db.session.refresh(profile)
    assert profile.verification_status == 'rejected'
    assert profile.rejection_reason


def test_admin_can_manage_users(client, make_user, login):
    target = make_user(role='tenant', credits=0)
    login(make_user(role='admin'))

    assert client.get(f'/manage/users/{target.id}/detail').status_code == 200

    client.post(f'/manage/users/{target.id}/credits', data={'amount': '5'})
    db.session.refresh(target)
    assert target.credits == 5

    client.post(f'/manage/users/{target.id}/toggle')
    db.session.refresh(target)
    assert target.is_active is False

    client.post(f'/manage/users/{target.id}/toggle')
    db.session.refresh(target)
    assert target.is_active is True


def test_admin_credit_grant_is_bounded(client, make_user, login):
    target = make_user(role='tenant', credits=0)
    login(make_user(role='admin'))

    client.post(f'/manage/users/{target.id}/credits', data={'amount': '10000'})
    db.session.refresh(target)
    assert target.credits == 0, 'out-of-range grant must be refused'


def test_admin_logout_clears_admin_session(client, make_user, login):
    login(make_user(role='admin'))
    assert client.get('/manage/').status_code == 200
    client.get('/manage/logout')
    resp = client.get('/manage/')
    assert resp.status_code == 302
    assert '/manage/login' in resp.headers['Location']
