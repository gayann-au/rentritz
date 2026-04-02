from datetime import datetime
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy.dialects.postgresql import ARRAY, JSONB

db = SQLAlchemy()

VALID_ROLES = ('tenant', 'landlord', 'lawyer')


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
    answer_viewed   = db.Column(db.Boolean, default=False, nullable=False, server_default='false')
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
    # Valid action values:
    #   signup_bonus · consultation · purchase · admin_grant · admin_deduct · lawyer_unlock
    __tablename__ = 'credit_logs'
    id         = db.Column(db.Integer, primary_key=True)
    user_id    = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    action     = db.Column(db.String(30))
    amount     = db.Column(db.Integer)
    balance    = db.Column(db.Integer)
    ref_id     = db.Column(db.String(100))
    note       = db.Column(db.String(255))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


# ============================================================================
# LAWYER MARKETPLACE MODELS
# ============================================================================

# ---------------------------------------------------------------------------
# MODEL 1 — LawyerSpecialisation
# ---------------------------------------------------------------------------

class LawyerSpecialisation(db.Model):
    """Legal practice areas used to tag lawyer profiles and drive search filters."""

    __tablename__ = 'lawyer_specialisations'

    id          = db.Column(db.Integer, primary_key=True)
    name        = db.Column(db.String(100), unique=True, nullable=False)
    slug        = db.Column(db.String(100), unique=True, nullable=False, index=True)
    description = db.Column(db.String(255), nullable=True)
    icon        = db.Column(db.String(50),  nullable=True)   # same icon naming as categories
    is_active   = db.Column(db.Boolean, default=True, nullable=False)
    order       = db.Column(db.Integer, default=0,    nullable=False)
    created_at  = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<LawyerSpecialisation {self.slug}>'


# ---------------------------------------------------------------------------
# Association table: LawyerProfile <-> LawyerSpecialisation (many-to-many)
# ---------------------------------------------------------------------------

lawyer_profile_specialisations = db.Table(
    'lawyer_profile_specialisations',
    db.Column(
        'lawyer_profile_id',
        db.Integer,
        db.ForeignKey('lawyer_profiles.id', ondelete='CASCADE'),
        primary_key=True,
    ),
    db.Column(
        'specialisation_id',
        db.Integer,
        db.ForeignKey('lawyer_specialisations.id', ondelete='CASCADE'),
        primary_key=True,
    ),
)


# ---------------------------------------------------------------------------
# MODEL 2 — LawyerProfile
# ---------------------------------------------------------------------------

