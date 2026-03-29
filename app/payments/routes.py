import logging
import os
from decimal import Decimal

import requests as http
from flask import Blueprint, request, jsonify, redirect, url_for, flash, current_app
from flask_login import login_required, current_user

from app import limiter
from app.models import db, Payment, CreditLog

payments_bp = Blueprint('payments', __name__)

# ---------------------------------------------------------------------------
# Payment-specific file logger (writes to payments.log in project root)
# ---------------------------------------------------------------------------
_pay_logger = logging.getLogger('payments')
_pay_logger.setLevel(logging.INFO)
_pay_logger.propagate = False   # don't double-print to root logger

_log_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'payments.log')
_fh = logging.FileHandler(_log_path, encoding='utf-8')
_fh.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(message)s'))
_pay_logger.addHandler(_fh)


def _log_payment(event, user_id, ip, pack_id=None, amount_aed=None, order_id=None, status=None, detail=None):
    """Write one structured line to both the app logger and payments.log."""
    parts = [
        'event=%s' % event,
        'user_id=%s' % user_id,
        'ip=%s' % ip,
    ]
    if pack_id   is not None: parts.append('pack=%s'        % pack_id)
    if amount_aed is not None: parts.append('amount_aed=%s' % amount_aed)
    if order_id  is not None: parts.append('order_id=%s'   % order_id)
    if status    is not None: parts.append('status=%s'      % status)
    if detail    is not None: parts.append('detail=%s'      % detail)
    msg = ' '.join(parts)
    _pay_logger.info(msg)
    current_app.logger.info('[payment] %s' % msg)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ngenius_base_url():
    env = current_app.config.get('NGENIUS_ENV', 'TEST')
    if env == 'TEST':
        return 'https://api-gateway.sandbox.ngenius-payments.com'
    return 'https://api-gateway.ngenius-payments.com'


