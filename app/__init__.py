import os
import uuid
import logging
from flask import Flask, abort, render_template, g, request
from flask_login import LoginManager, current_user
from flask_mail import Mail
from flask_wtf.csrf import CSRFProtect
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from app.models import db, User
from config.settings import config

login_manager = LoginManager()
mail          = Mail()
csrf          = CSRFProtect()
limiter       = Limiter(
    key_func=get_remote_address,
    default_limits=["200 per day", "100 per hour"],
    storage_uri="memory://",
)
logger        = logging.getLogger(__name__)


def create_app(env=None):
    env = env or os.environ.get('FLASK_ENV', 'production')
    app = Flask(__name__,
        template_folder = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'templates'),
        static_folder   = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'static'))
    app.config.from_object(config.get(env, config['production']))
    app.config['TEMPLATES_AUTO_RELOAD'] = (env == 'development')

    db.init_app(app)
    login_manager.init_app(app)
    mail.init_app(app)
    csrf.init_app(app)
    limiter.init_app(app)

    login_manager.login_view    = 'auth.login'
    login_manager.login_message = 'Please sign in to continue.'

    @login_manager.user_loader
    def load_user(user_id):
        return db.session.get(User, int(user_id))

    @app.before_request
    def assign_request_id():
        g.request_id = uuid.uuid4().hex

    @app.after_request
    def set_security_headers(response):
        response.headers['X-Content-Type-Options']  = 'nosniff'
        response.headers['X-Frame-Options']         = 'DENY'
        response.headers['X-XSS-Protection']        = '1; mode=block'
        response.headers['Referrer-Policy']         = 'strict-origin-when-cross-origin'
        response.headers['Permissions-Policy']      = 'geolocation=(), microphone=(), camera=()'
        response.headers['Content-Security-Policy'] = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' fonts.googleapis.com; "
            "style-src 'self' 'unsafe-inline' fonts.googleapis.com fonts.gstatic.com; "
            "font-src fonts.gstatic.com; "
            "img-src 'self' images.unsplash.com data:; "
            "connect-src 'self'"
        )
        if not app.config.get('DEBUG'):
            response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
        response.headers.remove('Server')
        response.headers.remove('X-Powered-By')

        # Log all 4xx and 5xx responses
        status = response.status_code
        if status >= 400:
            uid = current_user.id if current_user.is_authenticated else None
            logger.warning(
                'HTTP %s  ip=%s  route=%s  user_id=%s  request_id=%s',
                status, request.remote_addr, request.path, uid,
                getattr(g, 'request_id', '-'),
            )

        return response

    @app.route('/admin')
    @app.route('/admin/')
    def block_admin():
        abort(404)

    from app.auth.routes     import auth_bp
    from app.core.routes     import core_bp
    from app.payments.routes import payments_bp
    from app.api.routes      import api_bp
    from app.admin.routes    import admin_bp

    app.register_blueprint(auth_bp,     url_prefix='/auth')
    app.register_blueprint(core_bp,     url_prefix='/')
    app.register_blueprint(payments_bp, url_prefix='/pay')
    app.register_blueprint(api_bp,      url_prefix='/api/v1')
    app.register_blueprint(admin_bp,    url_prefix='/manage')

    @app.errorhandler(400)
    def bad_request(e):
        return render_template('errors/400.html'), 400

    @app.errorhandler(401)
    def unauthorized(e):
        return render_template('errors/401.html'), 401

    @app.errorhandler(403)
    def forbidden(e):
        return render_template('errors/403.html'), 403

    @app.errorhandler(404)
    def not_found(e):
        return render_template('errors/404.html'), 404

    @app.errorhandler(429)
    def too_many_requests(e):
        return render_template('errors/429.html'), 429

    @app.errorhandler(500)
    def server_error(e):
        logger.error(
            'HTTP 500  ip=%s  route=%s  user_id=%s  request_id=%s  error=%s',
            request.remote_addr, request.path,
            current_user.id if current_user.is_authenticated else None,
            getattr(g, 'request_id', '-'), e,
        )
        return render_template('errors/500.html'), 500

    with app.app_context():
        db.create_all()
        _migrate_schema()
        _seed_initial_data()

    return app


def _migrate_schema():
    """Add any new columns to existing tables that db.create_all() won't add."""
    from sqlalchemy import text
    stmts = [
        'ALTER TABLE questions ADD COLUMN IF NOT EXISTS answer_viewed BOOLEAN NOT NULL DEFAULT FALSE',
        'ALTER TABLE questions ADD COLUMN IF NOT EXISTS has_been_viewed BOOLEAN NOT NULL DEFAULT FALSE',
        'ALTER TABLE users ADD COLUMN IF NOT EXISTS reset_token VARCHAR(100)',
        'ALTER TABLE users ADD COLUMN IF NOT EXISTS reset_token_expiry TIMESTAMP',
        'ALTER TABLE users ADD COLUMN IF NOT EXISTS failed_login_count INTEGER NOT NULL DEFAULT 0',
        'ALTER TABLE users ADD COLUMN IF NOT EXISTS failed_login_lockout TIMESTAMP',
        'ALTER TABLE users ADD COLUMN IF NOT EXISTS has_seen_onboarding BOOLEAN NOT NULL DEFAULT FALSE',
    ]
    for stmt in stmts:
        try:
            db.session.execute(text(stmt))
            db.session.commit()
        except Exception:
            db.session.rollback()


def _seed_initial_data():
    from app.models import Category, User

    admin_email    = os.environ.get('ADMIN_EMAIL', '')
    admin_password = os.environ.get('ADMIN_PASSWORD', '')
    if not admin_email or not admin_password:
        import sys
        print('FATAL: ADMIN_EMAIL and ADMIN_PASSWORD must be set in .env')
        sys.exit(1)

    if not User.query.filter_by(email=admin_email).first():
        admin = User(
            full_name   = 'Admin',
            email       = admin_email,
            role        = 'admin',
            is_verified = True,
            credits     = 999,
        )
        admin.set_password(admin_password)
        db.session.add(admin)
        logger.info('Admin user created')

    if Category.query.count() == 0:
        cats = [
            Category(slug='rent_increase',   title='Rent Increase',         description='Your landlord wants to raise your rent',      icon='trending-up',    for_role='tenant',   order=1),
            Category(slug='eviction',        title='Eviction Notice',       description='You have been asked to vacate the property',   icon='home',           for_role='tenant',   order=2),
            Category(slug='maintenance',     title='Maintenance & Repairs',  description='Repair responsibilities and disputes',         icon='tool',           for_role='both',     order=3),
            Category(slug='deposit',         title='Security Deposit',      description='Deposit not returned or wrongly deducted',     icon='shield',         for_role='tenant',   order=4),
            Category(slug='dispute',         title='Filing a Dispute',      description='Taking a case to RDSC',                       icon='file-text',      for_role='both',     order=5),
            Category(slug='landlord_rights', title='Landlord Rights',       description='Eviction grounds and legal procedures',        icon='briefcase',      for_role='landlord', order=6),
        ]
        db.session.add_all(cats)
        logger.info('Categories seeded')

    db.session.commit()