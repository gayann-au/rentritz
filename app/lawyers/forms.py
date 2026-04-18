from flask_wtf import FlaskForm
from flask_wtf.file import FileField
from wtforms import (
    BooleanField, DecimalField, IntegerField, SelectMultipleField,
    StringField, SubmitField, TextAreaField,
)
from wtforms.validators import (
    DataRequired, Email, Length, NumberRange, Optional, URL,
)
from wtforms.widgets import CheckboxInput, ListWidget


class MultiCheckboxField(SelectMultipleField):
    """SelectMultipleField rendered as a list of checkboxes."""
    widget = ListWidget(prefix_label=False)
    option_widget = CheckboxInput()


class OptionalDecimalField(DecimalField):
    """DecimalField that treats an empty or whitespace-only submission as None.

    Standard WTForms DecimalField raises "Not a valid decimal value" before
    the Optional() validator runs, so blank fee fields crash with a 500 error.
    This subclass short-circuits that by returning None for blank input.
    """
    def process_formdata(self, valuelist):
        if valuelist and valuelist[0].strip() == '':
            self.data = None
            return
        super().process_formdata(valuelist)


class LawyerProfileForm(FlaskForm):
    # --- Identity ---
    display_name = StringField('Display Name', validators=[Optional(), Length(max=150)])
    bar_number   = StringField('Bar / Licence Number', validators=[Optional(), Length(max=100)])
    bar_issuing_authority = StringField(
        'Issuing Authority',
        validators=[Optional(), Length(max=200)],
        description='e.g. UAE Ministry of Justice, DIFC Authority',
    )

    # --- Bio ---
    bio = TextAreaField(
        'Professional Bio',
        validators=[DataRequired(), Length(min=50, max=2000)],
        description='Minimum 50 characters. Shown publicly on your profile.',
    )

    # --- Experience & firm ---
    years_experience = IntegerField(
        'Years of Experience', validators=[Optional(), NumberRange(0, 70)]
    )
    firm_name    = StringField('Firm Name',    validators=[Optional(), Length(max=200)])
    firm_website = StringField(
        'Firm Website',
        validators=[Optional(), URL(require_tld=True), Length(max=300)],
    )

    # --- Practice details (comma-separated — split to array in route) ---
    languages           = StringField(
        'Languages Spoken',
        validators=[Optional()],
        description='Comma-separated, e.g. English, Arabic, Hindi',
    )
    courts_practiced_in = StringField(
        'Courts Practiced In',
        validators=[Optional()],
        description='e.g. Dubai Courts, DIFC, Rental Dispute Centre',
    )
    jurisdictions = StringField(
        'Jurisdictions',
        validators=[Optional()],
        description='e.g. Dubai, Abu Dhabi, All UAE',
    )
    consultation_modes = MultiCheckboxField(
        'Consultation Modes',
        choices=[('in_person', 'In Person'), ('phone', 'Phone'), ('video', 'Video')],
        validators=[Optional()],
    )
    typical_response_hours = IntegerField(
        'Typical Response Time (hours)',
        validators=[Optional(), NumberRange(1, 72)],
        description='e.g. 4 means "typically responds within 4 hours"',
    )

    # --- Pricing ---
    offers_free_first_consultation = BooleanField('Offer free first consultation')
    free_consultation_minutes = IntegerField(
        'Free consultation duration (minutes)',
        validators=[Optional(), NumberRange(15, 120)],
    )
    hourly_rate_aed = OptionalDecimalField(
        'Hourly Rate (AED)',
        validators=[Optional(), NumberRange(0, 50000)],
        places=2,
    )
    initial_consultation_fee_aed = OptionalDecimalField(
        'Initial Consultation Fee (AED)',
        validators=[Optional(), NumberRange(0, 50000)],
        places=2,
    )
    fee_on_case_basis = BooleanField('Fee discussed after reviewing case')
    pricing_note = TextAreaField(
        'Pricing Note',
        validators=[Optional(), Length(max=500)],
        description='e.g. I offer flexible payment plans for tenancy disputes',
    )
    contact_unlock_credits = IntegerField(
        'Credits clients pay to unlock your contact details',
        validators=[Optional(), NumberRange(min=1, max=20)],
        default=5,
        description='How many credits a client must spend to see your phone/email. Default is 5.',
    )

    # --- Contact (private) ---
    phone         = StringField('Phone',         validators=[Optional(), Length(max=30)])
    whatsapp      = StringField('WhatsApp',       validators=[Optional(), Length(max=30)])
    contact_email = StringField('Contact Email',  validators=[Optional(), Email()])
    office_address = TextAreaField('Office Address', validators=[Optional()])
    office_city    = StringField('City',    validators=[Optional()], default='Dubai')
    office_country = StringField('Country', validators=[Optional()], default='UAE')

    # --- Presentation ---
    notable_cases = TextAreaField(
        'Notable Cases / Work',
        validators=[Optional(), Length(max=1000)],
    )
    linkedin_url = StringField(
        'LinkedIn URL',
        validators=[Optional(), URL(require_tld=True), Length(max=300)],
    )
    website_url = StringField(
        'Personal Website',
        validators=[Optional(), URL(require_tld=True), Length(max=300)],
    )

    # --- Files ---
    photo       = FileField('Profile Photo (jpg/png/webp, max 5 MB)')
    licence_pdf = FileField('Licence / Bar Certificate (PDF, max 10 MB)')

    # --- Specialisations (choices populated dynamically in route) ---
    specialisation_ids = MultiCheckboxField(
        'Practice Areas',
        choices=[],
        coerce=int,
        validators=[Optional()],
    )

    submit = SubmitField('Submit for Verification')

    def validate(self, extra_validators=None):
        rv = super().validate(extra_validators)
        if not self.specialisation_ids.data:
            self.specialisation_ids.errors.append(
                'Select at least one practice area.'
            )
            return False
        if not any([
            self.phone.data and self.phone.data.strip(),
            self.whatsapp.data and self.whatsapp.data.strip(),
            self.contact_email.data and self.contact_email.data.strip(),
        ]):
            self.phone.errors.append(
                'At least one contact method is required '
                '(phone, WhatsApp, or contact email).'
            )
            return False
        return rv
