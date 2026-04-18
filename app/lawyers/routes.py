from datetime import datetime, timedelta
import os

from flask import (
    Blueprint, abort, current_app, flash, jsonify, redirect, render_template,
    request, session, url_for,
)
from flask_login import current_user, login_required, login_user
from flask_mail import Message
from sqlalchemy import text

from app.models import (
    CreditLog, LawyerBooking, LawyerProfile, LawyerReview,
    LawyerSpecialisation, User, db,
)
from app.lawyers.forms import LawyerProfileForm
from app import mail, storage as _storage, limiter

lawyers_bp = Blueprint('lawyers', __name__, url_prefix='/lawyers')


def _split_csv(value):
    """Split a comma-separated string into a cleaned list, or return None."""
    if not value or not value.strip():
        return None
    parts = [p.strip() for p in value.split(',') if p.strip()]
    return parts if parts else None


def _csv_from_array(arr):
    """Convert a DB array back to a comma-separated string for form pre-fill."""
    if not arr:
        return ''
    return ', '.join(arr)


def _populate_specialisation_choices(form):
    """Populate specialisation_ids choices from the DB."""
    specs = LawyerSpecialisation.query.filter_by(is_active=True).order_by(
        LawyerSpecialisation.order
    ).all()
    form.specialisation_ids.choices = [(s.id, s.name) for s in specs]
    return specs


# ─────────────────────────────────────────────────────────────────────────────
# ROUTE 0 - Lawyer login
# ─────────────────────────────────────────────────────────────────────────────

_COOLDOWN_THRESHOLD = 3
_LOCKOUT_THRESHOLD  = 5
_EXTENDED_THRESHOLD = 10
_COOLDOWN_DURATION  = timedelta(seconds=30)
_LOCKOUT_DURATION   = timedelta(minutes=15)
_EXTENDED_DURATION  = timedelta(hours=1)


@lawyers_bp.route('/login', methods=['GET', 'POST'])
@limiter.limit("5 per minute; 20 per hour", methods=["POST"])
def login():
    if current_user.is_authenticated:
        if current_user.role == 'lawyer':
            return redirect(url_for('lawyers.dashboard'))
        return redirect(url_for('core.dashboard'))

    if request.method == 'POST':
        email    = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')

        user = User.query.filter_by(email=email).first()

        if user and user.role in ('tenant', 'landlord'):
            flash('This login is for lawyers only. Please use the client login page.', 'error')
            return render_template('lawyers/login.html')

        if user and user.role != 'lawyer':
            flash('Incorrect email or password.', 'error')
            return render_template('lawyers/login.html')

        # Lockout check
        if user:
            now = datetime.utcnow()
            if user.failed_login_lockout and now < user.failed_login_lockout:
                flash('Incorrect email or password.', 'error')
                return render_template('lawyers/login.html')

        if not user or not user.check_password(password):
            if user:
                user.failed_login_count += 1
                count = user.failed_login_count
                now   = datetime.utcnow()
                if count >= _EXTENDED_THRESHOLD:
                    user.failed_login_lockout = now + _EXTENDED_DURATION
                elif count >= _LOCKOUT_THRESHOLD:
                    user.failed_login_lockout = now + _LOCKOUT_DURATION
                elif count >= _COOLDOWN_THRESHOLD:
                    user.failed_login_lockout = now + _COOLDOWN_DURATION
                db.session.commit()
            flash('Incorrect email or password.', 'error')
            return render_template('lawyers/login.html')

        if not user.is_active:
            flash('Your account has been deactivated. Please contact support.', 'error')
            return render_template('lawyers/login.html')

        if not user.is_verified:
            flash('Please verify your email before logging in.', 'error')
            return render_template('lawyers/login.html')

        user.failed_login_count   = 0
        user.failed_login_lockout = None
        user.last_login           = datetime.utcnow()
        db.session.commit()
        login_user(user)
        return redirect(url_for('lawyers.dashboard'))

    return render_template('lawyers/login.html')


# ─────────────────────────────────────────────────────────────────────────────
# ROUTE 1 - Browse
# ─────────────────────────────────────────────────────────────────────────────

