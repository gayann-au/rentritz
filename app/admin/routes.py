import json
import logging
import os
from functools import wraps
from datetime import datetime, timedelta
from flask import Blueprint, render_template, redirect, url_for, request, flash, session, jsonify, g
from flask_login import current_user, login_user, logout_user
from flask_mail import Message
from app import limiter, mail
from app.models import db, User, Category, Scenario, Question, Payment, CreditLog, \
    LawyerProfile, LawyerBooking, LawyerReview

admin_bp = Blueprint('admin', __name__)
logger   = logging.getLogger(__name__)

# Dedicated file logger for admin access events
_admin_access_logger = logging.getLogger('admin_access')
_admin_access_logger.setLevel(logging.INFO)
_admin_access_logger.propagate = False
_admin_log_path = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'admin_access.log'
)
_afh = logging.FileHandler(_admin_log_path, encoding='utf-8')
_afh.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(message)s'))
_admin_access_logger.addHandler(_afh)


def _log_admin_access(event, email, ip, success, detail=None):
    rid = getattr(g, 'request_id', '-')
    parts = [
        'event=%s' % event,
        'email=%s' % email,
        'ip=%s' % ip,
        'success=%s' % success,
        'request_id=%s' % rid,
    ]
    if detail:
        parts.append('detail=%s' % detail)
    msg = ' '.join(parts)
    _admin_access_logger.info(msg)
    logger.info('[admin_access] %s' % msg)


def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role != 'admin' or not session.get('admin_verified'):
            logger.warning(f'Unauthorized admin access from {request.remote_addr}')
            session.pop('admin_verified', None)
            return redirect(url_for('admin.login'))
        return f(*args, **kwargs)
    return decorated


# ── AUTH ──────────────────────────────────────────────────────────────────────

@admin_bp.route('/login', methods=['GET', 'POST'])
@limiter.limit("3 per minute; 10 per hour", methods=["POST"])
def login():
    if current_user.is_authenticated and current_user.role == 'admin' and session.get('admin_verified'):
        return redirect(url_for('admin.dashboard'))

    if request.method == 'POST':
        email    = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        ip       = request.remote_addr
        user     = User.query.filter_by(email=email, role='admin').first()

        if user and user.check_password(password) and user.is_active:
            login_user(user)
            session['admin_verified'] = True
            user.last_login = datetime.utcnow()
            db.session.commit()
            _log_admin_access('admin_login', email, ip, success=True)
            return redirect(url_for('admin.dashboard'))

        _log_admin_access('admin_login', email, ip, success=False,
                          detail='bad_credentials' if not user else 'wrong_password_or_inactive')
        flash('Invalid credentials.', 'error')

    return render_template('admin/login.html')


@admin_bp.route('/logout')
def logout():
    logger.info(f'Admin logout: {current_user.email if current_user.is_authenticated else "unknown"}')
    session.pop('admin_verified', None)
    logout_user()
    return redirect(url_for('admin.login'))


# ── DASHBOARD ─────────────────────────────────────────────────────────────────

