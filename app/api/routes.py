from flask import Blueprint, jsonify, request
from flask_login import login_required, current_user
from app.models import db, Scenario, Question, CreditLog

api_bp = Blueprint('api', __name__)


@api_bp.route('/wizard/submit', methods=['POST'])
@login_required
def wizard_submit():
    data        = request.get_json()
    scenario_id = data.get('scenario_id')
    wizard_path = data.get('wizard_path', [])

    scenario = Scenario.query.filter_by(id=scenario_id, is_active=True).first()
    if not scenario:
        return jsonify({'error': 'Scenario not found.'}), 404

    if not current_user.has_credits:
        return jsonify({'error': 'no_credits', 'message': 'You have no credits remaining.'}), 402

    current_user.deduct_credit()
    current_user.total_asked += 1

    q = Question(
        user_id       = current_user.id,
        scenario_id   = scenario.id,
        category_slug = scenario.category.slug,
        wizard_path   = wizard_path,
        answer_given  = scenario.answer,
        credit_used   = True,
        is_answered   = True,
    )
    db.session.add(q)
    db.session.flush()

    log = CreditLog(
        user_id = current_user.id,
        action  = 'used',
        amount  = -1,
        balance = current_user.credits,
        ref_id  = str(q.id),
        note    = f'Consultation: {scenario.title}'
    )
    db.session.add(log)
    db.session.commit()

    return jsonify({
        'question_id':      q.id,
        'answer':           scenario.answer,
        'credits_remaining': current_user.credits,
    })


@api_bp.route('/credits/balance')
@login_required
def credits_balance():
    return jsonify({'credits': current_user.credits})