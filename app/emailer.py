"""
Background email delivery.

Flask-Mail's ``send()`` is synchronous and Flask-Mail exposes no way to pass an
SMTP timeout down to smtplib. A slow or unreachable SMTP server therefore
blocks the calling worker thread until the OS-level TCP timeout expires, and
with Waitress running 8 threads a handful of slow sends can stall the whole
site.

Every send goes through :func:`send_async` instead, which:

  * renders the message body in the caller's request context (so ``url_for``
    with ``_external=True`` still resolves against the real request), then
  * hands delivery to a daemon thread that owns its own app context.

Failures are logged rather than raised - the caller has already committed its
database work and the user should not see an error because Gmail was slow.
``run.py`` sets ``socket.setdefaulttimeout(10)`` so a hung SMTP connection
cannot keep a delivery thread alive indefinitely.
"""

import threading

from flask import current_app


def _deliver(app, subject, recipients, html):
    """Send one message inside its own app context. Never raises."""
    from flask_mail import Message

    from app import mail

    with app.app_context():
        try:
            mail.send(Message(subject=subject, recipients=recipients, html=html))
            app.logger.info(
                'mail sent  subject=%r  to=%s', subject, ','.join(recipients)
            )
        except Exception as e:
            # Logged, never re-raised: the user-facing request is already done.
            app.logger.error(
                'mail FAILED  subject=%r  to=%s  error=%s',
                subject, ','.join(recipients), e, exc_info=True,
            )


def send_async(subject, recipients, html):
    """
    Queue an email for delivery on a background thread.

    Returns immediately. ``recipients`` may be a single address or a list.
    """
    if isinstance(recipients, str):
        recipients = [recipients]
    recipients = [r for r in recipients if r]
    if not recipients:
        return

    app = current_app._get_current_object()

    if app.config.get('MAIL_SUPPRESS_SEND'):
        app.logger.info(
            'mail suppressed  subject=%r  to=%s', subject, ','.join(recipients)
        )
        return

    threading.Thread(
        target=_deliver,
        args=(app, subject, recipients, html),
        daemon=True,
        name='mail-send',
    ).start()
