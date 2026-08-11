import re
import secrets
from datetime import datetime, timedelta

from flask import (
    Blueprint, current_app, flash, redirect, render_template, request, url_for,
)
from flask_login import current_user, login_required, login_user, logout_user

from app import limiter
from app.emailer import send_async
from app.models import CreditLog, User, VALID_ROLES, db
from app.security import (
    clear_expired_lockout, clear_login_failures, is_locked_out,
    register_failed_login,
)

auth_bp = Blueprint('auth', __name__)

_EMAIL_RE  = re.compile(r'^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$')
_SCRIPT_RE = re.compile(r'<\s*script', re.IGNORECASE)
# Control characters and angle brackets are the only things rejected in a name.
# The old filter also blocked apostrophes, semicolons and the words "or"/"and",
# which locked out every O'Brien and D'Souza for no security gain - SQLAlchemy
# parameterises every query and Jinja escapes every template value.
_UNSAFE_NAME_RE = re.compile(r'[<>\x00-\x1f\x7f]')

MAX_EMAIL    = 254
MAX_PASSWORD = 128
MAX_NAME     = 100


def _valid_email(email):
    return bool(email) and len(email) <= MAX_EMAIL and bool(_EMAIL_RE.match(email))


def _valid_name(name):
    return not (_SCRIPT_RE.search(name) or _UNSAFE_NAME_RE.search(name))


def _safe_next(target):
    """Only allow same-site relative redirects."""
    if not target or not target.startswith('/') or target.startswith('//'):
        return None
    return target


def _home_for(user):
    if user.role == 'lawyer':
        return url_for('lawyers.dashboard')
    if user.role == 'admin':
        return url_for('admin.dashboard')
    return url_for('core.dashboard')


def _issue_verification_token(user, hours=24):
    token = secrets.token_urlsafe(32)
    user.reset_token        = token
    user.reset_token_expiry = datetime.utcnow() + timedelta(hours=hours)
    return token


def _send_verification_email(user, token):
    """Queue the (optional) verification email. Never blocks the request."""
    verify_url = url_for('auth.verify_email', token=token, _external=True)
    send_async(
        subject='Verify your Rentritz email address',
        recipients=[user.email],
        html=render_template('email/verify_email.html',
                             user=user, verify_url=verify_url),
    )


# ─────────────────────────────────────────────────────────────────────────────
# Register
# ─────────────────────────────────────────────────────────────────────────────

@auth_bp.route('/register', methods=['GET', 'POST'])
@limiter.limit("10 per minute; 50 per hour", methods=["POST"])
def register():
    if current_user.is_authenticated:
        return redirect(_home_for(current_user))

    if request.method == 'POST':
        full_name = request.form.get('full_name', '').strip()
        email     = request.form.get('email', '').strip().lower()
        password  = request.form.get('password', '')
        role      = request.form.get('role', '').strip().lower()

        if not full_name or not email or not password or not role:
            flash('All fields are required.', 'error')
            return render_template('auth/register.html')

        if len(full_name) > MAX_NAME:
            flash('Name must be 100 characters or fewer.', 'error')
            return render_template('auth/register.html')

        if len(email) > MAX_EMAIL:
            flash('Email address is too long.', 'error')
            return render_template('auth/register.html')

        if len(password) > MAX_PASSWORD:
            flash('Password must be 128 characters or fewer.', 'error')
            return render_template('auth/register.html')

        if not _valid_email(email):
            flash('Please enter a valid email address.', 'error')
            return render_template('auth/register.html')

        if not _valid_name(full_name):
            flash('Name contains invalid characters.', 'error')
            return render_template('auth/register.html')

        if role not in VALID_ROLES:
            flash('Please select a valid role.', 'error')
            return render_template('auth/register.html')

        if len(password) < 8:
            flash('Password must be at least 8 characters.', 'error')
            return render_template('auth/register.html')

        if User.query.filter_by(email=email).first():
            flash('An account with this email already exists.', 'error')
            return render_template('auth/register.html')

        free_credits = current_app.config['FREE_CREDITS_ON_SIGNUP']

        user = User(
            full_name   = full_name,
            email       = email,
            role        = role,
            is_active   = True,
            is_verified = False,
            credits     = free_credits,
        )
        user.set_password(password)
        db.session.add(user)
        db.session.flush()

        db.session.add(CreditLog(
            user_id = user.id,
            action  = 'signup_bonus',
            amount  = free_credits,
            balance = free_credits,
            note    = f'{free_credits} free credits on registration',
        ))

        token = _issue_verification_token(user)
        db.session.commit()
        current_app.logger.info('registered user id=%s role=%s', user.id, user.role)

        # Verification is optional - the account is usable immediately. The
        # email is queued on a background thread so a slow SMTP server cannot
        # hold the response (or a Waitress worker) open.
        _send_verification_email(user, token)

        # Lawyers authenticate through the lawyer portal. Sending them to
        # /auth/login would dead-end with "this login is for clients only".
        if user.role == 'lawyer':
            flash('Account created. Sign in to set up your lawyer profile.', 'success')
            return redirect(url_for('lawyers.login'))

        flash(f'Welcome, {user.full_name}! Your account is ready - sign in below.',
              'success')
        return redirect(url_for('auth.login'))

    return render_template('auth/register.html')