@lawyers_bp.route('/')
def browse():
    if not current_user.is_authenticated:
        flash('Please log in to find and connect with lawyers.', 'info')
        return redirect(url_for('auth.login', next='/lawyers/'))

    if current_user.role == 'lawyer':
        return redirect(url_for('lawyers.dashboard'))

    spec_slug         = request.args.get('specialisation', '').strip()
    city              = request.args.get('city', '').strip()
    language          = request.args.get('language', '').strip()
    search            = request.args.get('search', '').strip()
    min_rate          = request.args.get('min_rate', '', type=str).strip()
    max_rate          = request.args.get('max_rate', '', type=str).strip()
    free_consultation = request.args.get('free_consultation', '')
    page              = request.args.get('page', 1, type=int)

    try:
        min_rate_val = float(min_rate) if min_rate else None
    except ValueError:
        min_rate_val = None
    try:
        max_rate_val = float(max_rate) if max_rate else None
    except ValueError:
        max_rate_val = None

    query = LawyerProfile.query.filter(
        LawyerProfile.is_active == True,
        LawyerProfile.verification_status == 'verified',
    )

    if spec_slug:
        query = query.join(LawyerProfile.specialisations).filter(
            LawyerSpecialisation.slug == spec_slug
        )

    if city:
        query = query.filter(LawyerProfile.office_city.ilike(f'%{city}%'))

    if language:
        query = query.filter(LawyerProfile.languages.contains([language]))

    if min_rate_val is not None:
        query = query.filter(LawyerProfile.hourly_rate_aed >= min_rate_val)

    if max_rate_val is not None:
        query = query.filter(LawyerProfile.hourly_rate_aed <= max_rate_val)

    if free_consultation == '1':
        query = query.filter_by(offers_free_first_consultation=True)

    if search:
        like = f'%{search}%'
        query = query.filter(
            db.or_(
                LawyerProfile.display_name.ilike(like),
                LawyerProfile.firm_name.ilike(like),
            )
        )

    query = query.order_by(
        LawyerProfile.is_featured.desc(),
        LawyerProfile.total_reviews.desc(),
        LawyerProfile.profile_views.asc(),
    )

    lawyers = query.paginate(page=page, per_page=12, error_out=False)
    specialisations = LawyerSpecialisation.query.filter_by(is_active=True).order_by(
        LawyerSpecialisation.order
    ).all()

    return render_template(
        'lawyers/browse.html',
        lawyers=lawyers,
        specialisations=specialisations,
        current_spec=spec_slug,
        current_city=city,
        current_language=language,
        current_search=search,
        current_min_rate=min_rate,
        current_max_rate=max_rate,
        current_free_consultation=free_consultation,
    )


# ─────────────────────────────────────────────────────────────────────────────
# ROUTE 2 - Profile page
# ─────────────────────────────────────────────────────────────────────────────

