import os
import uuid
import logging
from logging.handlers import RotatingFileHandler
from flask import Flask, abort, render_template, g, request
from flask_login import LoginManager, current_user
from flask_mail import Mail
from flask_wtf.csrf import CSRFProtect
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from werkzeug.middleware.proxy_fix import ProxyFix
from app.models import db, User
from config.settings import config

login_manager = LoginManager()
mail          = Mail()
csrf          = CSRFProtect()
# Default limits are a blunt anti-abuse backstop, not a usage cap. The old
# "200 per day; 100 per hour" tripped on ordinary browsing - one user clicking
# through the wizard, dashboard and lawyer listing burns dozens of requests in
# a minute. Sensitive endpoints keep their own tighter per-route limits.
limiter       = Limiter(
    key_func=get_remote_address,
    default_limits=["2000 per hour"],
    storage_uri="memory://",
)
logger        = logging.getLogger(__name__)


def _configure_logging(app):
    """
    Send application logs to a rotating file as well as the console.

    Mail failures, 5xx responses and payment errors were previously only
    written to stderr, which is lost on Render between deploys. LOG_DIR can
    override the location; logging degrades to console-only if the filesystem
    is read-only rather than taking the app down.
    """
    level = logging.DEBUG if app.config.get('DEBUG') else logging.INFO
    fmt   = logging.Formatter('%(asctime)s %(levelname)-8s [%(name)s] %(message)s')

    root = logging.getLogger()
    root.setLevel(level)

    if not any(type(h) is logging.StreamHandler for h in root.handlers):
        console = logging.StreamHandler()
        console.setFormatter(fmt)
        root.addHandler(console)

    log_dir = app.config.get('LOG_DIR') or os.path.join(
        os.path.dirname(os.path.dirname(__file__)), 'logs'
    )
    try:
        os.makedirs(log_dir, exist_ok=True)
        log_path = os.path.abspath(os.path.join(log_dir, 'rentritz.log'))
        already = any(
            isinstance(h, RotatingFileHandler) and
            getattr(h, 'baseFilename', '') == log_path
            for h in root.handlers
        )
        if not already:
            file_handler = RotatingFileHandler(
                log_path, maxBytes=5 * 1024 * 1024, backupCount=5, encoding='utf-8',
            )
            file_handler.setFormatter(fmt)
            file_handler.setLevel(level)
            root.addHandler(file_handler)
        app.logger.info('File logging enabled at %s', log_path)
    except OSError as e:
        app.logger.warning('File logging unavailable (%s) - console only', e)

    app.logger.setLevel(level)


def create_app(env=None):
    env = env or os.environ.get('FLASK_ENV', 'production')

    # ── Sentry error monitoring ───────────────────────────────────────────────
    sentry_dsn = os.environ.get('SENTRY_DSN', '').strip()
    if sentry_dsn:
        try:
            import sentry_sdk
            from sentry_sdk.integrations.flask import FlaskIntegration
            sentry_sdk.init(
                dsn=sentry_dsn,
                integrations=[FlaskIntegration()],
                traces_sample_rate=0.1,
            )
            logger.info('Sentry initialised')
        except Exception as e:
            logger.warning('Sentry initialisation failed: %s', e)

    app = Flask(__name__,
        template_folder = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'templates'),
        static_folder   = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'static'))
    app.config.from_object(config.get(env, config['production']))
    app.config['TEMPLATES_AUTO_RELOAD'] = (env == 'development')
    app.config['PROPAGATE_EXCEPTIONS'] = (env == 'development')

    _configure_logging(app)

    # ── Reverse proxy awareness ──────────────────────────────────────────────
    # Render (and any other PaaS load balancer) terminates TLS and forwards the
    # request over plain HTTP. Without this, request.remote_addr is the proxy's
    # address - so every visitor shares one rate-limit bucket - and
    # url_for(..., _external=True) emits http:// links in verification and
    # password-reset emails. Trusting exactly one hop is correct for Render;
    # trusting more would let a client spoof X-Forwarded-For and evade limits.
    if app.config.get('TRUST_PROXY', True):
        app.wsgi_app = ProxyFix(
            app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_port=1, x_prefix=1
        )

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
        # hCaptcha is disabled app-wide, so its origins are no longer allowed.
        response.headers['Content-Security-Policy'] = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' fonts.googleapis.com "
                "https://cdn.jsdelivr.net https://esm.sh; "
            "style-src 'self' 'unsafe-inline' fonts.googleapis.com fonts.gstatic.com; "
            "font-src fonts.gstatic.com; "
            "img-src 'self' images.unsplash.com data:; "
            "connect-src 'self' https://esm.sh"
        )
        if not app.config.get('DEBUG'):
            response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
        response.headers.remove('Server')
        response.headers.remove('X-Powered-By')

        # Prevent browsers from caching HTML responses
        if 'text/html' in response.content_type:
            response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
            response.headers['Pragma']        = 'no-cache'
            response.headers['Expires']       = '0'

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

    from app.lawyers.routes import lawyers_bp
    app.register_blueprint(lawyers_bp, url_prefix='/lawyers')

    # Serve locally-uploaded files (lawyer photos, licence PDFs)
    from flask import send_from_directory

    @app.route('/uploads/<path:filename>')
    def serve_upload(filename):
        from flask_login import current_user
        from flask import abort
        # Licence PDFs are admin-only - they contain sensitive legal credentials
        if filename.startswith('lawyers/licences/'):
            if not current_user.is_authenticated or current_user.role != 'admin':
                abort(403)
        upload_folder = app.config.get(
            'UPLOAD_FOLDER',
            os.path.join(app.root_path, '..', 'uploads'),
        )
        return send_from_directory(upload_folder, filename)

    @app.context_processor
    def inject_hcaptcha():
        return dict(hcaptcha_site_key=os.environ.get('HCAPTCHA_SITE_KEY', '').strip())

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

    # ── Schema bootstrap (opt-in) ────────────────────────────────────────────
    # This used to run db.create_all(), seven ALTER TABLEs and a data seed on
    # EVERY boot, against production, on every Render restart and every worker.
    # It is now explicit: set RUN_DB_BOOTSTRAP=true for a first deploy or after
    # a schema change, then unset it. Leaving it off makes normal restarts a
    # pure no-op against the database.
    if os.environ.get('RUN_DB_BOOTSTRAP', '').strip().lower() in ('1', 'true', 'yes'):
        with app.app_context():
            app.logger.info('RUN_DB_BOOTSTRAP set - creating/migrating schema')
            db.create_all()
            _migrate_schema()
            _seed_initial_data()
            app.logger.info('Schema bootstrap complete')
    else:
        app.logger.info('RUN_DB_BOOTSTRAP not set - skipping schema bootstrap')

    return app