# ─────────────────────────────────────────────────────────────────────────────
# Login
# ─────────────────────────────────────────────────────────────────────────────

@auth_bp.route('/login', methods=['GET', 'POST'])
@limiter.limit("20 per minute; 200 per hour", methods=["POST"])
def login():
    if current_user.is_authenticated:
        return redirect(_home_for(current_user))

    if request.method == 'POST':
        email    = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        remember = bool(request.form.get('remember'))

        if not _valid_email(email) or len(password) > MAX_PASSWORD:
            flash('Incorrect email or password.', 'error')
            return render_template('auth/login.html')

        user = User.query.filter_by(email=email).first()

        # Role separation: lawyers and admins have their own entrances.
        if user and user.role == 'lawyer':
            flash('Lawyers sign in through the lawyer portal.', 'info')
            return redirect(url_for('lawyers.login'))

        if user and user.role != 'admin':
            clear_expired_lockout(user)
            if is_locked_out(user):
                db.session.commit()
                flash('Too many failed attempts. Try again in a few minutes.', 'error')
                return render_template('auth/login.html')

        if not user or not user.check_password(password):
            if user and user.role != 'admin':
                if register_failed_login(user):
                    current_app.logger.warning(
                        'account locked after repeated failures user_id=%s', user.id
                    )
                db.session.commit()
            flash('Incorrect email or password.', 'error')
            return render_template('auth/login.html')

        if user.role == 'admin':
            flash('Incorrect email or password.', 'error')
            return render_template('auth/login.html')

        if not user.is_active:
            flash('Your account has been deactivated. Please contact support.', 'error')
            return render_template('auth/login.html')

        # NOTE: email verification is intentionally NOT required to sign in.
        # The verify link remains available but is optional.

        clear_login_failures(user)
        user.last_login = datetime.utcnow()
        db.session.commit()

        if not login_user(user, remember=remember):
            # Flask-Login returns False when it refuses the user (e.g. a NULL
            # is_active). This used to be discarded, so the request redirected
            # to a page that bounced straight back to /login with no error.
            current_app.logger.error(
                'login_user() refused user_id=%s email=%s is_active=%r',
                user.id, user.email, user.is_active,
            )
            flash('We could not sign you in. Please contact support.', 'error')
            return render_template('auth/login.html')

        current_app.logger.info('login ok user_id=%s role=%s', user.id, user.role)

        next_page = _safe_next(request.args.get('next'))
        if next_page:
            return redirect(next_page)
        return redirect(_home_for(user))

    return render_template('auth/login.html')


@auth_bp.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('auth.login'))


# ─────────────────────────────────────────────────────────────────────────────
# Password reset
# ─────────────────────────────────────────────────────────────────────────────