@lawyers_bp.route('/<int:lawyer_profile_id>')
def profile(lawyer_profile_id):
    # Lawyers viewing their own profile go to their dashboard
    if current_user.is_authenticated and current_user.role == 'lawyer':
        own = LawyerProfile.query.filter_by(user_id=current_user.id).first()
        if own and own.id == lawyer_profile_id:
            return redirect(url_for('lawyers.dashboard'))

    lawyer = LawyerProfile.query.filter_by(
        id=lawyer_profile_id, is_active=True, verification_status='verified'
    ).first_or_404()

    # Increment profile views - skip for admin (own lawyer already redirected)
    if not (current_user.is_authenticated and current_user.role == 'admin'):
        try:
            db.session.execute(
                text('UPDATE lawyer_profiles SET profile_views = profile_views + 1 WHERE id = :id'),
                {'id': lawyer_profile_id},
            )
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            current_app.logger.error('profile_views increment failed: %s', e)

    # Contact unlock state
    contact_unlocked      = False
    unlocked_booking      = None
    viewer_is_other_lawyer = False

    if current_user.is_authenticated:
        if current_user.role == 'admin':
            contact_unlocked = True
        elif current_user.role == 'lawyer':
            viewer_is_other_lawyer = True
        else:
            unlocked_booking = LawyerBooking.query.filter_by(
                client_id=current_user.id,
                lawyer_profile_id=lawyer.id,
            ).filter(
                LawyerBooking.status.in_(['contact_unlocked', 'completed'])
            ).first()
            contact_unlocked = False

    # Review eligibility - only clients who have unlocked
    can_review      = False
    already_reviewed = False
    if current_user.is_authenticated and current_user.role in ('tenant', 'landlord') and unlocked_booking:
        already_reviewed = LawyerReview.query.filter_by(
            client_id=current_user.id,
            lawyer_profile_id=lawyer.id,
        ).first() is not None
        can_review = not already_reviewed

    reviews = LawyerReview.query.filter_by(
        lawyer_profile_id=lawyer.id,
        is_visible=True,
    ).order_by(LawyerReview.created_at.desc()).all()

    user_credits = 0
    if current_user.is_authenticated and current_user.role in ('tenant', 'landlord'):
        user_credits = current_user.available_credits

    return render_template(
        'lawyers/profile.html',
        lawyer=lawyer,
        reviews=reviews,
        contact_unlocked=contact_unlocked,
        unlocked_booking=unlocked_booking,
        viewer_is_other_lawyer=viewer_is_other_lawyer,
        user_credits=user_credits,
        can_review=can_review,
        already_reviewed=already_reviewed,
    )


# ─────────────────────────────────────────────────────────────────────────────
# ROUTE 3 - Unlock contact
# ─────────────────────────────────────────────────────────────────────────────

@lawyers_bp.route('/<int:lawyer_profile_id>/unlock', methods=['POST'])
@login_required
def unlock_contact(lawyer_profile_id):
    lawyer = LawyerProfile.query.filter_by(
        id=lawyer_profile_id,
        is_active=True,
        verification_status='verified',
    ).first_or_404()

    # Only tenants and landlords may unlock contact details
    if current_user.role not in ('tenant', 'landlord'):
        return jsonify({'error': 'forbidden', 'message': 'Only clients can unlock contact details.'}), 403

    if current_user.id == lawyer.user_id:
        return jsonify({'error': 'forbidden', 'message': 'You cannot unlock your own profile.'}), 403

    # Idempotency: prevent double-spend if client already unlocked this lawyer
    existing_booking = LawyerBooking.query.filter_by(
        client_id=current_user.id,
        lawyer_profile_id=lawyer.id,
    ).filter(
        LawyerBooking.status.in_(['contact_unlocked', 'completed'])
    ).first()
    if existing_booking:
        response_data = {'success': True, 'credits_remaining': current_user.credits, 'already_unlocked': True}
        if lawyer.phone:         response_data['phone']    = lawyer.phone
        if lawyer.whatsapp:      response_data['whatsapp'] = lawyer.whatsapp
        if lawyer.contact_email: response_data['email']    = lawyer.contact_email
        return jsonify(response_data)

    cost = lawyer.contact_unlock_credits
    if current_user.available_credits < cost:
        return jsonify({
            'error': 'insufficient_credits',
            'needed': cost,
            'have': current_user.available_credits,
        }), 402

    current_user.credits -= cost

    log = CreditLog(
        user_id=current_user.id,
        action='lawyer_unlock',
        amount=-cost,
        balance=current_user.credits,
        ref_id=f'lawyer_{lawyer.id}',
        note=f'Contact unlock: {lawyer.display_name or lawyer.user.full_name}',
    )
    db.session.add(log)

    source_question_id = request.form.get('source_question_id') or None
    if source_question_id:
        try:
            source_question_id = int(source_question_id)
        except (ValueError, TypeError):
            source_question_id = None

    booking = LawyerBooking(
        client_id=current_user.id,
        lawyer_profile_id=lawyer.id,
        status='contact_unlocked',
        credits_charged=cost,
        contact_unlocked_at=datetime.utcnow(),
        source_category_slug=request.form.get('source_category') or None,
        source_question_id=source_question_id,
        client_note=request.form.get('client_note', '').strip() or None,
        contact_method_chosen=request.form.get('contact_method', 'whatsapp'),
    )
    db.session.add(booking)

    db.session.execute(
        text('UPDATE lawyer_profiles SET total_unlocks = total_unlocks + 1 WHERE id = :id'),
        {'id': lawyer.id},
    )

    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise

    response_data = {'success': True, 'credits_remaining': current_user.credits}
    if lawyer.phone:
        response_data['phone'] = lawyer.phone
    if lawyer.whatsapp:
        response_data['whatsapp'] = lawyer.whatsapp
    if lawyer.contact_email:
        response_data['email'] = lawyer.contact_email

    return jsonify(response_data)