@admin_bp.route('/')
@admin_required
def dashboard():
    now        = datetime.utcnow()
    today      = now.replace(hour=0, minute=0, second=0, microsecond=0)
    seven_ago  = now - timedelta(days=7)
    thirty_ago = now - timedelta(days=30)
    lockout_window = now - timedelta(minutes=15)

    # ── User stats
    user_stats = {
        'total_users':    User.query.filter(User.role != 'admin').count(),
        'new_users_today': User.query.filter(User.role != 'admin', User.created_at >= today).count(),
        'new_users_7d':   User.query.filter(User.role != 'admin', User.created_at >= seven_ago).count(),
        'new_users_30d':  User.query.filter(User.role != 'admin', User.created_at >= thirty_ago).count(),
        'active_users':   User.query.filter(User.role != 'admin', User.is_active == True).count(),
        'locked_users':   User.query.filter(
            User.failed_login_lockout != None,
            User.failed_login_lockout > lockout_window,
        ).count(),
        'tenants':        User.query.filter_by(role='tenant').count(),
        'landlords':      User.query.filter_by(role='landlord').count(),
    }

    # ── Consultation stats
    q_stats = {
        'total_questions':    Question.query.count(),
        'answered_questions': Question.query.filter_by(status='answered').count(),
        'pending_questions':  Question.query.filter_by(status='pending').count(),
        'questions_today':    Question.query.filter(Question.created_at >= today).count(),
        'questions_7d':       Question.query.filter(Question.created_at >= seven_ago).count(),
    }

    # ── Content stats
    all_scenarios = Scenario.query.all()
    content_stats = {
        'total_scenarios':      len(all_scenarios),
        'active_scenarios':     sum(1 for s in all_scenarios if s.is_active),
        'incomplete_scenarios': sum(1 for s in all_scenarios if not s.is_complete),
        'total_categories':     Category.query.count(),
        'categories_with_tree': Category.query.filter(Category.tree_json != None).count(),
    }

    # ── Revenue stats
    def _rev(extra_filter=None):
        q = db.session.query(db.func.sum(Payment.amount_aed)).filter_by(status='captured')
        if extra_filter is not None:
            q = q.filter(extra_filter)
        return float(q.scalar() or 0)

    rev_stats = {
        'total_revenue':    _rev(),
        'revenue_7d':       _rev(Payment.created_at >= seven_ago),
        'revenue_30d':      _rev(Payment.created_at >= thirty_ago),
        'pending_payments': Payment.query.filter_by(status='pending').count(),
        'failed_payments':  Payment.query.filter_by(status='failed').count(),
    }

    # ── Recent activity
    recent_users = User.query.filter(User.role != 'admin')\
                       .order_by(User.created_at.desc()).limit(5).all()
    recent_questions = Question.query.filter_by(status='answered')\
                           .order_by(Question.answered_at.desc()).limit(8).all()
    recent_payments = Payment.query.filter_by(status='captured')\
                         .order_by(Payment.created_at.desc()).limit(5).all()

    # ── Category breakdown
    categories = Category.query.order_by(Category.order).all()
    category_stats = []
    for cat in categories:
        total_q    = Question.query.filter_by(category_slug=cat.slug).count()
        active_sc  = Scenario.query.filter_by(category_id=cat.id, is_active=True).count()
        category_stats.append({
            'category':        cat,
            'total_questions': total_q,
            'active_scenarios': active_sc,
        })

    # ── Lawyer marketplace stats
    lawyer_stats = {
        'total_profiles':  LawyerProfile.query.count(),
        'verified':        LawyerProfile.query.filter_by(
                               verification_status='verified').count(),
        'pending':         LawyerProfile.query.filter(
                               LawyerProfile.verification_status.in_(
                                   ['pending_review', 'unverified']
                               )).count(),
        'total_unlocks':   db.session.query(
                               db.func.sum(LawyerProfile.total_unlocks)
                           ).scalar() or 0,
        'total_completed': LawyerBooking.query.filter_by(
                               status='completed').count(),
        'total_reviews':   LawyerReview.query.count(),
        'avg_rating':      round(float(
                               db.session.query(
                                   db.func.avg(LawyerReview.rating)
                               ).scalar() or 0
                           ), 1),
    }

    hour = now.hour + 4  # GST offset
    if hour < 12:
        greeting = 'Good morning'
    elif hour < 18:
        greeting = 'Good afternoon'
    else:
        greeting = 'Good evening'

    return render_template(
        'admin/dashboard.html',
        greeting       = greeting,
        server_time    = (now + timedelta(hours=4)).strftime('%A, %d %B %Y | %H:%M GST'),
        user_stats     = user_stats,
        q_stats        = q_stats,
        content_stats  = content_stats,
        rev_stats      = rev_stats,
        recent_users   = recent_users,
        recent_questions = recent_questions,
        recent_payments  = recent_payments,
        category_stats   = category_stats,
        lawyer_stats     = lawyer_stats,
    )


@admin_bp.route('/api/pending-count')
@limiter.exempt
@admin_required
def api_pending_count():
    now = datetime.utcnow()
    lockout_window = now - timedelta(minutes=15)
    pending = Question.query.filter_by(status='pending').count()
    locked  = User.query.filter(
        User.failed_login_lockout != None,
        User.failed_login_lockout > lockout_window,
    ).count()
    lawyer_pending = LawyerProfile.query.filter(
        LawyerProfile.verification_status.in_(['pending_review', 'unverified'])
    ).count()
    return jsonify({'pending': pending, 'locked': locked, 'lawyer_pending': lawyer_pending})


# ── CATEGORIES ────────────────────────────────────────────────────────────────

@admin_bp.route('/categories')
@admin_required
def categories():
    cats = Category.query.order_by(Category.order).all()
    return render_template('admin/categories.html', categories=cats)


@admin_bp.route('/categories/new', methods=['GET', 'POST'])
@admin_required
def new_category():
    if request.method == 'POST':
        slug = request.form.get('slug', '').strip().lower()
        if Category.query.filter_by(slug=slug).first():
            flash('A category with this slug already exists.', 'error')
            return render_template('admin/category_form.html', cat=None)

        cat = Category(
            slug        = slug,
            title       = request.form.get('title', '').strip(),
            description = request.form.get('description', '').strip(),
            icon        = request.form.get('icon', '').strip(),
            for_role    = request.form.get('for_role', 'both'),
            order       = int(request.form.get('order', 99)),
            is_active   = True,
        )
        db.session.add(cat)
        db.session.commit()
        logger.info(f'Category created: {cat.slug}')
        flash('Category created.', 'success')
        return redirect(url_for('admin.categories'))

    return render_template('admin/category_form.html', cat=None)


