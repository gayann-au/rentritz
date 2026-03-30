import re
import secrets
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


def _valid_email(email):
    return bool(email) and len(email) <= MAX_EMAIL and _EMAIL_RE.match(email)


@auth_bp.route('/register', methods=['GET', 'POST'])
@limiter.limit("3 per minute; 10 per hour", methods=["POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('core.dashboard'))

    if request.method == 'POST':
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
            flash('Please select a valid role: tenant or landlord.', 'error')
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
            is_verified=True,
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
        db.session.commit()

        login_user(user)
        flash(f'Welcome, {user.full_name}. You have {free_credits} free consultations to get started.', 'success')
        return redirect(url_for('core.dashboard'))

    return render_template('auth/register.html')


_LOCKOUT_DURATION = timedelta(minutes=15)
_MAX_FAILED       = 5


@auth_bp.route('/login', methods=['GET', 'POST'])
@limiter.limit("5 per minute; 20 per hour", methods=["POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('core.dashboard'))

    if request.method == 'POST':
        email    = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        remember = bool(request.form.get('remember'))

        # Validate format before touching the database
        if not _valid_email(email) or len(password) > MAX_PASSWORD:
            flash('Incorrect email or password.', 'error')
            return render_template('auth/login.html')

        user = User.query.filter_by(email=email).first()

        # Check lockout (do this even if user not found to avoid timing leaks)
        if user and user.role != 'admin':
            now = datetime.utcnow()
            if user.failed_login_lockout:
                if now - user.failed_login_lockout < _LOCKOUT_DURATION:
                    flash('Incorrect email or password.', 'error')
                    return render_template('auth/login.html')
                # Lockout expired - reset
                user.failed_login_count   = 0
                user.failed_login_lockout = None
                db.session.commit()

        if not user or not user.check_password(password):
            # Increment failure counter only for real (non-admin) accounts
            if user and user.role != 'admin':
                user.failed_login_count += 1
                if user.failed_login_count >= _MAX_FAILED:
                    user.failed_login_lockout = datetime.utcnow()
                    user.failed_login_count   = 0
                db.session.commit()
            flash('Incorrect email or password.', 'error')
            return render_template('auth/login.html')

        if user.role == 'admin':
            flash('Incorrect email or password.', 'error')
            return render_template('auth/login.html')

        if not user.is_active:
            flash('Your account has been deactivated. Please contact support.', 'error')
            return render_template('auth/login.html')

        # Successful login - clear brute force state
        user.failed_login_count   = 0
        user.failed_login_lockout = None
        user.last_login           = datetime.utcnow()
        db.session.commit()
        login_user(user, remember=remember)

        next_page = request.args.get('next')
        if next_page:
            parsed = urlparse(next_page)
            if parsed.netloc or parsed.scheme or next_page.startswith('//'):
                next_page = None
        return redirect(next_page or url_for('core.dashboard'))

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
        return redirect(url_for('core.dashboard'))

    return render_template('auth/reset_password.html', token=token)