# ─────────────────────────────────────────────────────────────────────────────
# ROUTE 4 - Register as lawyer
# ─────────────────────────────────────────────────────────────────────────────

@lawyers_bp.route('/register', methods=['GET', 'POST'])
def register():
    # ── Role guards (no @login_required so we control the redirect destination) ──
    if not current_user.is_authenticated:
        flash('Please sign in to your lawyer account first.', 'info')
        return redirect(url_for('lawyers.login'))

    if current_user.role in ('tenant', 'landlord'):
        flash('The lawyer portal is for legal professionals only.', 'error')
        return redirect(url_for('core.dashboard'))

    if current_user.role == 'lawyer' and current_user.lawyer_profile:
        return redirect(url_for('lawyers.dashboard'))

    # Only lawyers without an existing profile reach here
    form = LawyerProfileForm()
    _populate_specialisation_choices(form)

    try:
        if form.validate_on_submit():
            photo_path   = None
            licence_path = None

            photo_file = request.files.get('photo')
            if photo_file and photo_file.filename:
                try:
                    photo_path = _storage.save_lawyer_photo(photo_file, current_user.id)
                except (ValueError, OSError) as e:
                    current_app.logger.error('Photo upload failed for user %s: %s', current_user.id, e)
                    flash('Could not save photo. Please try again.', 'error')
                    return render_template('lawyers/register.html', form=form)

            licence_file = request.files.get('licence_pdf')
            if licence_file and licence_file.filename:
                try:
                    licence_path = _storage.save_lawyer_licence(licence_file, current_user.id)
                except (ValueError, OSError) as e:
                    current_app.logger.error('Licence upload failed for user %s: %s', current_user.id, e)
                    flash('Could not save licence file. Please try again.', 'error')
                    return render_template('lawyers/register.html', form=form)

            current_user.role = 'lawyer'

            profile = LawyerProfile(
                user_id=current_user.id,
                display_name=form.display_name.data or None,
                bar_number=form.bar_number.data or None,
                bar_issuing_authority=form.bar_issuing_authority.data or None,
                photo_path=photo_path,
                licence_pdf_path=licence_path,
                bio=form.bio.data,
                years_experience=form.years_experience.data,
                firm_name=form.firm_name.data or None,
                firm_website=form.firm_website.data or None,
                languages=_split_csv(form.languages.data),
                courts_practiced_in=_split_csv(form.courts_practiced_in.data),
                jurisdictions=_split_csv(form.jurisdictions.data),
                consultation_modes=form.consultation_modes.data or None,
                typical_response_hours=form.typical_response_hours.data,
                offers_free_first_consultation=form.offers_free_first_consultation.data,
                free_consultation_minutes=form.free_consultation_minutes.data,
                hourly_rate_aed=form.hourly_rate_aed.data,
                initial_consultation_fee_aed=form.initial_consultation_fee_aed.data,
                fee_on_case_basis=form.fee_on_case_basis.data,
                pricing_note=form.pricing_note.data or None,
                contact_unlock_credits=form.contact_unlock_credits.data or 5,
                phone=form.phone.data or None,
                whatsapp=form.whatsapp.data or None,
                contact_email=form.contact_email.data or None,
                office_address=form.office_address.data or None,
                office_city=form.office_city.data or 'Dubai',
                office_country=form.office_country.data or 'UAE',
                notable_cases=form.notable_cases.data or None,
                linkedin_url=form.linkedin_url.data or None,
                website_url=form.website_url.data or None,
                verification_status='pending_review',
            )
            db.session.add(profile)
            db.session.flush()

            if form.specialisation_ids.data:
                specs = LawyerSpecialisation.query.filter(
                    LawyerSpecialisation.id.in_(form.specialisation_ids.data)
                ).all()
                profile.specialisations = specs

            db.session.commit()

            # Notify admin of new lawyer registration
            admin_email = current_app.config.get('ADMIN_EMAIL') or os.environ.get('ADMIN_EMAIL', '')
            if admin_email:
                try:
                    spec_names = ', '.join(s.name for s in profile.specialisations) or 'None selected'
                    profile_url = url_for('admin.lawyer_detail', profile_id=profile.id, _external=True)
                    msg = Message(
                        subject=f'New lawyer registration pending review - {current_user.full_name}',
                        recipients=[admin_email],
                        html=(
                            f'<p>A new lawyer has registered on Rentritz and requires review.</p>'
                            f'<ul>'
                            f'<li><strong>Name:</strong> {current_user.full_name}</li>'
                            f'<li><strong>Email:</strong> {current_user.email}</li>'
                            f'<li><strong>Bar number:</strong> {profile.bar_number or "Not provided"}</li>'
                            f'<li><strong>Issuing authority:</strong> {profile.bar_issuing_authority or "Not provided"}</li>'
                            f'<li><strong>Specialisations:</strong> {spec_names}</li>'
                            f'</ul>'
                            f'<p><a href="{profile_url}">Review profile in admin panel</a></p>'
                        ),
                    )
                    mail.send(msg)
                except Exception as e:
                    current_app.logger.error(
                        'Failed to send admin notification for new lawyer %s: %s',
                        current_user.email, e,
                    )

            # Confirm submission to the lawyer
            try:
                spec_names = ', '.join(s.name for s in profile.specialisations) or None
                msg = Message(
                    subject='Your Rentritz profile is under review',
                    recipients=[current_user.email],
                    html=render_template(
                        'email/lawyer_submitted.html',
                        name=profile.display_name or current_user.full_name.split()[0],
                        bar_number=profile.bar_number,
                        specialisations=spec_names,
                        dashboard_url=url_for('lawyers.dashboard', _external=True),
                    ),
                )
                mail.send(msg)
            except Exception as e:
                current_app.logger.error(
                    'Failed to send submission confirmation to %s: %s',
                    current_user.email, e,
                )

            flash('Profile submitted. Our team will review and verify it shortly.', 'success')
            return redirect(url_for('lawyers.dashboard'))

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(
            'Register error for user %s: %s', current_user.id, e, exc_info=True,
        )
        flash('Something went wrong saving your profile. Please try again.', 'error')

    return render_template('lawyers/register.html', form=form)


