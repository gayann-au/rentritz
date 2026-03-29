from datetime import datetime
from flask import Blueprint, render_template, redirect, url_for, flash, request, current_app
from flask_login import login_user, logout_user, login_required, current_user
from app.models import db, User, CreditLog, VALID_ROLES

auth_bp = Blueprint('auth', __name__)


@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('core.dashboard'))

    if request.method == 'POST':
        full_name = request.form.get('full_name', '').strip()
        email     = request.form.get('email', '').strip().lower()
        password  = request.form.get('password', '')
        role      = request.form.get('role', '').strip().lower()

        if not full_name or not email or not password or not role:
            flash('All fields are required.', 'error')
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


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('core.dashboard'))

    if request.method == 'POST':
        email    = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        remember = bool(request.form.get('remember'))

        user = User.query.filter_by(email=email).first()

        if not user or not user.check_password(password):
            flash('Incorrect email or password.', 'error')
            return render_template('auth/login.html')

        if user.role == 'admin':
            flash('Incorrect email or password.', 'error')
            return render_template('auth/login.html')

        if not user.is_active:
            flash('Your account has been deactivated. Please contact support.', 'error')
            return render_template('auth/login.html')

        user.last_login = datetime.utcnow()
        db.session.commit()
        login_user(user, remember=remember)

        next_page = request.args.get('next')
        return redirect(next_page or url_for('core.dashboard'))

    return render_template('auth/login.html')


@auth_bp.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('auth.login'))