@admin_bp.route('/categories/<int:id>/edit', methods=['GET', 'POST'])
@admin_required
def edit_category(id):
    cat = Category.query.get_or_404(id)

    if request.method == 'POST':
        cat.title       = request.form.get('title', '').strip()
        cat.description = request.form.get('description', '').strip()
        cat.icon        = request.form.get('icon', '').strip()
        cat.for_role    = request.form.get('for_role', 'both')
        cat.order       = int(request.form.get('order', 99))
        db.session.commit()
        flash('Category updated.', 'success')
        return redirect(url_for('admin.categories'))

    return render_template('admin/category_form.html', cat=cat)


@admin_bp.route('/categories/<int:id>/toggle', methods=['POST'])
@admin_required
def toggle_category(id):
    cat           = Category.query.get_or_404(id)
    cat.is_active = not cat.is_active
    db.session.commit()
    return redirect(url_for('admin.categories'))


# ── DECISION TREE BUILDER ─────────────────────────────────────────────────────

@admin_bp.route('/categories/<int:id>/tree')
@admin_required
def tree_builder(id):
    cat            = Category.query.get_or_404(id)
    scenarios      = Scenario.query.filter_by(is_active=True)\
                         .order_by(Scenario.title).all()
    scenarios_data = [{'id': s.id, 'slug': s.slug, 'title': s.title, 'for_role': s.for_role} for s in scenarios]
    return render_template('admin/tree_builder.html', category=cat, scenarios=scenarios_data)


@admin_bp.route('/categories/<int:id>/tree/save', methods=['POST'])
@admin_required
def tree_save(id):
    cat = Category.query.get_or_404(id)

    try:
        data = request.get_json(force=True)
        if not data or 'tree' not in data:
            return jsonify({'ok': False, 'error': 'No tree data provided.'}), 400

        tree = data['tree']

        errors = _validate_tree(tree)
        if errors:
            return jsonify({'ok': False, 'error': errors[0]}), 400

        cat.tree_json  = tree
        cat.updated_at = datetime.utcnow()
        db.session.commit()

        logger.info(f'Tree saved for category: {cat.slug}')
        return jsonify({'ok': True, 'message': 'Decision tree saved successfully.'})

    except Exception as e:
        logger.error(f'Tree save error for category {id}: {e}')
        return jsonify({'ok': False, 'error': 'An unexpected error occurred.'}), 500


@admin_bp.route('/categories/<int:id>/tree/clear', methods=['POST'])
@admin_required
def tree_clear(id):
    cat            = Category.query.get_or_404(id)
    cat.tree_json  = None
    cat.updated_at = datetime.utcnow()
    db.session.commit()
    flash('Decision tree cleared.', 'success')
    return redirect(url_for('admin.tree_builder', id=id))


def _validate_tree(node, depth=0):
    if depth > 10:
        return ['Tree is too deep (max 10 levels).']

    errors = []

    if not isinstance(node, dict):
        return ['Tree node must be an object.']

    if not node.get('question', '').strip():
        errors.append('Every node must have a question.')

    if not node.get('key', '').strip():
        errors.append('Every node must have a key.')

    options = node.get('options', [])
    if not options:
        errors.append(f'Node "{node.get("question", "")}" has no options.')

    for opt in options:
        if not opt.get('label', '').strip():
            errors.append('Every option must have a label.')
        if 'scenario' not in opt and 'next' not in opt:
            errors.append(f'Option "{opt.get("label", "")}" must link to a scenario or next question.')
        if 'next' in opt:
            errors.extend(_validate_tree(opt['next'], depth + 1))

    return errors


# ── SCENARIOS ─────────────────────────────────────────────────────────────────

@admin_bp.route('/scenarios')
@admin_required
def scenarios():
    category_id   = request.args.get('category_id', type=int)
    role_filter   = request.args.get('role', '')
    status_filter = request.args.get('status', '')
    query         = Scenario.query

    if category_id:
        query = query.filter_by(category_id=category_id)
    if role_filter in ('tenant', 'landlord', 'both'):
        query = query.filter_by(for_role=role_filter)
    if status_filter == 'active':
        query = query.filter_by(is_active=True)
    elif status_filter == 'inactive':
        query = query.filter_by(is_active=False)

    items = query.order_by(Scenario.created_at.desc()).all()
    cats  = Category.query.order_by(Category.order).all()
    for s in items:
        if s.created_at:
            s.created_at = s.created_at + timedelta(hours=4)
    return render_template('admin/scenarios.html', scenarios=items, categories=cats,
                           selected_category=category_id,
                           role_filter=role_filter,
                           status_filter=status_filter)