# ─────────────────────────────────────────────────────────────────────────────
# ROUTE 5 - Lawyer dashboard
# ─────────────────────────────────────────────────────────────────────────────

@lawyers_bp.route('/dashboard')
@login_required
def dashboard():
    profile = LawyerProfile.query.filter_by(user_id=current_user.id).first()
    if current_user.role != 'lawyer' or not profile:
        return redirect(url_for('lawyers.register'))

    bookings = LawyerBooking.query.filter_by(
        lawyer_profile_id=profile.id
    ).order_by(LawyerBooking.created_at.desc()).limit(20).all()

    recent_reviews = LawyerReview.query.filter_by(
        lawyer_profile_id=profile.id,
        is_visible=True,
    ).order_by(LawyerReview.created_at.desc()).limit(5).all()

    reviews = LawyerReview.query.filter_by(
        lawyer_profile_id=profile.id,
        is_visible=True,
    ).order_by(LawyerReview.created_at.desc()).all()

    return render_template(
        'lawyers/dashboard.html',
        profile=profile,
        bookings=bookings,
        recent_reviews=recent_reviews,
        reviews=reviews,
    )


# ─────────────────────────────────────────────────────────────────────────────
# ROUTE 6 - Edit profile
# ─────────────────────────────────────────────────────────────────────────────

