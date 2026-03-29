from flask import Blueprint, jsonify
from flask_login import login_required, current_user

api_bp = Blueprint('api', __name__)


@api_bp.route('/credits/balance')
@login_required
def credits_balance():
    return jsonify({'credits': current_user.credits})
