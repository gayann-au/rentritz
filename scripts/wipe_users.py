"""
wipe_users.py

Deletes all non-admin users and every row in every table that depends on them,
in the correct order to satisfy foreign key constraints.

USAGE:
    python scripts/wipe_users.py            # DRY RUN - shows counts only, deletes nothing
    python scripts/wipe_users.py --confirm  # ACTUALLY DELETES - irreversible

The env file defaults to .env.test, so this cannot be pointed at production by
accident:

    ENV_FILE=.env.test python scripts/wipe_users.py --confirm

Set ALLOW_PRODUCTION_WIPE=yes to override the production guard. Do not.
"""
import os
import sys
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
    print('Pass one explicitly, e.g. ENV_FILE=.env.test python scripts/wipe_users.py')
    sys.exit(1)
load_dotenv(ENV_FILE, override=True)

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app, db                                   # noqa: E402
from app.models import (                                         # noqa: E402
    User, CreditReservation, Question, Payment, CreditLog,
    LawyerProfile, LawyerBooking, LawyerReview,
)

CONFIRM = '--confirm' in sys.argv

# ── Production guard ─────────────────────────────────────────────────────────
# This script issues DELETEs. Refuse to touch the live database unless the
# operator has very deliberately opted in.
db_url  = os.environ.get('DATABASE_URL', '')
db_name = database_name(db_url)
if db_name == PRODUCTION_DB_NAME and \
        os.environ.get('ALLOW_PRODUCTION_WIPE', '').lower() != 'yes':
    print(f'REFUSING TO RUN: DATABASE_URL points at the production database ({db_name}).')
    print(f'  env file : {ENV_FILE}')
    print('  Use ENV_FILE=.env.test, or set ALLOW_PRODUCTION_WIPE=yes if you')
    print('  genuinely intend to delete every non-admin user in production.')
    sys.exit(1)

app = create_app(os.environ.get('FLASK_ENV', 'development'))

with app.app_context():
    print(f'Env file : {ENV_FILE}')
    print(f'Database : {db_url.rsplit("@", 1)[-1] or "unknown"}')
    print('')

    admin_ids = [u.id for u in User.query.filter_by(role='admin').all()]
    if not admin_ids:
        print('FATAL: no admin user found (role == "admin"). Aborting.')
        sys.exit(1)

    print(f'Admin user id(s) to KEEP: {admin_ids}')

    non_admin_ids = [u.id for u in User.query.filter(User.id.notin_(admin_ids)).all()]
    print(f'Non-admin users to DELETE: {len(non_admin_ids)}')

    if not non_admin_ids:
        print('Nothing to delete. Exiting.')
        sys.exit(0)

    # NOTE: LawyerBooking's foreign key to users is `client_id`, not `user_id`.
    # Every reference below used to say `user_id`, so this script raised
    # AttributeError on the first count and could never run at all.
    counts = {
        'LawyerReview': LawyerReview.query.join(
            LawyerBooking, LawyerReview.booking_id == LawyerBooking.id
        ).filter(LawyerBooking.client_id.in_(non_admin_ids)).count(),

        'LawyerBooking': LawyerBooking.query.filter(
            LawyerBooking.client_id.in_(non_admin_ids)
        ).count(),

        'LawyerProfile': LawyerProfile.query.filter(
            LawyerProfile.user_id.in_(non_admin_ids)
        ).count(),

        'Payment': Payment.query.filter(
            Payment.user_id.in_(non_admin_ids)
        ).count(),

        'CreditLog': CreditLog.query.filter(
            CreditLog.user_id.in_(non_admin_ids)
        ).count(),

        'CreditReservation': CreditReservation.query.filter(
            CreditReservation.user_id.in_(non_admin_ids)
        ).count(),

        'Question': Question.query.filter(
            Question.user_id.in_(non_admin_ids)
        ).count(),

        'User': len(non_admin_ids),
    }

    print('')
    print('Rows that will be deleted:')
    for table, n in counts.items():
        print(f'  {table:20s} {n}')

    if not CONFIRM:
        print('')
        print('DRY RUN ONLY - nothing was deleted.')
        print('Review the counts above. If correct, re-run with --confirm.')
        sys.exit(0)

    print('')
    print('--confirm passed. Deleting now...')
    try:
        LawyerReview.query.filter(
            LawyerReview.booking_id.in_(
                db.session.query(LawyerBooking.id).filter(
                    LawyerBooking.client_id.in_(non_admin_ids)
                )
            )
        ).delete(synchronize_session=False)

        LawyerBooking.query.filter(
            LawyerBooking.client_id.in_(non_admin_ids)
        ).delete(synchronize_session=False)

        LawyerProfile.query.filter(
            LawyerProfile.user_id.in_(non_admin_ids)
        ).delete(synchronize_session=False)

        Payment.query.filter(
            Payment.user_id.in_(non_admin_ids)
        ).delete(synchronize_session=False)

        CreditLog.query.filter(
            CreditLog.user_id.in_(non_admin_ids)
        ).delete(synchronize_session=False)

        CreditReservation.query.filter(
            CreditReservation.user_id.in_(non_admin_ids)
        ).delete(synchronize_session=False)

        Question.query.filter(
            Question.user_id.in_(non_admin_ids)
        ).delete(synchronize_session=False)

        User.query.filter(
            User.id.in_(non_admin_ids)
        ).delete(synchronize_session=False)

        db.session.commit()
        print('Done. All non-admin users and their dependent data have been deleted.')
    except Exception as e:
        db.session.rollback()
        print(f'ERROR - rolled back, nothing was deleted. Details: {e}')
        sys.exit(1)
