import os
import logging
from flask import Flask, abort, render_template
from flask_login import LoginManager
from flask_mail import Mail
from flask_wtf.csrf import CSRFProtect
from app.models import db, User
from config.settings import config

login_manager = LoginManager()
mail          = Mail()
csrf          = CSRFProtect()
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

    login_manager.login_view    = 'auth.login'
    login_manager.login_message = 'Please sign in to continue.'

    @login_manager.user_loader
    def load_user(user_id):
        return db.session.get(User, int(user_id))

    @app.after_request
    def set_security_headers(response):
        response.headers['X-Content-Type-Options']  = 'nosniff'
        response.headers['X-Frame-Options']         = 'DENY'
        response.headers['X-XSS-Protection']        = '1; mode=block'
        response.headers['Referrer-Policy']         = 'strict-origin-when-cross-origin'
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

    @app.errorhandler(404)
    def not_found(e):
        return render_template('errors/404.html'), 404

    @app.errorhandler(403)
    def forbidden(e):
        return render_template('errors/403.html'), 403

    @app.errorhandler(500)
    def server_error(e):
        logger.error(f'Server error: {e}')
        return render_template('errors/500.html'), 500

    with app.app_context():
        db.create_all()
        _seed_initial_data()

    return app


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