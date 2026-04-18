import re
import secrets
import requests as _http
from datetime import datetime, timedelta
from urllib.parse import urlparse
from flask import Blueprint, render_template, redirect, url_for, flash, request, current_app
from flask_login import login_user, logout_user, login_required, current_user
from flask_mail import Message
from app import mail, limiter
from app.models import db, User, CreditLog, VALID_ROLES

auth_bp = Blueprint('auth', __name__)

_EMAIL_RE    = re.compile(r'^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$')
_SCRIPT_RE   = re.compile(r'<\s*script', re.IGNORECASE)
_SQLI_RE     = re.compile(r"['\";]|--|\bOR\b|\bAND\b|\bDROP\b|\bSELECT\b|\bINSERT\b|\bUNION\b",
                           re.IGNORECASE)

MAX_EMAIL    = 254
MAX_PASSWORD = 128
MAX_NAME     = 100

# ── Progressive login lockout thresholds ─────────────────────────────────────
# failed_login_lockout stores the "locked UNTIL" timestamp (not "locked AT").
# failed_login_count is cumulative and never reset by an expiring lockout,
# so penalties escalate across repeated attack sessions.
_COOLDOWN_THRESHOLD = 3          # ≥3 wrong: 30-second cooldown
_LOCKOUT_THRESHOLD  = 5          # ≥5 wrong: 15-minute lockout
_EXTENDED_THRESHOLD = 10         # ≥10 wrong: 1-hour lockout
_COOLDOWN_DURATION  = timedelta(seconds=30)
_LOCKOUT_DURATION   = timedelta(minutes=15)
_EXTENDED_DURATION  = timedelta(hours=1)


def _valid_email(email):
    return bool(email) and len(email) <= MAX_EMAIL and _EMAIL_RE.match(email)


def _verify_hcaptcha():
    """Return True if hCaptcha passes, or if hCaptcha is not configured, or on localhost."""
    secret = current_app.config.get('HCAPTCHA_SECRET_KEY', '')
    if not secret:
        return True  # no captcha configured
    host = request.host.split(':')[0]
    if host in ('localhost', '127.0.0.1'):
        return True  # hCaptcha does not validate localhost - skip in local dev
    token = request.form.get('h-captcha-response', '')
    if not token:
        return False
    try:
        resp = _http.post(
            'https://hcaptcha.com/siteverify',
            data={'secret': secret, 'response': token},
            timeout=5,
        )
        return resp.json().get('success', False)
    except Exception:
        return False