@lawyers_bp.route('/edit-profile', methods=['GET', 'POST'])
@login_required
def edit_profile():
    if current_user.role != 'lawyer' or not current_user.lawyer_profile:
        return redirect(url_for('lawyers.register'))

    profile = current_user.lawyer_profile
    form    = LawyerProfileForm(obj=profile)
    _populate_specialisation_choices(form)

    if request.method == 'GET':
        # Pre-fill array fields as comma-separated strings
        form.languages.data           = _csv_from_array(profile.languages)
        form.courts_practiced_in.data = _csv_from_array(profile.courts_practiced_in)
        form.jurisdictions.data       = _csv_from_array(profile.jurisdictions)
        form.consultation_modes.data  = profile.consultation_modes or []
        form.specialisation_ids.data  = [s.id for s in profile.specialisations]

    if form.validate_on_submit():
        old_bar_number = profile.bar_number

        # Handle photo upload
        photo_file = request.files.get('photo')
        if photo_file and photo_file.filename:
            try:
                new_path = _storage.save_lawyer_photo(photo_file, current_user.id)
                _storage.delete_file(profile.photo_path)
                profile.photo_path = new_path
            except (ValueError, OSError) as e:
                current_app.logger.error('Photo upload failed for user %s: %s', current_user.id, e)
                flash('Could not save photo. Please try again.', 'error')
                return render_template('lawyers/edit_profile.html', form=form, profile=profile)

        # Handle licence upload
        licence_file = request.files.get('licence_pdf')
        if licence_file and licence_file.filename:
            try:
                new_path = _storage.save_lawyer_licence(licence_file, current_user.id)
                _storage.delete_file(profile.licence_pdf_path)
                profile.licence_pdf_path = new_path
            except (ValueError, OSError) as e:
                current_app.logger.error('Licence upload failed for user %s: %s', current_user.id, e)
                flash('Could not save licence file. Please try again.', 'error')
                return render_template('lawyers/edit_profile.html', form=form, profile=profile)

        profile.display_name          = form.display_name.data or None
        profile.bar_number            = form.bar_number.data or None
        profile.bar_issuing_authority = form.bar_issuing_authority.data or None
        profile.bio                   = form.bio.data
        profile.years_experience      = form.years_experience.data
        profile.firm_name             = form.firm_name.data or None
        profile.firm_website          = form.firm_website.data or None
        profile.languages             = _split_csv(form.languages.data)
        profile.courts_practiced_in   = _split_csv(form.courts_practiced_in.data)
        profile.jurisdictions         = _split_csv(form.jurisdictions.data)
        profile.consultation_modes    = form.consultation_modes.data or None
        profile.typical_response_hours = form.typical_response_hours.data
        profile.offers_free_first_consultation = form.offers_free_first_consultation.data
        profile.free_consultation_minutes = form.free_consultation_minutes.data
        profile.hourly_rate_aed       = form.hourly_rate_aed.data
        profile.initial_consultation_fee_aed = form.initial_consultation_fee_aed.data
        profile.fee_on_case_basis     = form.fee_on_case_basis.data
        profile.pricing_note          = form.pricing_note.data or None
        profile.contact_unlock_credits = form.contact_unlock_credits.data or 5
        profile.phone                 = form.phone.data or None
        profile.whatsapp              = form.whatsapp.data or None
        profile.contact_email         = form.contact_email.data or None
        profile.office_address        = form.office_address.data or None
        profile.office_city           = form.office_city.data or 'Dubai'
        profile.office_country        = form.office_country.data or 'UAE'
        profile.notable_cases         = form.notable_cases.data or None
        profile.linkedin_url          = form.linkedin_url.data or None
        profile.website_url           = form.website_url.data or None
        profile.updated_at            = datetime.utcnow()

        # Bar number change resets to pending review (must be re-verified)
        new_bar_number = profile.bar_number
        if new_bar_number and new_bar_number != old_bar_number:
            if profile.verification_status == 'verified':
                profile.verification_status = 'pending_review'

        if form.specialisation_ids.data:
            specs = LawyerSpecialisation.query.filter(
                LawyerSpecialisation.id.in_(form.specialisation_ids.data)
            ).all()
            profile.specialisations = specs
        else:
            profile.specialisations = []

        db.session.commit()
        flash('Profile updated.', 'success')
        return redirect(url_for('lawyers.dashboard'))

    return render_template('lawyers/edit_profile.html', form=form, profile=profile)


