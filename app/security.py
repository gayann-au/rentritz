"""
Shared brute-force lockout logic for the three login routes.

The previous behaviour locked an account after 3 wrong passwords and never
reset the counter, so the penalty escalated forever: a user who mistyped their
password a few times over the life of the account eventually sat in a
permanent one-hour lockout showing "Incorrect email or password", which is
indistinguishable from actually having the wrong password.

The alpha needs the opposite trade-off - the per-IP rate limit is the real
brute-force defence and the lockout is only a backstop against slow
distributed guessing. So:

  * 10 consecutive failures, not 3, before anything happens.
  * A flat 5-minute lockout, not an escalating 30s -> 15min -> 1h ladder.
  * The counter SELF-CLEARS once the lockout expires, so a legitimate user is
    never permanently penalised for old mistakes.
  * Any successful login clears the state completely.
"""

from datetime import datetime, timedelta

# Consecutive failures tolerated before the account is briefly locked.
FAILED_ATTEMPTS_BEFORE_LOCKOUT = 10

# How long that lockout lasts. Short on purpose: the per-IP rate limit
# (20/minute) is what actually makes online guessing impractical.
LOCKOUT_DURATION = timedelta(minutes=5)


def is_locked_out(user, now=None):
    """True if the account is inside an active lockout window."""
    if not user or not user.failed_login_lockout:
        return False
    now = now or datetime.utcnow()
    return now < user.failed_login_lockout


def clear_expired_lockout(user, now=None):
    """
    Reset the failure counter once a lockout has elapsed.

    This is what makes the lockout self-clearing: without it,
    failed_login_count stays above the threshold forever and every subsequent
    mistake re-locks the account immediately.
    """
    if not user or not user.failed_login_lockout:
        return False
    now = now or datetime.utcnow()
    if now >= user.failed_login_lockout:
        user.failed_login_count   = 0
        user.failed_login_lockout = None
        return True
    return False


def register_failed_login(user, now=None):
    """
    Record one failed attempt. Returns True if this attempt locked the account.

    The caller is responsible for committing the session.
    """
    if not user:
        return False
    now = now or datetime.utcnow()
    clear_expired_lockout(user, now)
    user.failed_login_count = (user.failed_login_count or 0) + 1
    if user.failed_login_count >= FAILED_ATTEMPTS_BEFORE_LOCKOUT:
        user.failed_login_lockout = now + LOCKOUT_DURATION
        return True
    return False


def clear_login_failures(user):
    """Wipe lockout state after a successful authentication."""
    if not user:
        return
    user.failed_login_count   = 0
    user.failed_login_lockout = None
