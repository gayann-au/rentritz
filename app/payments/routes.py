import requests as http
from flask import Blueprint, request, jsonify, redirect, url_for, flash, current_app
from flask_login import login_required, current_user
from app.models import db, Payment, CreditLog

payments_bp = Blueprint('payments', __name__)


def _ngenius_headers():
    return {
        'Authorization': f'Basic {current_app.config["NGENIUS_API_KEY"]}',
        'Content-Type': 'application/vnd.ni-payment.v2+json',
        'Accept': 'application/vnd.ni-payment.v2+json',
    }


def _get_pack(pack_id):
    for p in current_app.config['CREDIT_PACKS']:
        if p['id'] == pack_id:
            return p
    return None


@payments_bp.route('/create-order', methods=['POST'])
@login_required
def create_order():
    data    = request.get_json()
    pack_id = data.get('pack', '')
    pack    = _get_pack(pack_id)

    if not pack:
        return jsonify({'error': 'Invalid pack.'}), 400

    amount_fils = pack['price_fils']
    amount_aed  = pack['price_aed']
    outlet_id   = current_app.config.get('NGENIUS_OUTLET_ID')
    api_key     = current_app.config.get('NGENIUS_API_KEY')

    if not outlet_id or not api_key:
        return jsonify({'error': 'Payment gateway not configured yet.'}), 503

    env      = current_app.config.get('NGENIUS_ENV', 'TEST')
    base_url = 'https://api-gateway.sandbox.ngenius-payments.com' if env == 'TEST' else 'https://api-gateway.ngenius-payments.com'

    payload = {
        'action': 'SALE',
        'amount': {'currencyCode': 'AED', 'value': amount_fils},
        'merchantAttributes': {
            'redirectUrl': url_for('payments.callback', _external=True),
            'cancelUrl':   url_for('core.credits', _external=True),
        },
        'emailAddress': current_user.email,
    }

    try:
        resp = http.post(
            f'{base_url}/transactions/outlets/{outlet_id}/orders',
            json=payload, headers=_ngenius_headers(), timeout=10,
        )
        resp.raise_for_status()
        order = resp.json()
    except Exception as e:
        return jsonify({'error': str(e)}), 500

    order_id = order.get('reference')
    pay_url  = next(
        (l['href'] for l in order.get('_links', {}).values()
         if isinstance(l, dict) and 'payment' in l.get('href', '')), None
    )

    payment = Payment(
        user_id           = current_user.id,
        payment_type      = 'credit_pack',
        credits_purchased = pack['credits'],
        amount_aed        = amount_aed,
        status            = 'pending',
        ngenius_order_id  = order_id,
    )
    db.session.add(payment)
    db.session.commit()

    return jsonify({'redirect_url': pay_url, 'order_id': order_id})


@payments_bp.route('/callback')
@login_required
def callback():
    ref     = request.args.get('ref') or request.args.get('order_ref')
    payment = Payment.query.filter_by(ngenius_order_id=ref, user_id=current_user.id).first()

    if not payment:
        flash('Payment record not found.', 'error')
        return redirect(url_for('core.credits'))

    env      = current_app.config.get('NGENIUS_ENV', 'TEST')
    base_url = 'https://api-gateway.sandbox.ngenius-payments.com' if env == 'TEST' else 'https://api-gateway.ngenius-payments.com'
    outlet_id = current_app.config.get('NGENIUS_OUTLET_ID')

    try:
        resp       = http.get(
            f'{base_url}/transactions/outlets/{outlet_id}/orders/{ref}',
            headers=_ngenius_headers(), timeout=10
        )
        order_data = resp.json()
        status     = order_data.get('status', '').lower()
    except Exception:
        flash('Could not verify payment. Please contact support.', 'error')
        return redirect(url_for('core.credits'))

    if status in ('captured', 'authorised'):
        payment.status        = 'captured'
        current_user.credits += payment.credits_purchased
        log = CreditLog(
            user_id = current_user.id,
            action  = 'purchase',
            amount  = payment.credits_purchased,
            balance = current_user.credits,
            ref_id  = str(payment.id),
            note    = f'Purchased {payment.credits_purchased} credits',
        )
        db.session.add(log)
        db.session.commit()
        flash(f'{payment.credits_purchased} credits added to your account.', 'success')
    else:
        payment.status = 'failed'
        db.session.commit()
        flash('Payment was not completed.', 'error')

    return redirect(url_for('core.credits'))