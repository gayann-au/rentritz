import json
import logging
from functools import wraps
from datetime import datetime, timedelta
from flask import Blueprint, render_template, redirect, url_for, request, flash, session, jsonify
from flask_login import current_user, login_user, logout_user
from app.models import db, User, Category, Scenario, Question, Payment, CreditLog

admin_bp = Blueprint('admin', __name__)
logger   = logging.getLogger(__name__)


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
def login():
    if current_user.is_authenticated and current_user.role == 'admin' and session.get('admin_verified'):
        return redirect(url_for('admin.dashboard'))

    if request.method == 'POST':
        email    = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        user     = User.query.filter_by(email=email, role='admin').first()

        if user and user.check_password(password) and user.is_active:
            login_user(user)
            session['admin_verified'] = True
            user.last_login = datetime.utcnow()
            db.session.commit()
            logger.info(f'Admin login: {email} from {request.remote_addr}')
            return redirect(url_for('admin.dashboard'))

        logger.warning(f'Failed admin login: {email} from {request.remote_addr}')
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
    stats = {
        'users':     User.query.filter(User.role != 'admin').count(),
        'scenarios': Scenario.query.count(),
        'questions': Question.query.filter_by(status='answered').count(),
        'revenue':   db.session.query(db.func.sum(Payment.amount_aed))\
                         .filter_by(status='captured').scalar() or 0,
    }
    categories = Category.query.order_by(Category.order).all()
    recent_q   = Question.query.filter_by(status='answered')\
                     .order_by(Question.answered_at.desc()).limit(10).all()
    return render_template('admin/dashboard.html', stats=stats, categories=categories, recent_q=recent_q)


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

        rights_tenant   = _parse_bullet_list(request.form.get('tenant_rights', ''))
        rights_landlord = _parse_bullet_list(request.form.get('landlord_rights', ''))
        what_to_do      = _parse_bullet_list(request.form.get('what_to_do', ''))
        law_refs        = _parse_bullet_list(request.form.get('law_refs', ''))

        s = Scenario(
            category_id      = int(request.form.get('category_id')),
            slug             = slug,
            title            = request.form.get('title', '').strip(),
            headline         = request.form.get('headline', '').strip(),
            situation        = request.form.get('situation', '').strip(),
            tenant_rights    = rights_tenant,
            landlord_rights  = rights_landlord,
            what_to_do       = what_to_do,
            law_refs         = law_refs,
            keywords         = request.form.get('keywords', '').strip(),
            for_role         = request.form.get('for_role', 'both'),
            show_rera_button = 'show_rera_button' in request.form,
            is_active        = True,
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
        s.slug             = new_slug
        s.category_id      = int(request.form.get('category_id'))
        s.title            = request.form.get('title', '').strip()
        s.headline         = request.form.get('headline', '').strip()
        s.situation        = request.form.get('situation', '').strip()
        s.tenant_rights    = _parse_bullet_list(request.form.get('tenant_rights', ''))
        s.landlord_rights  = _parse_bullet_list(request.form.get('landlord_rights', ''))
        s.what_to_do       = _parse_bullet_list(request.form.get('what_to_do', ''))
        s.law_refs         = _parse_bullet_list(request.form.get('law_refs', ''))
        s.keywords         = request.form.get('keywords', '').strip()
        s.for_role         = request.form.get('for_role', 'both')
        s.show_rera_button = 'show_rera_button' in request.form
        s.updated_at       = datetime.utcnow()
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
            draft['title'] = f'{category.title} — Scenario {i + 1}'

        drafts.append(draft)

    return drafts


# ── USERS ─────────────────────────────────────────────────────────────────────

@admin_bp.route('/users')
@admin_required
def users():
    role_filter = request.args.get('role', '')
    query       = User.query.filter(User.role != 'admin')

    if role_filter in ('tenant', 'landlord'):
        query = query.filter_by(role=role_filter)

    all_users = query.order_by(User.created_at.desc()).all()
    return render_template('admin/users.html', users=all_users, role_filter=role_filter)


@admin_bp.route('/users/<int:id>/toggle', methods=['POST'])
@admin_required
def toggle_user(id):
    user           = User.query.get_or_404(id)
    user.is_active = not user.is_active
    db.session.commit()
    logger.info(f'User {user.email} active={user.is_active} by admin')
    return redirect(url_for('admin.users'))


@admin_bp.route('/users/<int:user_id>/credits', methods=['POST'])
@admin_required
def add_credits(user_id):
    user   = User.query.get_or_404(user_id)
    amount = int(request.form.get('amount') or 0)

    if amount > 0:
        user.credits += amount
        log = CreditLog(
            user_id = user.id,
            action  = 'admin_grant',
            amount  = amount,
            balance = user.credits,
            note    = 'Credits added by admin',
        )
        db.session.add(log)
        db.session.commit()
        flash(f'Added {amount} credits to {user.email}.', 'success')
    return redirect(url_for('admin.users'))


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

@admin_bp.route('/questions')
@admin_required
def questions():
    items = Question.query.filter_by(status='answered')\
                .order_by(Question.answered_at.desc()).limit(200).all()
    return render_template('admin/questions.html', questions=items)


# ── PAYMENTS ──────────────────────────────────────────────────────────────────

@admin_bp.route('/payments')
@admin_required
def payments():
    items = Payment.query.order_by(Payment.id.desc()).limit(200).all()
    return render_template('admin/payments.html', payments=items)


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