@admin_bp.route('/scenarios/new', methods=['GET', 'POST'])
@admin_required
def new_scenario():
    cats = Category.query.order_by(Category.order).all()

    if request.method == 'POST':
        slug = request.form.get('slug', '').strip().lower()
        if Scenario.query.filter_by(slug=slug).first():
            flash('A scenario with this slug already exists.', 'error')
            return render_template('admin/scenario_form.html', scenario=None, categories=cats)

        rights_tenant        = _parse_bullet_list(request.form.get('tenant_rights', ''))
        rights_landlord      = _parse_bullet_list(request.form.get('landlord_rights', ''))
        what_to_do           = _parse_bullet_list(request.form.get('what_to_do', ''))
        landlord_what_to_do  = _parse_bullet_list(request.form.get('landlord_what_to_do', ''))
        law_refs             = _parse_bullet_list(request.form.get('law_refs', ''))

        s = Scenario(
            category_id         = int(request.form.get('category_id')),
            slug                = slug,
            title               = request.form.get('title', '').strip(),
            headline            = request.form.get('headline', '').strip(),
            situation           = request.form.get('situation', '').strip(),
            landlord_headline   = request.form.get('landlord_headline', '').strip() or None,
            landlord_situation  = request.form.get('landlord_situation', '').strip() or None,
            tenant_rights       = rights_tenant,
            landlord_rights     = rights_landlord,
            what_to_do          = what_to_do,
            landlord_what_to_do = landlord_what_to_do or None,
            law_refs            = law_refs,
            keywords            = request.form.get('keywords', '').strip(),
            for_role            = request.form.get('for_role', 'both'),
            show_rera_button    = 'show_rera_button' in request.form,
            is_active           = True,
        )
        db.session.add(s)
        db.session.commit()
        logger.info(f'Scenario created: {s.slug}')
        flash('Scenario created successfully.', 'success')
        return redirect(url_for('admin.scenarios'))

    return render_template('admin/scenario_form.html', scenario=None, categories=cats)


@admin_bp.route('/scenarios/<int:id>/edit', methods=['GET', 'POST'])
@admin_required
def edit_scenario(id):
    s    = Scenario.query.get_or_404(id)
    cats = Category.query.order_by(Category.order).all()

    if request.method == 'POST':
        new_slug = request.form.get('slug', '').strip().lower()
        existing = Scenario.query.filter_by(slug=new_slug).first()
        if existing and existing.id != s.id:
            flash('A scenario with this slug already exists.', 'error')
            return render_template('admin/scenario_form.html', scenario=s, categories=cats)
        s.slug                = new_slug
        s.category_id         = int(request.form.get('category_id'))
        s.title               = request.form.get('title', '').strip()
        s.headline            = request.form.get('headline', '').strip()
        s.situation           = request.form.get('situation', '').strip()
        s.landlord_headline   = request.form.get('landlord_headline', '').strip() or None
        s.landlord_situation  = request.form.get('landlord_situation', '').strip() or None
        s.tenant_rights       = _parse_bullet_list(request.form.get('tenant_rights', ''))
        s.landlord_rights     = _parse_bullet_list(request.form.get('landlord_rights', ''))
        s.what_to_do          = _parse_bullet_list(request.form.get('what_to_do', ''))
        s.landlord_what_to_do = _parse_bullet_list(request.form.get('landlord_what_to_do', '')) or None
        s.law_refs            = _parse_bullet_list(request.form.get('law_refs', ''))
        s.keywords            = request.form.get('keywords', '').strip()
        s.for_role            = request.form.get('for_role', 'both')
        s.show_rera_button    = 'show_rera_button' in request.form
        s.updated_at          = datetime.utcnow()
        db.session.commit()
        flash('Scenario updated successfully.', 'success')
        return redirect(url_for('admin.scenarios'))

    return render_template('admin/scenario_form.html', scenario=s, categories=cats)


@admin_bp.route('/scenarios/<int:id>/delete', methods=['POST'])
@admin_required
def delete_scenario(id):
    s = Scenario.query.get_or_404(id)
    db.session.delete(s)
    db.session.commit()
    logger.info(f'Scenario deleted: {s.slug}')
    flash('Scenario deleted.', 'success')
    return redirect(url_for('admin.scenarios'))


@admin_bp.route('/scenarios/<int:id>/toggle', methods=['POST'])
@admin_required
def toggle_scenario(id):
    s           = Scenario.query.get_or_404(id)
    s.is_active = not s.is_active
    db.session.commit()
    return redirect(url_for('admin.scenarios'))


@admin_bp.route('/scenarios/<int:id>/preview')
@admin_required
def preview_scenario(id):
    s        = Scenario.query.get_or_404(id)
    category = s.category
    return render_template('admin/scenario_preview.html', scenario=s, category=category)


# ── BULK IMPORT ───────────────────────────────────────────────────────────────

@admin_bp.route('/import', methods=['GET', 'POST'])
@admin_required
def bulk_import():
    cats = Category.query.order_by(Category.order).all()

    if request.method == 'POST':
        category_id = request.form.get('category_id', type=int)
        raw_text    = request.form.get('content', '').strip()

        if not category_id or not raw_text:
            flash('Category and content are required.', 'error')
            return render_template('admin/bulk_import.html', categories=cats)

        cat = Category.query.get_or_404(category_id)

        try:
            drafts = _parse_bulk_import(raw_text, cat)
        except Exception as e:
            flash(f'Could not parse content: {str(e)}', 'error')
            return render_template('admin/bulk_import.html', categories=cats)

        session['import_drafts']      = drafts
        session['import_category_id'] = category_id
        flash(f'{len(drafts)} scenario(s) parsed. Review and confirm below.', 'success')
        return redirect(url_for('admin.bulk_import_review'))

    return render_template('admin/bulk_import.html', categories=cats)


