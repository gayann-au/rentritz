"""
seed_test_accounts.py

Creates (or refreshes) one login per role with a known password, so the four
user journeys can be walked by hand.

USAGE
    ENV_FILE=.env.test python scripts/seed_test_accounts.py

    # against production, deliberately:
    ENV_FILE=.env python scripts/seed_test_accounts.py --allow-production

The script is idempotent: running it again resets the passwords and balances
rather than creating duplicates. It never deletes anything.

The lawyer account is created already verified and with a complete, contactable
profile, so it shows up in the public lawyer listing immediately.
"""
import os
import sys
from datetime import datetime
from urllib.parse import urlparse

from dotenv import load_dotenv

PRODUCTION_DB_NAME = 'neondb'


def database_name(url):
    """
    The database name from a connection URL.

    Substring matching is not safe here: the production username is
    `neondb_owner`, so `'/neondb' in url` is true even for
    `postgresql://neondb_owner:...@host/rentritz_test`.
    """
    try:
        return (urlparse(url).path or '').lstrip('/').split('?')[0]
    except Exception:
        return ''

ENV_FILE = os.environ.get('ENV_FILE', '.env.test')
if not os.path.exists(ENV_FILE):
    print(f'FATAL: env file {ENV_FILE!r} not found.')
    sys.exit(1)
load_dotenv(ENV_FILE, override=True)

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app, db                                      # noqa: E402
from app.models import (                                            # noqa: E402
    CreditLog, LawyerProfile, LawyerSpecialisation, User,
)

ALLOW_PROD = '--allow-production' in sys.argv

db_url  = os.environ.get('DATABASE_URL', '')
db_name = database_name(db_url)
if db_name == PRODUCTION_DB_NAME and not ALLOW_PROD:
    print(f'REFUSING TO RUN: DATABASE_URL points at production ({db_name}).')
    print('Use ENV_FILE=.env.test, or pass --allow-production to seed live.')
    sys.exit(1)

# ── The accounts ─────────────────────────────────────────────────────────────
PASSWORD = 'RentritzAlpha!2026'

ACCOUNTS = [
    {'role': 'tenant',   'email': 'alpha.tenant@rentritz.test',
     'full_name': 'Alpha Tenant',   'credits': 25},
    {'role': 'landlord', 'email': 'alpha.landlord@rentritz.test',
     'full_name': 'Alpha Landlord', 'credits': 25},
    {'role': 'lawyer',   'email': 'alpha.lawyer@rentritz.test',
     'full_name': 'Alpha Lawyer',   'credits': 0},
    {'role': 'admin',    'email': 'alpha.admin@rentritz.test',
     'full_name': 'Alpha Admin',    'credits': 999},
]

LOGIN_URL = {
    'tenant':   '/auth/login',
    'landlord': '/auth/login',
    'lawyer':   '/lawyers/login',
    'admin':    '/manage/login',
}


def upsert_user(spec):
    user = User.query.filter_by(email=spec['email']).first()
    created = user is None
    if created:
        user = User(email=spec['email'])
        db.session.add(user)

    user.full_name   = spec['full_name']
    user.role        = spec['role']
    user.is_active   = True
    # Verification is optional for login; these are marked verified so they
    # look like settled accounts.
    user.is_verified = True
    user.credits     = spec['credits']
    user.failed_login_count   = 0
    user.failed_login_lockout = None
    user.set_password(PASSWORD)
    db.session.flush()

    if created and spec['credits']:
        db.session.add(CreditLog(
            user_id = user.id,
            action  = 'admin_grant',
            amount  = spec['credits'],
            balance = spec['credits'],
            note    = 'Seeded alpha test account',
        ))
    return user, created


def ensure_lawyer_profile(user):
    """Give the lawyer account a verified, listable profile."""
    profile = LawyerProfile.query.filter_by(user_id=user.id).first()
    created = profile is None
    if created:
        profile = LawyerProfile(user_id=user.id)
        db.session.add(profile)

    profile.display_name           = 'Alpha Lawyer'
    profile.bio                    = (
        'Alpha test profile. Tenancy, eviction and rent-increase disputes '
        'across Dubai, including RDSC filings.'
    )
    profile.years_experience       = 8
    profile.firm_name              = 'Alpha Legal Consultants'
    profile.phone                  = '+971500000001'
    profile.whatsapp               = '+971500000001'
    profile.contact_email          = 'alpha.lawyer@rentritz.test'
    profile.office_city            = 'Dubai'
    profile.office_country         = 'UAE'
    profile.languages              = ['English', 'Arabic']
    profile.consultation_modes     = ['phone', 'video', 'in_person']
    profile.hourly_rate_aed        = 500
    profile.contact_unlock_credits = 5
    profile.verification_status    = 'verified'
    profile.verified_at            = datetime.utcnow()
    profile.is_active              = True
    profile.is_available           = True

    spec = (LawyerSpecialisation.query.filter_by(slug='tenancy').first()
            or LawyerSpecialisation.query.first())
    if spec:
        profile.specialisations = [spec]

    return profile, created


def main():
    app = create_app(os.environ.get('FLASK_ENV', 'development'))
    with app.app_context():
        print(f'Env file : {ENV_FILE}')
        print(f'Database : {db_url.rsplit("@", 1)[-1] or "unknown"}')
        print('')

        results = []
        for spec in ACCOUNTS:
            user, created = upsert_user(spec)
            results.append((spec, user, created))
            if spec['role'] == 'lawyer':
                ensure_lawyer_profile(user)

        db.session.commit()

        print('=' * 74)
        print('ALPHA TEST ACCOUNTS')
        print('=' * 74)
        print(f'Password for all four accounts: {PASSWORD}')
        print('')
        print(f'{"ROLE":<10} {"EMAIL":<34} {"SIGN IN AT":<16} {"CREDITS":>7}')
        print('-' * 74)
        for spec, user, _ in results:
            print(f'{spec["role"]:<10} {user.email:<34} '
                  f'{LOGIN_URL[spec["role"]]:<16} {user.credits:>7}')
        print('-' * 74)
        for spec, user, created in results:
            print(f'  {spec["role"]:<10} {"created" if created else "updated"}'
                  f'  (user id {user.id})')
        print('')
        print('Notes:')
        print('  * Lawyers sign in at /lawyers/login, admins at /manage/login.')
        print('  * The lawyer account is pre-verified and appears in /lawyers/.')
        print('  * Unlocking the lawyer costs 5 credits from a client account.')


if __name__ == '__main__':
    main()