@auth_bp.route('/forgot-password', methods=['GET', 'POST'])
@limiter.limit("10 per minute; 30 per hour", methods=["POST"])
def forgot_password():
    if current_user.is_authenticated:
        return redirect(_home_for(current_user))

    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()

        if _valid_email(email):
            user = User.query.filter_by(email=email).first()
            # Same response either way, to avoid confirming which emails exist.
            if user and user.role != 'admin':
                token = secrets.token_urlsafe(32)
                user.reset_token        = token
                user.reset_token_expiry = datetime.utcnow() + timedelta(hours=1)
                db.session.commit()

                reset_url = url_for('auth.reset_password', token=token, _external=True)
                send_async(
                    subject='Reset your Rentritz password',
                    recipients=[user.email],
                    html=render_template('email/reset_password.html',
                                         user=user, reset_url=reset_url),
                )

        flash('If that email is registered you will receive a reset link shortly.',
              'success')
        return redirect(url_for('auth.forgot_password'))

    return render_template('auth/forgot_password.html')


@auth_bp.route('/reset-password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    if current_user.is_authenticated:
        return redirect(_home_for(current_user))

    user = User.query.filter_by(reset_token=token).first()

    if not user or not user.reset_token_expiry or user.reset_token_expiry < datetime.utcnow():
        flash('This reset link is invalid or has expired. Please request a new one.',
              'error')
        return redirect(url_for('auth.forgot_password'))

    if request.method == 'POST':
        password = request.form.get('password', '')
        confirm  = request.form.get('confirm_password', '')

        if len(password) < 8:
            flash('Password must be at least 8 characters.', 'error')
            return render_template('auth/reset_password.html', token=token)

        if len(password) > MAX_PASSWORD:
            flash('Password must be 128 characters or fewer.', 'error')
            return render_template('auth/reset_password.html', token=token)

        if password != confirm:
            flash('Passwords do not match.', 'error')
            return render_template('auth/reset_password.html', token=token)

        user.set_password(password)
        user.reset_token        = None
        user.reset_token_expiry = None
        user.last_login         = datetime.utcnow()
        clear_login_failures(user)
        db.session.commit()

        if not login_user(user):
            current_app.logger.error(
                'login_user() refused after password reset user_id=%s is_active=%r',
                user.id, user.is_active,
            )
            flash('Password updated. Please sign in.', 'success')
            return redirect(url_for('auth.login'))

        flash('Your password has been reset. Welcome back!', 'success')
        return redirect(_home_for(user))

    return render_template('auth/reset_password.html', token=token)


# ─────────────────────────────────────────────────────────────────────────────
# Email verification (optional)
# ─────────────────────────────────────────────────────────────────────────────

@auth_bp.route('/resend-verification', methods=['POST'])
@limiter.limit("10 per hour")
def resend_verification():
    email = request.form.get('email', '').strip().lower()

    if _valid_email(email):
        user = User.query.filter_by(email=email).first()
        if user and not user.is_verified and user.role != 'admin':
            token = _issue_verification_token(user)
            db.session.commit()
            _send_verification_email(user, token)

    flash('If that email is registered and unverified, you will receive a '
          'verification link shortly.', 'success')
    return redirect(url_for('auth.login'))


@auth_bp.route('/verify-email/<token>')
def verify_email(token):
    user = User.query.filter_by(reset_token=token).first()

    if not user or not user.reset_token_expiry or user.reset_token_expiry < datetime.utcnow():
        flash('This verification link is invalid or has expired. Request a new one below.',
              'error')
        return redirect(url_for('auth.login'))

    user.is_verified        = True
    user.reset_token        = None
    user.reset_token_expiry = None
    db.session.commit()

    # Already signed in (verification is optional, so this is the common case).
    if current_user.is_authenticated:
        flash('Your email has been verified.', 'success')
        return redirect(_home_for(current_user))

    if not login_user(user):
        current_app.logger.error(
            'login_user() refused after email verification user_id=%s is_active=%r',
            user.id, user.is_active,
        )
        flash('Your email has been verified. Please sign in.', 'success')
        return redirect(url_for('auth.login'))

    flash(f'Your email has been verified. Welcome to Rentritz, {user.full_name}!',
          'success')
    return redirect(_home_for(user))