@admin_bp.route('/import/review', methods=['GET', 'POST'])
@admin_required
def bulk_import_review():
    drafts      = session.get('import_drafts', [])
    category_id = session.get('import_category_id')

    if not drafts or not category_id:
        flash('No import in progress.', 'error')
        return redirect(url_for('admin.bulk_import'))

    cat = Category.query.get_or_404(category_id)

    if request.method == 'POST':
        saved = 0
        for i, draft in enumerate(drafts):
            if request.form.get(f'include_{i}') != 'on':
                continue

            slug = request.form.get(f'slug_{i}', draft.get('slug', '')).strip().lower()
            if not slug or Scenario.query.filter_by(slug=slug).first():
                continue

            s = Scenario(
                category_id     = category_id,
                slug            = slug,
                title           = request.form.get(f'title_{i}', draft.get('title', '')).strip(),
                headline        = request.form.get(f'headline_{i}', draft.get('headline', '')).strip(),
                situation       = request.form.get(f'situation_{i}', draft.get('situation', '')).strip(),
                tenant_rights   = _parse_bullet_list(request.form.get(f'tenant_rights_{i}', '')),
                landlord_rights = _parse_bullet_list(request.form.get(f'landlord_rights_{i}', '')),
                what_to_do      = _parse_bullet_list(request.form.get(f'what_to_do_{i}', '')),
                law_refs        = _parse_bullet_list(request.form.get(f'law_refs_{i}', '')),
                keywords        = request.form.get(f'keywords_{i}', '').strip(),
                for_role        = request.form.get(f'for_role_{i}', 'both'),
                is_active       = False,
            )
            db.session.add(s)
            saved += 1

        db.session.commit()
        session.pop('import_drafts', None)
        session.pop('import_category_id', None)
        logger.info(f'Bulk import: {saved} scenarios saved for category {category_id}')
        flash(f'{saved} scenario(s) saved as drafts. Activate them when ready.', 'success')
        return redirect(url_for('admin.scenarios', category_id=category_id))

    return render_template('admin/bulk_import_review.html', drafts=drafts, category=cat)


def _parse_bulk_import(raw_text, category):
    blocks    = [b.strip() for b in raw_text.split('---') if b.strip()]
    drafts    = []
    slug_base = category.slug

    for i, block in enumerate(blocks):
        lines = block.strip().split('\n')
        draft = {
            'title':           '',
            'slug':            f'{slug_base}_scenario_{i + 1}',
            'headline':        '',
            'situation':       '',
            'tenant_rights':   '',
            'landlord_rights': '',
            'what_to_do':      '',
            'law_refs':        '',
            'keywords':        '',
            'for_role':        'both',
        }
        current_section = 'situation'
        buffer          = []

        for line in lines:
            low = line.strip().lower()

            if low.startswith('title:'):
                draft['title']    = line.split(':', 1)[1].strip()
            elif low.startswith('headline:'):
                draft['headline'] = line.split(':', 1)[1].strip()
            elif low.startswith('slug:'):
                draft['slug']     = line.split(':', 1)[1].strip().lower()
            elif low.startswith('for_role:') or low.startswith('for role:'):
                draft['for_role'] = line.split(':', 1)[1].strip().lower()
            elif low.startswith('situation:') or low.startswith('overview:'):
                if buffer:
                    draft[current_section] = '\n'.join(buffer).strip()
                current_section = 'situation'
                buffer          = [line.split(':', 1)[1].strip()] if ':' in line else []
            elif low.startswith('tenant rights:') or low.startswith('tenant_rights:'):
                if buffer:
                    draft[current_section] = '\n'.join(buffer).strip()
                current_section = 'tenant_rights'
                buffer          = []
            elif low.startswith('landlord rights:') or low.startswith('landlord_rights:'):
                if buffer:
                    draft[current_section] = '\n'.join(buffer).strip()
                current_section = 'landlord_rights'
                buffer          = []
            elif low.startswith('what to do:') or low.startswith('what_to_do:') or low.startswith('steps:'):
                if buffer:
                    draft[current_section] = '\n'.join(buffer).strip()
                current_section = 'what_to_do'
                buffer          = []
            elif low.startswith('law refs:') or low.startswith('law_refs:') or low.startswith('laws:'):
                if buffer:
                    draft[current_section] = '\n'.join(buffer).strip()
                current_section = 'law_refs'
                buffer          = []
            elif low.startswith('keywords:'):
                if buffer:
                    draft[current_section] = '\n'.join(buffer).strip()
                draft['keywords'] = line.split(':', 1)[1].strip()
                current_section   = None
                buffer            = []
            else:
                if line.strip():
                    buffer.append(line.strip())

        if buffer and current_section:
            draft[current_section] = '\n'.join(buffer).strip()

        if not draft['title']:
            draft['title'] = f'{category.title} - Scenario {i + 1}'

        drafts.append(draft)

    return drafts


