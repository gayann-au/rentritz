from datetime import datetime
from flask import Blueprint, render_template, redirect, url_for, flash, request, session, abort, current_app, make_response, jsonify
from flask_login import login_required, current_user
from sqlalchemy import text
from app import limiter
from app.models import db, Category, Scenario, Question, CreditLog, LawyerBooking

core_bp = Blueprint('core', __name__)

CATEGORY_TO_SPECIALISATION = {
    'rent_increase':   'tenancy',
    'eviction':        'tenancy',
    'maintenance':     'tenancy',
    'deposit':         'tenancy',
    'dispute':         'tenancy',
    'landlord_rights': 'tenancy',
}


def _get_node_at_path(tree, selections):
    node = tree
    for selection in selections:
        matched = None
        for option in node.get('options', []):
            if option['label'] == selection:
                matched = option
                break
        if not matched or 'next' not in matched:
            return None
        node = matched['next']
    return node


def _clear_wizard_session():
    session.pop('wizard', None)


def _release_reservation_on_abandon():
    wizard = session.get('wizard')
    if not wizard:
        return
    reservation_id = wizard.get('reservation_id')
    question_id    = wizard.get('question_id')
    if reservation_id:
        current_user.release_credit(reservation_id)
    if question_id:
        q = Question.query.filter_by(id=question_id, user_id=current_user.id).first()
        if q and q.status == 'pending':
            q.status = 'failed'
    db.session.commit()
    _clear_wizard_session()


@core_bp.route('/')
def index():
    if current_user.is_authenticated:
        return redirect(url_for('core.dashboard'))
    return render_template('core/landing.html')


@core_bp.route('/dashboard')
@login_required
def dashboard():
    if current_user.role == 'lawyer':
        response = redirect(url_for('lawyers.dashboard'), 303)
        response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
        response.headers['Pragma'] = 'no-cache'
        return response
    if current_user.role == 'admin':
        return redirect(url_for('admin.dashboard'))
    categories = Category.query.filter_by(is_active=True).order_by(Category.order).all()
    visible    = [c for c in categories if c.for_role in ('both', current_user.role)]
    recent     = Question.query.filter_by(user_id=current_user.id)\
                    .order_by(Question.created_at.desc()).limit(5).all()
    question_count = Question.query.filter_by(user_id=current_user.id).count()
    try:
        credit_history = CreditLog.query.filter_by(
            user_id=current_user.id,
        ).order_by(CreditLog.created_at.desc()).limit(10).all()
    except Exception as e:
        current_app.logger.error(f'credit_history query failed: {e}')
        credit_history = []
    return render_template(
        'core/dashboard.html',
        categories=visible,
        recent=recent,
        has_seen_onboarding=current_user.has_seen_onboarding,
        credit_history=credit_history,
        question_count=question_count,
    )


@core_bp.route('/onboarding/complete', methods=['POST'])
@login_required
@limiter.limit("3 per hour")
def onboarding_complete():
    current_user.has_seen_onboarding = True
    db.session.commit()
    return jsonify({'ok': True})


@core_bp.route('/consult/<category_slug>')
@login_required
def consult(category_slug):
    category = Category.query.filter_by(slug=category_slug, is_active=True).first_or_404()

    if category.for_role != 'both' and category.for_role != current_user.role:
        abort(403)

    if not category.has_tree:
        flash('This topic is being prepared. Please check back soon.', 'error')
        return redirect(url_for('core.dashboard'))

    if current_user.available_credits < 1:
        flash('You need credits to start a consultation.', 'error')
        return redirect(url_for('core.credits'))

    if session.get('wizard', {}).get('category_slug') == category_slug:
        _release_reservation_on_abandon()

    reservation = current_user.reserve_credit()
    if not reservation:
        flash('Unable to reserve credit. Please try again.', 'error')
        return redirect(url_for('core.dashboard'))

    question = Question(
        user_id       = current_user.id,
        category_slug = category_slug,
        status        = 'pending',
        wizard_path   = [],
    )
    db.session.add(question)
    db.session.flush()

    reservation.question_id = question.id
    db.session.commit()

    session['wizard'] = {
        'category_slug':  category_slug,
        'reservation_id': reservation.id,
        'question_id':    question.id,
        'selections':     [],
    }

    return render_template(
        'core/wizard.html',
        category=category,
        node=category.tree_json,
        path=[],
        step=1,
    )


@core_bp.route('/consult/<category_slug>/step', methods=['POST'])
@login_required
def wizard_step(category_slug):
    wizard = session.get('wizard')

    if not wizard or wizard.get('category_slug') != category_slug:
        flash('Session expired. Please start again.', 'error')
        return redirect(url_for('core.consult', category_slug=category_slug))

    category = Category.query.filter_by(slug=category_slug, is_active=True).first_or_404()
    selected = request.form.get('answer', '').strip()

    current_node = _get_node_at_path(category.tree_json, wizard['selections'])

    if not current_node:
        flash('Session error. Please start again.', 'error')
        _release_reservation_on_abandon()
        return redirect(url_for('core.consult', category_slug=category_slug))

    if not selected:
        flash('Please select an option to continue.', 'error')
        return render_template(
            'core/wizard.html',
            category=category,
            node=current_node,
            path=_build_path(category.tree_json, wizard['selections']),
            step=len(wizard['selections']) + 1,
        )

    matched_option = None
    for option in current_node.get('options', []):
        if option['label'] == selected:
            matched_option = option
            break

    if not matched_option:
        flash('Invalid selection. Please try again.', 'error')
        return render_template(
            'core/wizard.html',
            category=category,
            node=current_node,
            path=_build_path(category.tree_json, wizard['selections']),
            step=len(wizard['selections']) + 1,
        )

    wizard['selections'].append(selected)
    session['wizard'] = wizard

    if 'scenario' in matched_option:
        return _deliver_answer(wizard, matched_option['scenario'], category)

    if 'next' in matched_option:
        next_node = matched_option['next']
        return render_template(
            'core/wizard.html',
            category=category,
            node=next_node,
            path=_build_path(category.tree_json, wizard['selections']),
            step=len(wizard['selections']) + 1,
        )

    flash('Something went wrong. Your credit has been returned.', 'error')
    _release_reservation_on_abandon()
    return redirect(url_for('core.consult', category_slug=category_slug))