# ─────────────────────────────────────────────────────────────────────────────
# ROUTE 7 - Toggle availability
# ─────────────────────────────────────────────────────────────────────────────

@lawyers_bp.route('/toggle-availability', methods=['POST'])
@login_required
def toggle_availability():
    if current_user.role != 'lawyer' or not current_user.lawyer_profile:
        abort(403)

    profile = current_user.lawyer_profile
    profile.is_available = not profile.is_available
    db.session.commit()

    return jsonify({'is_available': profile.is_available})


# ─────────────────────────────────────────────────────────────────────────────
# ROUTE 8 - Mark booking as responded
# ─────────────────────────────────────────────────────────────────────────────

@lawyers_bp.route('/bookings/<int:booking_id>/respond', methods=['POST'])
@login_required
def booking_respond(booking_id):
    booking = LawyerBooking.query.get_or_404(booking_id)

    if booking.lawyer_profile.user_id != current_user.id:
        abort(403)

    if booking.status != 'contact_unlocked':
        return jsonify({'error': 'invalid_status'}), 400

    booking.lawyer_responded_at = datetime.utcnow()
    db.session.commit()

    return jsonify({
        'success': True,
        'responded_at': booking.lawyer_responded_at.isoformat(),
    })


# ─────────────────────────────────────────────────────────────────────────────
# ROUTE 9 - Mark booking as completed
# ─────────────────────────────────────────────────────────────────────────────

@lawyers_bp.route('/bookings/<int:booking_id>/complete', methods=['POST'])
@login_required
def booking_complete(booking_id):
    booking = LawyerBooking.query.get_or_404(booking_id)

    if booking.lawyer_profile.user_id != current_user.id:
        abort(403)

    if booking.status not in ('contact_unlocked',):
        return jsonify({'error': 'invalid_status'}), 400

    booking.status       = 'completed'
    booking.completed_at = datetime.utcnow()
    booking.lawyer_profile.total_completed_bookings += 1
    db.session.commit()

    return jsonify({'success': True})


# ─────────────────────────────────────────────────────────────────────────────
# ROUTE 10 - Review form (GET) + Submit review (POST)
# ─────────────────────────────────────────────────────────────────────────────

@lawyers_bp.route('/bookings/<int:booking_id>/review', methods=['GET'])
@login_required
def review_form(booking_id):
    booking = LawyerBooking.query.get_or_404(booking_id)

    if booking.client_id != current_user.id:
        abort(403)

    if booking.status != 'completed':
        flash('You can only review a completed booking.', 'error')
        return redirect(url_for('lawyers.browse'))

    existing = LawyerReview.query.filter_by(booking_id=booking_id).first()
    if existing:
        flash('You have already reviewed this booking.', 'info')
        return redirect(url_for('lawyers.profile',
                                lawyer_profile_id=booking.lawyer_profile_id))

    return render_template('lawyers/review.html',
                           booking=booking,
                           lawyer=booking.lawyer_profile)