def _migrate_schema():
    """Add any new columns to existing tables that db.create_all() won't add."""
    from sqlalchemy import text
    stmts = [
        'ALTER TABLE questions ADD COLUMN IF NOT EXISTS has_been_viewed BOOLEAN NOT NULL DEFAULT FALSE',
        'ALTER TABLE questions ADD COLUMN IF NOT EXISTS answer_viewed BOOLEAN NOT NULL DEFAULT FALSE',
        'ALTER TABLE users ADD COLUMN IF NOT EXISTS reset_token VARCHAR(100)',
        'ALTER TABLE users ADD COLUMN IF NOT EXISTS reset_token_expiry TIMESTAMP',
        'ALTER TABLE users ADD COLUMN IF NOT EXISTS failed_login_count INTEGER NOT NULL DEFAULT 0',
        'ALTER TABLE users ADD COLUMN IF NOT EXISTS failed_login_lockout TIMESTAMP',
        'ALTER TABLE users ADD COLUMN IF NOT EXISTS has_seen_onboarding BOOLEAN NOT NULL DEFAULT FALSE',
        # users.is_active was nullable with no server default. A NULL there makes
        # Flask-Login's login_user() fail silently (UserMixin.is_active is falsy),
        # so the user is rejected with no error anywhere. Backfill, then make the
        # column NOT NULL DEFAULT TRUE so a NULL can never reappear.
        'UPDATE users SET is_active = TRUE WHERE is_active IS NULL',
        'ALTER TABLE users ALTER COLUMN is_active SET DEFAULT TRUE',
        'ALTER TABLE users ALTER COLUMN is_active SET NOT NULL',
        'UPDATE users SET is_verified = FALSE WHERE is_verified IS NULL',
        'ALTER TABLE users ALTER COLUMN is_verified SET DEFAULT FALSE',
        'UPDATE users SET credits = 0 WHERE credits IS NULL',
    ]
    for stmt in stmts:
        try:
            db.session.execute(text(stmt))
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            logger.warning('schema bootstrap statement failed: %s -- %s', stmt, e)


def _seed_initial_data():
    from app.models import Category, User, LawyerSpecialisation

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

    if LawyerSpecialisation.query.count() == 0:
        specs = [
            LawyerSpecialisation(name='Tenancy',     slug='tenancy',     icon='home',      order=1),
            LawyerSpecialisation(name='Employment',  slug='employment',  icon='briefcase', order=2),
            LawyerSpecialisation(name='Corporate',   slug='corporate',   icon='building',  order=3),
            LawyerSpecialisation(name='Family',      slug='family',      icon='users',     order=4),
            LawyerSpecialisation(name='Criminal',    slug='criminal',    icon='shield',    order=5),
            LawyerSpecialisation(name='Civil',       slug='civil',       icon='scale',     order=6),
            LawyerSpecialisation(name='Immigration', slug='immigration', icon='globe',     order=7),
        ]
        db.session.add_all(specs)
        logger.info('Lawyer specialisations seeded')

    db.session.commit()