def _build_path(tree, selections):
    path = []
    node = tree
    for selection in selections:
        path.append({
            'question': node.get('question', ''),
            'answer':   selection,
        })
        for option in node.get('options', []):
            if option['label'] == selection:
                if 'next' in option:
                    node = option['next']
                break
    return path


def _deliver_answer(wizard, scenario_slug, category):
    scenario = Scenario.query.filter_by(slug=scenario_slug, is_active=True).first()

    if not scenario or not scenario.is_complete:
        current_user.release_credit(wizard['reservation_id'])
        q = Question.query.get(wizard['question_id'])
        if q:
            q.status = 'failed'
        db.session.commit()
        _clear_wizard_session()
        flash('We could not match your situation. Your credit has been returned.', 'error')
        return redirect(url_for('core.dashboard'))

    q             = Question.query.get(wizard['question_id'])
    q.scenario_id = scenario.id
    q.wizard_path = _build_path(category.tree_json, wizard['selections'])
    q.status      = 'answered'
    q.credit_used = True
    q.answered_at = datetime.utcnow()

    current_user.confirm_credit(wizard['reservation_id'])

    log = CreditLog(
        user_id = current_user.id,
        action  = 'consultation',
        amount  = -1,
        balance = current_user.credits,
        ref_id  = str(q.id),
        note    = f'Consultation: {category.title}',
    )
    db.session.add(log)
    db.session.commit()
    _clear_wizard_session()
    return redirect(url_for('core.answer', question_id=q.id))


@core_bp.route('/answer/<int:question_id>')
@login_required
def answer(question_id):
    q = Question.query.filter_by(id=question_id, user_id=current_user.id).first_or_404()
    if not q.is_answered:
        abort(403)

    # Read has_been_viewed directly from DB (bypasses any stale ORM cache)
    with db.engine.connect() as conn:
        row = conn.execute(
            text('SELECT has_been_viewed FROM questions WHERE id = :id'),
            {'id': question_id}
        ).fetchone()
    already_viewed = row[0] if row else False

    if already_viewed:
        flash('This consultation has already been viewed.', 'info')
        return redirect(url_for('core.history'))

    # Use a direct engine connection so the write persists regardless of
    # ORM session state (important under Waitress multi-thread environment).
    with db.engine.connect() as conn:
        conn.execute(
            text('UPDATE questions SET has_been_viewed = TRUE, answer_viewed = TRUE WHERE id = :id'),
            {'id': question_id}
        )
        conn.commit()
    db.session.expire(q)   # force ORM to re-read from DB for any lazy loads below

    scenario = q.scenario
    category = Category.query.filter_by(slug=q.category_slug).first()

    from app.models import LawyerProfile

    lawyer_count = LawyerProfile.query.filter_by(
        is_active=True,
        is_available=True,
        verification_status='verified'
    ).count()

    specialisation_hint = CATEGORY_TO_SPECIALISATION.get(
        q.category_slug, ''
    )

    resp = make_response(render_template(
        'core/answer.html',
        question=q,
        scenario=scenario,
        category=category,
        lawyer_count=lawyer_count,
        specialisation_hint=specialisation_hint,
    ))
    resp.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    resp.headers['Pragma'] = 'no-cache'
    return resp


@core_bp.route('/history')
@login_required
def history():
    questions = Question.query.filter_by(user_id=current_user.id)\
                    .order_by(Question.created_at.desc()).all()

    from app.models import LawyerBooking, LawyerReview

    completed = LawyerBooking.query.filter_by(
        client_id=current_user.id,
        status='completed'
    ).all()
    reviewed_ids = {
        r.booking_id for r in LawyerReview.query.filter_by(
            client_id=current_user.id
        ).all()
    }
    reviewable_bookings = [b for b in completed if b.id not in reviewed_ids]

    resp = make_response(render_template(
        'core/history.html',
        questions=questions,
        reviewable_bookings=reviewable_bookings,
    ))
    resp.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    resp.headers['Pragma'] = 'no-cache'
    return resp


@core_bp.route('/terms')
def terms():
    return render_template('core/terms.html')


@core_bp.route('/privacy')
def privacy():
    return render_template('core/privacy.html')


@core_bp.route('/credits')
@login_required
def credits():
    from datetime import timedelta
    page     = request.args.get('page', 1, type=int)
    per_page = 20
    logs_q   = CreditLog.query.filter_by(user_id=current_user.id)\
                   .order_by(CreditLog.created_at.desc())
    total    = logs_q.count()
    logs     = logs_q.offset((page - 1) * per_page).limit(per_page).all()
    for log in logs:
        log.created_at = log.created_at + timedelta(hours=4)
    total_pages = (total + per_page - 1) // per_page
    packs       = current_app.config['CREDIT_PACKS']
    return render_template('core/credits.html',
        logs=logs, packs=packs,
        page=page, total_pages=total_pages, total=total)

@core_bp.route('/for-lawyers')
def for_lawyers():
    return render_template('core/for_lawyers.html')
