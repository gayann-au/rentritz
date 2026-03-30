from datetime import datetime
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy.dialects.postgresql import JSONB

db = SQLAlchemy()

VALID_ROLES = ('tenant', 'landlord')


class User(UserMixin, db.Model):
    __tablename__ = 'users'
    id            = db.Column(db.Integer, primary_key=True)
    full_name     = db.Column(db.String(120), nullable=False)
    email         = db.Column(db.String(255), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=True)
    role          = db.Column(db.String(20), nullable=False)
    is_active     = db.Column(db.Boolean, default=True)
    is_verified   = db.Column(db.Boolean, default=False)
    credits       = db.Column(db.Integer, default=0)
    total_asked   = db.Column(db.Integer, default=0)
    created_at    = db.Column(db.DateTime, default=datetime.utcnow)
    last_login              = db.Column(db.DateTime)
    reset_token             = db.Column(db.String(100), nullable=True, index=True)
    reset_token_expiry      = db.Column(db.DateTime, nullable=True)
    failed_login_count      = db.Column(db.Integer, default=0, nullable=False)
    failed_login_lockout    = db.Column(db.DateTime, nullable=True)
    has_seen_onboarding     = db.Column(db.Boolean, default=False, nullable=False)

    questions    = db.relationship('Question',          backref='user', lazy='dynamic')
    payments     = db.relationship('Payment',           backref='user', lazy='dynamic')
    credit_logs  = db.relationship('CreditLog',         backref='user', lazy='dynamic')
    reservations = db.relationship('CreditReservation', backref='user', lazy='dynamic')

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        if not self.password_hash:
            return False
        return check_password_hash(self.password_hash, password)

    @property
    def available_credits(self):
        held = CreditReservation.query.filter_by(user_id=self.id, status='held').count()
        return self.credits - held

    @property
    def has_credits(self):
        return self.available_credits > 0

    def reserve_credit(self):
        if self.available_credits < 1:
            return None
        reservation = CreditReservation(user_id=self.id, status='held')
        db.session.add(reservation)
        db.session.flush()
        return reservation

    def confirm_credit(self, reservation_id):
        reservation = CreditReservation.query.filter_by(
            id=reservation_id, user_id=self.id, status='held'
        ).first()
        if not reservation:
            return False
        reservation.status       = 'confirmed'
        reservation.confirmed_at = datetime.utcnow()
        self.credits    -= 1
        self.total_asked += 1
        return True

    def release_credit(self, reservation_id):
        reservation = CreditReservation.query.filter_by(
            id=reservation_id, user_id=self.id, status='held'
        ).first()
        if not reservation:
            return False
        reservation.status = 'released'
        return True


class CreditReservation(db.Model):
    __tablename__ = 'credit_reservations'
    id           = db.Column(db.Integer, primary_key=True)
    user_id      = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    question_id  = db.Column(db.Integer, db.ForeignKey('questions.id'), nullable=True)
    status       = db.Column(db.String(20), default='held')
    created_at   = db.Column(db.DateTime, default=datetime.utcnow)
    confirmed_at = db.Column(db.DateTime, nullable=True)


class Category(db.Model):
    __tablename__ = 'categories'
    id          = db.Column(db.Integer, primary_key=True)
    slug        = db.Column(db.String(80), unique=True, nullable=False, index=True)
    title       = db.Column(db.String(120), nullable=False)
    description = db.Column(db.Text)
    icon        = db.Column(db.String(50))
    for_role    = db.Column(db.String(20), default='both')
    order       = db.Column(db.Integer, default=0)
    is_active   = db.Column(db.Boolean, default=True)
    tree_json   = db.Column(JSONB, nullable=True)
    created_at  = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at  = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    scenarios   = db.relationship('Scenario', backref='category', lazy='dynamic')

    @property
    def has_tree(self):
        return self.tree_json is not None and bool(self.tree_json)

    @property
    def scenario_count(self):
        return self.scenarios.filter_by(is_active=True).count()


class Scenario(db.Model):
    __tablename__ = 'scenarios'
    id              = db.Column(db.Integer, primary_key=True)
    category_id     = db.Column(db.Integer, db.ForeignKey('categories.id'), nullable=False, index=True)
    slug            = db.Column(db.String(150), unique=True, nullable=False, index=True)
    title           = db.Column(db.String(200), nullable=False)
    headline            = db.Column(db.String(300), nullable=True)
    situation           = db.Column(db.Text, nullable=True)
    landlord_headline   = db.Column(db.String(300), nullable=True)
    landlord_situation  = db.Column(db.Text, nullable=True)
    tenant_rights   = db.Column(JSONB, nullable=True)
    landlord_rights = db.Column(JSONB, nullable=True)
    what_to_do      = db.Column(JSONB, nullable=True)
    landlord_what_to_do = db.Column(JSONB, nullable=True)
    law_refs        = db.Column(JSONB, nullable=True)
    keywords        = db.Column(db.Text)
    for_role        = db.Column(db.String(20), default='both')
    is_active         = db.Column(db.Boolean, default=True)
    show_rera_button  = db.Column(db.Boolean, default=False)
    created_at      = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at      = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    questions = db.relationship('Question', backref='scenario', lazy='dynamic')

    @property
    def is_complete(self):
        return bool(self.headline and self.situation and self.what_to_do)


class Question(db.Model):
    __tablename__ = 'questions'
    id            = db.Column(db.Integer, primary_key=True)
    user_id       = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    scenario_id   = db.Column(db.Integer, db.ForeignKey('scenarios.id'), nullable=True)
    category_slug = db.Column(db.String(80), nullable=False)
    wizard_path   = db.Column(JSONB)
    status        = db.Column(db.String(20), default='pending')
    credit_used   = db.Column(db.Boolean, default=False)
    has_been_viewed = db.Column(db.Boolean, default=False, nullable=False, server_default='false')
    created_at    = db.Column(db.DateTime, default=datetime.utcnow)
    answered_at   = db.Column(db.DateTime, nullable=True)

    reservation = db.relationship(
        'CreditReservation', backref='question', uselist=False,
        primaryjoin='Question.id == foreign(CreditReservation.question_id)'
    )
    payment = db.relationship('Payment', backref='question', uselist=False)

    @property
    def is_answered(self):
        return self.status == 'answered'


class Payment(db.Model):
    __tablename__ = 'payments'
    id                = db.Column(db.Integer, primary_key=True)
    user_id           = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    question_id       = db.Column(db.Integer, db.ForeignKey('questions.id'), nullable=True)
    payment_type      = db.Column(db.String(20), default='credit_pack')
    credits_purchased = db.Column(db.Integer, default=0)
    amount_aed        = db.Column(db.Numeric(10, 2), nullable=False)
    currency          = db.Column(db.String(3), default='AED')
    status            = db.Column(db.String(30), default='pending')
    ngenius_order_id  = db.Column(db.String(255))
    ngenius_ref       = db.Column(db.String(255))
    created_at        = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at        = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class CreditLog(db.Model):
    __tablename__ = 'credit_logs'
    id         = db.Column(db.Integer, primary_key=True)
    user_id    = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    action     = db.Column(db.String(30))
    amount     = db.Column(db.Integer)
    balance    = db.Column(db.Integer)
    ref_id     = db.Column(db.String(100))
    note       = db.Column(db.String(255))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)