@auth_bp.route('/register', methods=['GET', 'POST'])
@limiter.limit("3 per minute; 10 per hour", methods=["POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('core.dashboard'))

    if request.method == 'POST':
        if not _verify_hcaptcha():
            flash('Security check failed. Please try again.', 'error')
            return render_template('auth/register.html')

        full_name = request.form.get('full_name', '').strip()
        email     = request.form.get('email', '').strip().lower()
        password  = request.form.get('password', '')
        role      = request.form.get('role', '').strip().lower()

        # Presence check
        if not full_name or not email or not password or not role:
            flash('All fields are required.', 'error')
            return render_template('auth/register.html')

        # Length limits
        if len(full_name) > MAX_NAME:
            flash('Name must be 100 characters or fewer.', 'error')
            return render_template('auth/register.html')

        if len(email) > MAX_EMAIL:
            flash('Email address is too long.', 'error')
            return render_template('auth/register.html')

        if len(password) > MAX_PASSWORD:
            flash('Password must be 128 characters or fewer.', 'error')
            return render_template('auth/register.html')

        # Email format
        if not _valid_email(email):
            flash('Please enter a valid email address.', 'error')
            return render_template('auth/register.html')

        # Name injection checks
        if _SCRIPT_RE.search(full_name):
            flash('Name contains invalid characters.', 'error')
            return render_template('auth/register.html')

        if _SQLI_RE.search(full_name):
            flash('Name contains invalid characters.', 'error')
            return render_template('auth/register.html')

        # Role - exact match only
        if role not in VALID_ROLES:
            flash('Please select a valid role.', 'error')
            return render_template('auth/register.html')

        # Password length
        if len(password) < 8:
            flash('Password must be at least 8 characters.', 'error')
            return render_template('auth/register.html')

        if User.query.filter_by(email=email).first():
            flash('An account with this email already exists.', 'error')
            return render_template('auth/register.html')

        free_credits = current_app.config['FREE_CREDITS_ON_SIGNUP']

        user = User(
            full_name=full_name,
            email=email,
            role=role,
            is_verified=False,
            credits=free_credits,
        )
        user.set_password(password)
        db.session.add(user)
        db.session.flush()

        log = CreditLog(
            user_id=user.id,
            action='signup_bonus',
            amount=free_credits,
            balance=free_credits,
            note=f'{free_credits} free credits on registration',
        )
        db.session.add(log)

        # Generate email verification token
        token = secrets.token_urlsafe(32)
        user.reset_token        = token
        user.reset_token_expiry = datetime.utcnow() + timedelta(hours=24)
        db.session.commit()

        verify_url = url_for('auth.verify_email', token=token, _external=True)
        try:
            msg = Message(
                subject='Verify your Rentritz email address',
                recipients=[user.email],
                html=render_template('email/verify_email.html',
                                     user=user, verify_url=verify_url),
            )
            mail.send(msg)
        except Exception as e:
            current_app.logger.error(f'Failed to send verification email to {user.email}: {e}')

        flash(f'Welcome, {user.full_name}! Check your email to verify your account before logging in.', 'success')
        return redirect(url_for('auth.login'))

    return render_template('auth/register.html')


@auth_bp.route('/login', methods=['GET', 'POST'])
@limiter.limit("5 per minute; 20 per hour", methods=["POST"])
def login():
    if current_user.is_authenticated:
        if current_user.role == 'lawyer':
            return redirect(url_for('lawyers.dashboard'))
        return redirect(url_for('core.dashboard'))

    if request.method == 'POST':
        email    = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        remember = bool(request.form.get('remember'))

        # Validate format before touching the database
        if not _valid_email(email) or len(password) > MAX_PASSWORD:
            flash('Incorrect email or password.', 'error')
            return render_template('auth/login.html')

        if not _verify_hcaptcha():
            flash('Security check failed. Please try again.', 'error')
            return render_template('auth/login.html')

        user = User.query.filter_by(email=email).first()

        if user and user.role == 'lawyer':
            flash('This login is for clients only. Lawyers use the lawyer portal.', 'error')
            return render_template('auth/login.html')

        # Check lockout - failed_login_lockout is the "locked until" timestamp
        if user and user.role != 'admin':
            now = datetime.utcnow()
            if user.failed_login_lockout and now < user.failed_login_lockout:
                flash('Incorrect email or password.', 'error')
                return render_template('auth/login.html')

        if not user or not user.check_password(password):
            # Increment cumulative failure counter (never auto-reset on expiry)
            if user and user.role != 'admin':
                user.failed_login_count += 1
                count = user.failed_login_count
                now   = datetime.utcnow()
                if count >= _EXTENDED_THRESHOLD:
                    user.failed_login_lockout = now + _EXTENDED_DURATION
                elif count >= _LOCKOUT_THRESHOLD:
                    user.failed_login_lockout = now + _LOCKOUT_DURATION
                elif count >= _COOLDOWN_THRESHOLD:
                    user.failed_login_lockout = now + _COOLDOWN_DURATION
                db.session.commit()
            flash('Incorrect email or password.', 'error')
            return render_template('auth/login.html')

        if user.role == 'admin':
            flash('Incorrect email or password.', 'error')
            return render_template('auth/login.html')

        if not user.is_active:
            flash('Your account has been deactivated. Please contact support.', 'error')
            return render_template('auth/login.html')

        if not user.is_verified:
            flash('Please verify your email before logging in. Check your inbox for the verification link.', 'error')
            return render_template('auth/login.html', unverified_email=email)

        # Successful login - clear brute force state
        user.failed_login_count   = 0
        user.failed_login_lockout = None
        user.last_login           = datetime.utcnow()
        db.session.commit()
        login_user(user, remember=remember)

        next_page = request.args.get('next')
        if next_page and (not next_page.startswith('/') or next_page.startswith('//')):
            next_page = None
        if next_page:
            return redirect(next_page)
        if user.role == 'lawyer':
            response = redirect(url_for('lawyers.dashboard'), 303)
            response.headers['Cache-Control'] = 'no-store'
            return response
        return redirect(url_for('core.dashboard'))

    return render_template('auth/login.html')


@auth_bp.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('auth.login'))


@auth_bp.route('/forgot-password', methods=['GET', 'POST'])
@limiter.limit("3 per minute; 5 per hour", methods=["POST"])
def forgot_password():
    if current_user.is_authenticated:
        return redirect(url_for('core.dashboard'))

    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()

        # Validate format before any database query
        if not _valid_email(email):
            flash('If that email is registered you will receive a reset link shortly.', 'success')
            return redirect(url_for('auth.forgot_password'))

        user = User.query.filter_by(email=email).first()

        # Always show the same message to prevent email enumeration
        if user and user.role != 'admin':
            token = secrets.token_urlsafe(32)
            user.reset_token        = token
            user.reset_token_expiry = datetime.utcnow() + timedelta(hours=1)
            db.session.commit()

            reset_url = url_for('auth.reset_password', token=token, _external=True)
            msg = Message(
                subject='Reset your Rentritz password',
                recipients=[user.email],
                html=render_template('email/reset_password.html',
                                     user=user, reset_url=reset_url),
            )
            try:
                mail.send(msg)
            except Exception as e:
                current_app.logger.error(f'Failed to send reset email to {email}: {e}')

        flash('If that email is registered you will receive a reset link shortly.', 'success')
        return redirect(url_for('auth.forgot_password'))

    return render_template('auth/forgot_password.html')


@auth_bp.route('/reset-password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    if current_user.is_authenticated:
        return redirect(url_for('core.dashboard'))

    user = User.query.filter_by(reset_token=token).first()

    if not user or not user.reset_token_expiry or user.reset_token_expiry < datetime.utcnow():
        flash('This reset link is invalid or has expired. Please request a new one.', 'error')
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
        db.session.commit()

        login_user(user)
        flash('Your password has been reset. Welcome back!', 'success')
        if user.role == 'lawyer':
            return redirect(url_for('lawyers.dashboard'))
        return redirect(url_for('core.dashboard'))

    return render_template('auth/reset_password.html', token=token)


@auth_bp.route('/resend-verification', methods=['POST'])
@limiter.limit("3 per hour")
def resend_verification():
    email = request.form.get('email', '').strip().lower()

    if _valid_email(email):
        user = User.query.filter_by(email=email).first()
        if user and not user.is_verified and user.role != 'admin':
            token = secrets.token_urlsafe(32)
            user.reset_token        = token
            user.reset_token_expiry = datetime.utcnow() + timedelta(hours=24)
            db.session.commit()

            verify_url = url_for('auth.verify_email', token=token, _external=True)
            msg = Message(
                subject='Verify your Rentritz email address',
                recipients=[user.email],
                html=render_template('email/verify_email.html',
                                     user=user, verify_url=verify_url),
            )
            try:
                mail.send(msg)
            except Exception as e:
                current_app.logger.error(f'Failed to send verification email to {email}: {e}')

    flash('If that email is registered and unverified, you will receive a verification link shortly.', 'success')
    return redirect(url_for('auth.login'))


@auth_bp.route('/verify-email/<token>')
def verify_email(token):
    if current_user.is_authenticated:
        return redirect(url_for('core.dashboard'))

    user = User.query.filter_by(reset_token=token).first()

    if not user or not user.reset_token_expiry or user.reset_token_expiry < datetime.utcnow():
        flash('This verification link is invalid or has expired. Request a new one below.', 'error')
        return redirect(url_for('auth.login'))

    user.is_verified        = True
    user.reset_token        = None
    user.reset_token_expiry = None
    db.session.commit()

    login_user(user)
    flash(f'Your email has been verified. Welcome to Rentritz, {user.full_name}!', 'success')
    return redirect(url_for('core.dashboard'))