class LawyerProfile(db.Model):
    """
    One-to-one extension of User for lawyers.

    Sensitive contact fields (phone, whatsapp, contact_email, office_address)
    are never exposed until a LawyerBooking with status='contact_unlocked'
    exists for the requesting client.

    Denormalised stats (average_rating, total_reviews, etc.) are updated by
    application logic after each review/booking change — never recalculated
    on read to avoid aggregate queries on every profile page load.
    """

    __tablename__ = 'lawyer_profiles'

    # --- Identity & credentials ---
    id      = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer,
        db.ForeignKey('users.id', ondelete='CASCADE'),
        unique=True, nullable=False, index=True,
    )
    display_name          = db.Column(db.String(150), nullable=True)
    bar_number            = db.Column(db.String(100), nullable=True)
    bar_issuing_authority = db.Column(db.String(200), nullable=True)
    licence_pdf_path      = db.Column(db.String(500), nullable=True)   # via storage abstraction
    photo_path            = db.Column(db.String(500), nullable=True)   # via storage abstraction
    years_experience      = db.Column(db.Integer,     nullable=True)
    firm_name             = db.Column(db.String(200), nullable=True)
    firm_website          = db.Column(db.String(300), nullable=True)

    # --- Practice details ---
    sub_specialisations    = db.Column(ARRAY(db.String), nullable=True)
    # ^ free-text tags e.g. ['rent disputes', 'eviction'] (more granular than specialisations)
    languages              = db.Column(ARRAY(db.String), nullable=True)
    courts_practiced_in    = db.Column(ARRAY(db.String), nullable=True)
    jurisdictions          = db.Column(ARRAY(db.String), nullable=True)
    consultation_modes     = db.Column(ARRAY(db.String), nullable=True)
    # ^ e.g. ['in_person', 'phone', 'video']
    typical_response_hours = db.Column(db.Integer, nullable=True)

    # --- Pricing (all nullable — lawyer fills what applies) ---
    offers_free_first_consultation = db.Column(db.Boolean, default=False)
    free_consultation_minutes      = db.Column(db.Integer,     nullable=True)
    hourly_rate_aed                = db.Column(db.Numeric(10, 2), nullable=True)
    initial_consultation_fee_aed   = db.Column(db.Numeric(10, 2), nullable=True)
    fee_on_case_basis              = db.Column(db.Boolean, default=False)
    fixed_fee_services             = db.Column(JSONB, nullable=True)
    # ^ array of {service: "Contract review", fee_aed: 300}
    pricing_note                   = db.Column(db.Text, nullable=True)
    contact_unlock_credits         = db.Column(db.Integer, default=5, nullable=False)
    # ^ cost in credits to unlock contact; snapshot stored on booking at unlock time

    # --- Contact (private — revealed only after credit unlock) ---
    phone          = db.Column(db.String(30),  nullable=True)
    whatsapp       = db.Column(db.String(30),  nullable=True)
    contact_email  = db.Column(db.String(255), nullable=True)
    office_address = db.Column(db.Text,        nullable=True)
    office_city    = db.Column(db.String(100), nullable=True, default='Dubai')
    office_country = db.Column(db.String(100), nullable=True, default='UAE')

    # --- Bio & presentation ---
    bio            = db.Column(db.Text,        nullable=True)
    education      = db.Column(JSONB,          nullable=True)
    # ^ array of {degree, institution, year}
    certifications = db.Column(JSONB,          nullable=True)
    # ^ array of {name, issuer, year}
    notable_cases  = db.Column(db.Text,        nullable=True)
    linkedin_url   = db.Column(db.String(300), nullable=True)
    website_url    = db.Column(db.String(300), nullable=True)

    # --- Trust & stats (denormalised) ---
    profile_views            = db.Column(db.Integer, default=0, nullable=False)
    total_unlocks            = db.Column(db.Integer, default=0, nullable=False)
    total_completed_bookings = db.Column(db.Integer, default=0, nullable=False)
    average_rating           = db.Column(db.Numeric(3, 2), nullable=True)
    total_reviews            = db.Column(db.Integer, default=0, nullable=False)
    is_featured              = db.Column(db.Boolean, default=False)
    # ^ admin can pin featured lawyers to top of listing

    # --- Verification & admin control ---
    verification_status  = db.Column(db.String(20), default='unverified', nullable=False)
    # ^ Valid: 'unverified', 'pending_review', 'verified', 'rejected'
    rejection_reason     = db.Column(db.Text,     nullable=True)   # shown to lawyer if rejected
    admin_notes          = db.Column(db.Text,     nullable=True)   # internal only
    verified_at          = db.Column(db.DateTime, nullable=True)
    verified_by_admin_id = db.Column(db.Integer,  db.ForeignKey('users.id'), nullable=True)
    is_available         = db.Column(db.Boolean,  default=True,  nullable=False)
    is_active            = db.Column(db.Boolean,  default=True,  nullable=False)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # --- Relationships ---
    user = db.relationship(
        'User',
        foreign_keys=[user_id],
        backref=db.backref('lawyer_profile', uselist=False),
    )
    verified_by = db.relationship('User', foreign_keys=[verified_by_admin_id])
    specialisations = db.relationship(
        'LawyerSpecialisation',
        secondary=lawyer_profile_specialisations,
        lazy='subquery',
        backref=db.backref('lawyers', lazy=True),
    )

    @property
    def photo_url(self):
        from app.storage import get_upload_url
        return get_upload_url(self.photo_path)

    @property
    def licence_url(self):
        from app.storage import get_upload_url
        return get_upload_url(self.licence_pdf_path)

    @property
    def is_profile_complete(self):
        """True when profile has minimum info to be shown to clients."""
        return all([
            self.bio,
            self.phone or self.whatsapp or self.contact_email,
            self.verification_status == 'verified',
        ])

    def __repr__(self):
        return f'<LawyerProfile user_id={self.user_id} status={self.verification_status}>'


# ---------------------------------------------------------------------------
# MODEL 3 — LawyerBooking
# ---------------------------------------------------------------------------