def _get_bearer_token():
    api_key  = current_app.config.get('NGENIUS_API_KEY')
    base_url = _ngenius_base_url()
    resp = http.post(
        '%s/identity/auth/access-token' % base_url,
        headers={
            'Authorization': 'Basic %s' % api_key,
            'Content-Type': 'application/vnd.ni-identity.v1+json',
        },
        json={},
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()['access_token']


def _ngenius_headers(token):
    return {
        'Authorization': 'Bearer %s' % token,
        'Content-Type': 'application/vnd.ni-payment.v2+json',
        'Accept': 'application/vnd.ni-payment.v2+json',
    }


def _get_pack(pack_id):
    """Return the pack dict if pack_id exactly matches a known pack, else None."""
    if not pack_id or not isinstance(pack_id, str) or len(pack_id) > 50:
        return None
    for p in current_app.config['CREDIT_PACKS']:
        if p['id'] == pack_id:
            return p
    return None


def _validate_pack_amounts(pack):
    """
    Cross-check that price_fils and price_aed in config are internally
    consistent (fils == aed * 100, within 1 fil rounding tolerance).
    Returns True if valid.
    """
    try:
        expected_fils = int(Decimal(str(pack['price_aed'])) * 100)
        return abs(pack['price_fils'] - expected_fils) <= 1
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@payments_bp.route('/create-order', methods=['POST'])
@login_required
@limiter.limit("5 per minute; 10 per hour")
def create_order():
    ip   = request.remote_addr
    data = request.get_json(silent=True) or {}

    pack_id = data.get('pack', '')
    pack    = _get_pack(pack_id)

    # Server-side pack validation
    if not pack:
        _log_payment('order_rejected', current_user.id, ip,
                     pack_id=pack_id, detail='unknown_pack_id')
        return jsonify({'error': 'Invalid pack.'}), 400

    # Server-side amount consistency check
    if not _validate_pack_amounts(pack):
        _log_payment('order_rejected', current_user.id, ip,
                     pack_id=pack_id, detail='amount_mismatch_in_config')
        current_app.logger.error('Pack config amount mismatch for pack_id=%s' % pack_id)
        return jsonify({'error': 'Payment configuration error.'}), 400

    amount_fils = pack['price_fils']
    amount_aed  = pack['price_aed']
    outlet_id   = current_app.config.get('NGENIUS_OUTLET_ID')
    api_key     = current_app.config.get('NGENIUS_API_KEY')

    if not outlet_id or not api_key:
        _log_payment('order_rejected', current_user.id, ip,
                     pack_id=pack_id, amount_aed=amount_aed, detail='gateway_not_configured')
        return jsonify({'error': 'Payment gateway not configured yet.'}), 503

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
        token = _get_bearer_token()
        resp  = http.post(
            '%s/transactions/outlets/%s/orders' % (_ngenius_base_url(), outlet_id),
            json=payload, headers=_ngenius_headers(token), timeout=10,
        )
        resp.raise_for_status()
        order = resp.json()
    except Exception as e:
        _log_payment('order_error', current_user.id, ip,
                     pack_id=pack_id, amount_aed=amount_aed, detail=str(e)[:120])
        current_app.logger.error('nGenius order creation failed: %s' % e)
        return jsonify({'error': 'Payment gateway error. Please try again.'}), 500

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

    _log_payment('order_created', current_user.id, ip,
                 pack_id=pack_id, amount_aed=amount_aed,
                 order_id=order_id, status='pending')

    return jsonify({'redirect_url': pay_url, 'order_id': order_id})


@payments_bp.route('/callback')
@login_required
def callback():
    ip  = request.remote_addr
    ref = request.args.get('ref') or request.args.get('order_ref')

    payment = Payment.query.filter_by(ngenius_order_id=ref, user_id=current_user.id).first()

    if not payment:
        _log_payment('callback_no_record', current_user.id, ip, order_id=ref)
        flash('Payment record not found.', 'error')
        return redirect(url_for('core.credits'))

    # Idempotency guard — already captured, do not credit again
    if payment.status == 'captured':
        _log_payment('callback_duplicate', current_user.id, ip,
                     order_id=ref, status='captured', detail='already_credited_skipped')
        flash('Payment already processed.', 'info')
        return redirect(url_for('core.credits'))

    base_url  = _ngenius_base_url()
    outlet_id = current_app.config.get('NGENIUS_OUTLET_ID')

    try:
        token      = _get_bearer_token()
        resp       = http.get(
            '%s/transactions/outlets/%s/orders/%s' % (base_url, outlet_id, ref),
            headers=_ngenius_headers(token), timeout=10,
        )
        resp.raise_for_status()
        order_data = resp.json()
        status     = order_data.get('status', '').lower()
    except Exception as e:
        _log_payment('callback_verify_error', current_user.id, ip,
                     order_id=ref, detail=str(e)[:120])
        flash('Could not verify payment. Please contact support.', 'error')
        return redirect(url_for('core.credits'))

    _log_payment('callback_received', current_user.id, ip,
                 order_id=ref, amount_aed=str(payment.amount_aed),
                 status=status)

    if status in ('captured', 'authorised'):
        payment.status        = 'captured'
        current_user.credits += payment.credits_purchased
        log = CreditLog(
            user_id = current_user.id,
            action  = 'purchase',
            amount  = payment.credits_purchased,
            balance = current_user.credits,
            ref_id  = str(payment.id),
            note    = 'Purchased %d credits' % payment.credits_purchased,
        )
        db.session.add(log)
        db.session.commit()
        _log_payment('credits_granted', current_user.id, ip,
                     order_id=ref, amount_aed=str(payment.amount_aed),
                     status='captured', detail='credits=%d' % payment.credits_purchased)
        flash('%d credits added to your account.' % payment.credits_purchased, 'success')
    else:
        payment.status = 'failed'
        db.session.commit()
        _log_payment('payment_failed', current_user.id, ip,
                     order_id=ref, amount_aed=str(payment.amount_aed), status=status)
        flash('Payment was not completed.', 'error')

    return redirect(url_for('core.credits'))