# ── USERS ─────────────────────────────────────────────────────────────────────

PER_PAGE = 20

@admin_bp.route('/users')
@admin_required
def users():
    search        = request.args.get('search', '').strip()
    role_filter   = request.args.get('role', '')
    status_filter = request.args.get('status', '')
    page          = max(1, request.args.get('page', 1, type=int))
    now           = datetime.utcnow()

    query = User.query.filter(User.role != 'admin')

    if search:
        like = f'%{search}%'
        query = query.filter(
            db.or_(User.full_name.ilike(like), User.email.ilike(like))
        )

    if role_filter in ('tenant', 'landlord'):
        query = query.filter_by(role=role_filter)

    if status_filter == 'active':
        query = query.filter_by(is_active=True)
    elif status_filter == 'inactive':
        query = query.filter_by(is_active=False)
    elif status_filter == 'locked':
        lockout_window = now - timedelta(minutes=15)
        query = query.filter(
            User.failed_login_lockout != None,
            User.failed_login_lockout > lockout_window,
        )

    total_count  = query.count()
    total_pages  = max(1, (total_count + PER_PAGE - 1) // PER_PAGE)
    page         = min(page, total_pages)
    offset       = (page - 1) * PER_PAGE
    users_page   = query.order_by(User.created_at.desc()).offset(offset).limit(PER_PAGE).all()

    return render_template(
        'admin/users.html',
        users         = users_page,
        total_count   = total_count,
        page          = page,
        total_pages   = total_pages,
        search        = search,
        role_filter   = role_filter,
        status_filter = status_filter,
        now           = now,
    )


@admin_bp.route('/users/<int:id>/toggle', methods=['POST'])
@admin_required
def toggle_user(id):
    user           = User.query.get_or_404(id)
    user.is_active = not user.is_active
    db.session.commit()
    logger.info(f'User {user.email} active={user.is_active} by admin')
    # Preserve current filter/search/page when redirecting back
    return redirect(request.referrer or url_for('admin.users'))


@admin_bp.route('/users/<int:user_id>/credits', methods=['POST'])
@admin_required
def add_credits(user_id):
    user = User.query.get_or_404(user_id)
    try:
        amount = int(request.form.get('amount') or 0)
    except (ValueError, TypeError):
        flash('Invalid credit amount.', 'error')
        return redirect(request.referrer or url_for('admin.users'))

    if amount != 0:
        user.credits = max(0, user.credits + amount)
        action = 'admin_grant' if amount > 0 else 'admin_deduct'
        note   = 'Credits added by admin' if amount > 0 else 'Credits deducted by admin'
        log = CreditLog(
            user_id = user.id,
            action  = action,
            amount  = amount,
            balance = user.credits,
            note    = note,
        )
        db.session.add(log)
        db.session.commit()
        verb = f'Added {amount}' if amount > 0 else f'Deducted {abs(amount)}'
        flash(f'{verb} credits for {user.email}.', 'success')
    return redirect(request.referrer or url_for('admin.users'))


@admin_bp.route('/users/<int:id>/detail')
@admin_required
def user_detail(id):
    user      = User.query.get_or_404(id)
    questions = Question.query.filter_by(user_id=id)\
                    .order_by(Question.created_at.desc()).all()
    logs      = CreditLog.query.filter_by(user_id=id)\
                    .order_by(CreditLog.created_at.desc()).all()
    return render_template('admin/user_detail.html', user=user, questions=questions, logs=logs)


# ── QUESTIONS ─────────────────────────────────────────────────────────────────

Q_PER_PAGE = 25

@admin_bp.route('/questions')
@admin_required
def questions():
    status_filter   = request.args.get('status', '')
    category_filter = request.args.get('category', '')
    role_filter     = request.args.get('role', '')
    date_filter     = request.args.get('date', '')
    page            = max(1, request.args.get('page', 1, type=int))
    now             = datetime.utcnow()

    query = Question.query.join(User, Question.user_id == User.id)

    if status_filter in ('pending', 'answered'):
        query = query.filter(Question.status == status_filter)

    if category_filter:
        query = query.filter(Question.category_slug == category_filter)

    if role_filter in ('tenant', 'landlord'):
        query = query.filter(User.role == role_filter)

    if date_filter == 'today':
        query = query.filter(Question.created_at >= now.replace(hour=0, minute=0, second=0, microsecond=0))
    elif date_filter == '7d':
        query = query.filter(Question.created_at >= now - timedelta(days=7))
    elif date_filter == '30d':
        query = query.filter(Question.created_at >= now - timedelta(days=30))

    total_count   = query.count()
    total_pages   = max(1, (total_count + Q_PER_PAGE - 1) // Q_PER_PAGE)
    page          = min(page, total_pages)
    items         = query.order_by(Question.created_at.desc())\
                         .offset((page - 1) * Q_PER_PAGE).limit(Q_PER_PAGE).all()

    pending_total = Question.query.filter_by(status='pending').count()
    categories    = Category.query.order_by(Category.order).all()

    return render_template(
        'admin/questions.html',
        questions       = items,
        total_count     = total_count,
        page            = page,
        total_pages     = total_pages,
        pending_total   = pending_total,
        categories      = categories,
        status_filter   = status_filter,
        category_filter = category_filter,
        role_filter     = role_filter,
        date_filter     = date_filter,
    )


# ── PAYMENTS ──────────────────────────────────────────────────────────────────

PAY_PER_PAGE = 25

@admin_bp.route('/payments')
@admin_required
def payments():
    status_filter = request.args.get('status', '')
    date_filter   = request.args.get('date', '')
    search        = request.args.get('search', '').strip()
    page          = max(1, request.args.get('page', 1, type=int))
    now           = datetime.utcnow()

    query = Payment.query.join(User, Payment.user_id == User.id)

    if status_filter in ('pending', 'captured', 'failed'):
        query = query.filter(Payment.status == status_filter)

    if date_filter == 'today':
        query = query.filter(Payment.created_at >= now.replace(hour=0, minute=0, second=0, microsecond=0))
    elif date_filter == '7d':
        query = query.filter(Payment.created_at >= now - timedelta(days=7))
    elif date_filter == '30d':
        query = query.filter(Payment.created_at >= now - timedelta(days=30))

    if search:
        like = f'%{search}%'
        query = query.filter(
            db.or_(User.full_name.ilike(like), User.email.ilike(like))
        )

    total_count = query.count()
    total_pages = max(1, (total_count + PAY_PER_PAGE - 1) // PAY_PER_PAGE)
    page        = min(page, total_pages)
    items       = query.order_by(Payment.created_at.desc())\
                       .offset((page - 1) * PAY_PER_PAGE).limit(PAY_PER_PAGE).all()

    def _sum(q):
        return float(
            db.session.query(db.func.sum(Payment.amount_aed))
            .filter(Payment.id.in_([p.id for p in q.with_entities(Payment.id)]))
            .scalar() or 0
        )

    # Summary stats (unfiltered)
    total_captured_aed = float(
        db.session.query(db.func.sum(Payment.amount_aed))
        .filter(Payment.status == 'captured').scalar() or 0
    )
    total_pending_count = Payment.query.filter_by(status='pending').count()
    total_failed_count  = Payment.query.filter_by(status='failed').count()

    # Filtered AED total (captured only within current filter)
    filtered_q = query.filter(Payment.status == 'captured')
    filtered_total_aed = float(
        db.session.query(db.func.sum(Payment.amount_aed))
        .filter(Payment.id.in_(filtered_q.with_entities(Payment.id)))
        .scalar() or 0
    )

    return render_template(
        'admin/payments.html',
        payments            = items,
        total_count         = total_count,
        page                = page,
        total_pages         = total_pages,
        status_filter       = status_filter,
        date_filter         = date_filter,
        search              = search,
        total_captured_aed  = total_captured_aed,
        total_pending_count = total_pending_count,
        total_failed_count  = total_failed_count,
        filtered_total_aed  = filtered_total_aed,
    )


# ── HELPERS ───────────────────────────────────────────────────────────────────

def _parse_bullet_list(text):
    if not text:
        return []
    lines = [
        line.lstrip('•-*').strip()
        for line in text.strip().split('\n')
        if line.strip()
    ]
    return [l for l in lines if l]


# ── LAWYERS ───────────────────────────────────────────────────────────────────

LAW_PER_PAGE = 20

@admin_bp.route('/lawyers/')
@admin_required
def lawyers():
    from sqlalchemy import case as sa_case
    status_filter = request.args.get('status', '')
    search        = request.args.get('search', '').strip()
    page          = max(1, request.args.get('page', 1, type=int))

    query = LawyerProfile.query.join(User, LawyerProfile.user_id == User.id)

    if status_filter in ('unverified', 'pending_review', 'verified', 'rejected'):
        query = query.filter(LawyerProfile.verification_status == status_filter)

    if search:
        like = f'%{search}%'
        query = query.filter(
            db.or_(
                LawyerProfile.display_name.ilike(like),
                LawyerProfile.bar_number.ilike(like),
                User.full_name.ilike(like),
                User.email.ilike(like),
            )
        )

    status_order = sa_case(
        (LawyerProfile.verification_status == 'pending_review', 0),
        (LawyerProfile.verification_status == 'unverified', 1),
        (LawyerProfile.verification_status == 'verified', 2),
        (LawyerProfile.verification_status == 'rejected', 3),
        else_=4,
    )
    query = query.order_by(status_order, LawyerProfile.created_at.desc())

    total_count = query.count()
    total_pages = max(1, (total_count + LAW_PER_PAGE - 1) // LAW_PER_PAGE)
    page        = min(page, total_pages)
    profiles    = query.offset((page - 1) * LAW_PER_PAGE).limit(LAW_PER_PAGE).all()

    pending_count    = LawyerProfile.query.filter_by(verification_status='pending_review').count()
    unverified_count = LawyerProfile.query.filter_by(verification_status='unverified').count()
    verified_count   = LawyerProfile.query.filter_by(verification_status='verified').count()
    rejected_count   = LawyerProfile.query.filter_by(verification_status='rejected').count()

    return render_template(
        'admin/lawyers_list.html',
        profiles              = profiles,
        total_count           = total_count,
        page                  = page,
        total_pages           = total_pages,
        search                = search,
        current_status_filter = status_filter,
        pending_count         = pending_count,
        unverified_count      = unverified_count,
        verified_count        = verified_count,
        rejected_count        = rejected_count,
    )


@admin_bp.route('/lawyers/<int:profile_id>')
@admin_required
def lawyer_detail(profile_id):
    profile = LawyerProfile.query.get_or_404(profile_id)

    booking_count   = LawyerBooking.query.filter_by(lawyer_profile_id=profile_id).count()
    recent_bookings = LawyerBooking.query.filter_by(lawyer_profile_id=profile_id)\
                          .order_by(LawyerBooking.created_at.desc()).limit(5).all()

    reviews      = LawyerReview.query.filter_by(lawyer_profile_id=profile_id)\
                       .order_by(LawyerReview.created_at.desc()).limit(5).all()
    review_count = LawyerReview.query.filter_by(lawyer_profile_id=profile_id).count()

    avg_rating = None
    if review_count:
        result = db.session.query(db.func.avg(LawyerReview.rating))\
                     .filter(LawyerReview.lawyer_profile_id == profile_id).scalar()
        if result:
            avg_rating = round(float(result), 1)

    return render_template(
        'admin/lawyer_detail.html',
        profile         = profile,
        booking_count   = booking_count,
        recent_bookings = recent_bookings,
        reviews         = reviews,
        review_count    = review_count,
        avg_rating      = avg_rating,
    )


@admin_bp.route('/lawyers/<int:profile_id>/verify', methods=['POST'])
@admin_required
def verify_lawyer(profile_id):
    profile = LawyerProfile.query.get_or_404(profile_id)

    profile.verification_status  = 'verified'
    profile.is_active            = True
    profile.verified_at          = datetime.utcnow()
    profile.verified_by_admin_id = current_user.id
    profile.rejection_reason     = None
    profile.admin_notes          = request.form.get('admin_notes', '').strip() or None
    db.session.commit()

    name = profile.display_name or profile.user.full_name
    flash(f'{name} verified successfully.', 'success')
    logger.info(f'Lawyer profile {profile_id} verified by admin {current_user.email}')

    try:
        msg = Message(
            subject    = 'Your Rentritz Lawyer Profile Has Been Verified',
            recipients = [profile.user.email],
            html       = render_template(
                'email/lawyer_verified.html',
                profile   = profile,
                login_url = url_for('lawyers.dashboard', _external=True),
            ),
        )
        mail.send(msg)
    except Exception as e:
        logger.error(f'Failed to send verification email to {profile.user.email}: {e}')

    return redirect(url_for('admin.lawyer_detail', profile_id=profile_id))


@admin_bp.route('/lawyers/<int:profile_id>/reject', methods=['POST'])
@admin_required
def reject_lawyer(profile_id):
    profile = LawyerProfile.query.get_or_404(profile_id)

    reason = request.form.get('reason', '').strip()
    if not reason:
        flash('A rejection reason is required.', 'error')
        return redirect(url_for('admin.lawyer_detail', profile_id=profile_id))

    profile.verification_status = 'rejected'
    profile.rejection_reason    = reason
    profile.admin_notes         = request.form.get('admin_notes', '').strip() or None
    db.session.commit()

    flash('Profile rejected.', 'warning')
    logger.info(f'Lawyer profile {profile_id} rejected by admin {current_user.email}')

    try:
        msg = Message(
            subject    = 'Action Required: Your Rentritz Lawyer Profile',
            recipients = [profile.user.email],
            html       = render_template(
                'email/lawyer_rejected.html',
                profile  = profile,
                reason   = reason,
                edit_url = url_for('lawyers.edit_profile', _external=True),
            ),
        )
        mail.send(msg)
    except Exception as e:
        logger.error(f'Failed to send rejection email to {profile.user.email}: {e}')

    return redirect(url_for('admin.lawyer_detail', profile_id=profile_id))


@admin_bp.route('/lawyers/<int:profile_id>/toggle-active', methods=['POST'])
@admin_required
def toggle_lawyer_active(profile_id):
    profile           = LawyerProfile.query.get_or_404(profile_id)
    profile.is_active = not profile.is_active
    db.session.commit()
    logger.info(f'Lawyer profile {profile_id} is_active={profile.is_active} by admin {current_user.email}')
    return jsonify({'is_active': profile.is_active})


@admin_bp.route('/lawyers/<int:profile_id>/notes', methods=['POST'])
@admin_required
def update_lawyer_notes(profile_id):
    profile             = LawyerProfile.query.get_or_404(profile_id)
    profile.admin_notes = request.form.get('notes', '').strip() or None
    db.session.commit()
    return jsonify({'saved': True})