class LawyerBooking(db.Model):
    """
    Records a client unlocking a lawyer's contact details.

    The unique constraint 'uq_booking_client_lawyer' ensures a client pays
    once per lawyer — subsequent access reuses the existing booking record.

    Status lifecycle:
        pending → contact_unlocked → completed
        pending → cancelled
        contact_unlocked → cancelled  (admin-only edge case)
    """

    __tablename__  = 'lawyer_bookings'
    __table_args__ = (
        db.UniqueConstraint('client_id', 'lawyer_profile_id', name='uq_booking_client_lawyer'),
    )

    id                = db.Column(db.Integer, primary_key=True)
    client_id         = db.Column(
        db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'),
        nullable=False, index=True,
    )
    lawyer_profile_id = db.Column(
        db.Integer, db.ForeignKey('lawyer_profiles.id', ondelete='CASCADE'),
        nullable=False, index=True,
    )
    status = db.Column(db.String(20), default='pending', nullable=False)
    # Valid: 'pending', 'contact_unlocked', 'completed', 'cancelled'

    # --- Credit transaction (immutable snapshot at time of unlock) ---
    credits_charged = db.Column(db.Integer, default=0, nullable=False)
    credit_log_id   = db.Column(db.Integer, db.ForeignKey('credit_logs.id'), nullable=True)

    # --- Origin tracking (where the client came from) ---
    source_category_slug = db.Column(db.String(80), nullable=True)
    source_question_id   = db.Column(db.Integer, db.ForeignKey('questions.id'), nullable=True)

    # --- Contact unlock ---
    contact_unlocked_at   = db.Column(db.DateTime, nullable=True)
    contact_method_chosen = db.Column(db.String(20), nullable=True)
    # ^ which contact the client chose: 'phone', 'whatsapp', 'email'
    client_note           = db.Column(db.Text, nullable=True)
    # ^ client writes context when unlocking: "I have an eviction notice"

    # --- Progress tracking ---
    lawyer_responded_at = db.Column(db.DateTime, nullable=True)
    completed_at        = db.Column(db.DateTime, nullable=True)
    cancelled_at        = db.Column(db.DateTime, nullable=True)
    cancelled_by        = db.Column(db.String(20), nullable=True)   # 'client', 'lawyer', 'admin'
    cancellation_reason = db.Column(db.Text, nullable=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # --- Relationships ---
    client = db.relationship(
        'User', foreign_keys=[client_id],
        backref=db.backref('lawyer_bookings', lazy='dynamic'),
    )
    lawyer_profile = db.relationship(
        'LawyerProfile',
        backref=db.backref('bookings', lazy='dynamic'),
    )
    source_question = db.relationship('Question', foreign_keys=[source_question_id])
    credit_log      = db.relationship('CreditLog', foreign_keys=[credit_log_id])

    def __repr__(self):
        return f'<LawyerBooking id={self.id} client={self.client_id} status={self.status}>'


# ---------------------------------------------------------------------------
# MODEL 4 — LawyerReview
# ---------------------------------------------------------------------------

class LawyerReview(db.Model):
    """
    Client review of a lawyer, gated on a completed booking.

    Enforced at application layer:
    - rating 1–5
    - one review per booking (unique FK on booking_id)
    - only clients with booking.status == 'completed' may submit

    lawyer_profile_id is denormalised for fast profile page queries without
    joining through lawyer_bookings.
    """

    __tablename__ = 'lawyer_reviews'

    id                = db.Column(db.Integer, primary_key=True)
    booking_id        = db.Column(
        db.Integer, db.ForeignKey('lawyer_bookings.id', ondelete='CASCADE'),
        unique=True, nullable=False,
    )
    lawyer_profile_id = db.Column(
        db.Integer, db.ForeignKey('lawyer_profiles.id', ondelete='CASCADE'),
        nullable=False, index=True,
    )
    client_id = db.Column(
        db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'),
        nullable=False, index=True,
    )

    # --- Review content ---
    rating           = db.Column(db.Integer,  nullable=False)   # 1–5
    comment          = db.Column(db.Text,     nullable=True)
    would_recommend  = db.Column(db.Boolean,  nullable=True)
    lawyer_reply     = db.Column(db.Text,     nullable=True)
    lawyer_replied_at = db.Column(db.DateTime, nullable=True)

    # --- Admin moderation ---
    is_visible    = db.Column(db.Boolean, default=True, nullable=False)
    hidden_reason = db.Column(db.Text, nullable=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # --- Relationships ---
    booking = db.relationship('LawyerBooking', backref=db.backref('review', uselist=False))
    lawyer_profile = db.relationship(
        'LawyerProfile', foreign_keys=[lawyer_profile_id],
        backref=db.backref('reviews', lazy='dynamic'),
    )
    client = db.relationship(
        'User', foreign_keys=[client_id],
        backref=db.backref('lawyer_reviews', lazy='dynamic'),
    )

    def __repr__(self):
        return f'<LawyerReview booking={self.booking_id} rating={self.rating}>'