@lawyers_bp.route('/bookings/<int:booking_id>/review', methods=['POST'])
@login_required
def submit_review(booking_id):
    booking = LawyerBooking.query.get_or_404(booking_id)

    if booking.client_id != current_user.id:
        abort(403)

    if booking.status != 'completed':
        return jsonify({'error': 'invalid_status'}), 400

    existing = LawyerReview.query.filter_by(booking_id=booking_id).first()
    if existing:
        return jsonify({'error': 'already_reviewed'}), 400

    rating = request.form.get('rating', type=int)
    comment = request.form.get('comment', '').strip() or None
    would_recommend = request.form.get('would_recommend') == 'yes'

    if not rating or rating not in range(1, 6):
        flash('Please select a rating.', 'error')
        return redirect(url_for('lawyers.review_form', booking_id=booking_id))

    review = LawyerReview(
        booking_id=booking_id,
        lawyer_profile_id=booking.lawyer_profile_id,
        client_id=current_user.id,
        rating=rating,
        comment=comment,
        would_recommend=would_recommend,
    )
    db.session.add(review)

    profile = booking.lawyer_profile
    all_ratings = db.session.query(
        db.func.avg(LawyerReview.rating),
        db.func.count(LawyerReview.id),
    ).filter(
        LawyerReview.lawyer_profile_id == profile.id,
        LawyerReview.is_visible == True,
    ).one()
    profile.average_rating = round(float(all_ratings[0]), 2) if all_ratings[0] else None
    profile.total_reviews  = all_ratings[1]

    db.session.commit()

    flash('Thank you for your review.', 'success')
    return redirect(url_for('lawyers.profile',
                            lawyer_profile_id=booking.lawyer_profile_id))


# ─────────────────────────────────────────────────────────────────────────────
# ROUTE 11 - Submit review from profile page (POST /lawyers/<id>/review)
# ─────────────────────────────────────────────────────────────────────────────

@lawyers_bp.route('/<int:lawyer_profile_id>/review', methods=['POST'])
@login_required
def submit_lawyer_review(lawyer_profile_id):
    if current_user.role not in ('tenant', 'landlord'):
        flash('Only clients can submit reviews.', 'error')
        return redirect(url_for('lawyers.profile', lawyer_profile_id=lawyer_profile_id))

    lawyer = LawyerProfile.query.filter_by(
        id=lawyer_profile_id, is_active=True
    ).first_or_404()

    booking = LawyerBooking.query.filter_by(
        client_id=current_user.id,
        lawyer_profile_id=lawyer.id,
    ).filter(
        LawyerBooking.status.in_(['contact_unlocked', 'completed'])
    ).first()

    if not booking:
        flash('Unlock this lawyer first to leave a review.', 'error')
        return redirect(url_for('lawyers.profile', lawyer_profile_id=lawyer.id))

    existing = LawyerReview.query.filter_by(
        client_id=current_user.id,
        lawyer_profile_id=lawyer.id,
    ).first()
    if existing:
        flash('You have already reviewed this lawyer.', 'info')
        return redirect(url_for('lawyers.profile', lawyer_profile_id=lawyer_profile_id))

    rating = request.form.get('rating', type=int)
    if not rating or rating not in range(1, 6):
        flash('Please select a rating from 1 to 5.', 'error')
        return redirect(url_for('lawyers.profile', lawyer_profile_id=lawyer_profile_id))

    comment = request.form.get('comment', '').strip()[:1000] or None

    review = LawyerReview(
        lawyer_profile_id=lawyer.id,
        client_id=current_user.id,
        booking_id=booking.id,
        rating=rating,
        comment=comment,
        is_visible=True,
    )
    db.session.add(review)

    # Recalculate denormalised stats
    try:
        db.session.flush()
        all_ratings = db.session.query(
            db.func.avg(LawyerReview.rating),
            db.func.count(LawyerReview.id),
        ).filter(
            LawyerReview.lawyer_profile_id == lawyer.id,
            LawyerReview.is_visible == True,
        ).one()
        lawyer.average_rating = round(float(all_ratings[0]), 2) if all_ratings[0] else None
        lawyer.total_reviews  = all_ratings[1]
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        current_app.logger.error('Review submission failed for lawyer %s: %s', lawyer_profile_id, e)
        flash('Something went wrong. Please try again.', 'error')
        return redirect(url_for('lawyers.profile', lawyer_profile_id=lawyer_profile_id))

    flash('Review submitted. Thank you!', 'success')
    return redirect(url_for('lawyers.profile', lawyer_profile_id=lawyer_profile_id))
