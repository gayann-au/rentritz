# Rentritz Dubai

A Dubai tenancy law consultation portal that guides tenants and landlords through their legal rights and obligations under UAE rental law.

Users register as either a tenant or a landlord, then navigate a role-aware decision tree to reach their specific legal scenario. Each scenario delivers tailored advice: the rights that apply, the exact steps to take, and the specific articles of Dubai law that govern the situation.

---

## What It Does

- **Role-aware wizard** - tenants and landlords navigate separate branches of the same decision tree, reaching answers relevant to their position
- **Dual-content scenarios** - every scenario holds distinct content for tenants and landlords: headline, situation summary, applicable rights, action steps, and law references
- **Legal categories covered:**
  - Rent Increase
  - Eviction Notice
  - Maintenance & Repairs
  - Security Deposit
  - Subletting
  - Early Termination
  - Lease Renewal
  - Rent Payment Issues
  - Filing a Dispute (RDSC)
  - Landlord Rights
- **Credit system** - users receive 2 free consultations on signup and can purchase credit packs (Starter / Standard / Pro) via nGenius payment gateway
- **Admin panel** - manage categories, scenarios, decision trees, users, and payments at `/manage`
- **PWA-ready** - includes service worker and web manifest for installability

---

## Tech Stack

| Layer | Technology |
|---|---|
| Language | Python 3 |
| Framework | Flask 3.1 |
| Database | PostgreSQL |
| ORM | SQLAlchemy 2.0 (JSONB for decision trees) |
| Auth | Flask-Login + Werkzeug password hashing |
| Forms / CSRF | Flask-WTF |
| Email | Flask-Mail + Gmail SMTP |
| Payments | nGenius (Network International) |
| Templates | Jinja2 |
| Production server | Waitress |
| Environment | python-dotenv |

---

## Local Setup

### Prerequisites

- Python 3.10+
- PostgreSQL running locally
- A SendGrid account (optional in development)
- An nGenius account (optional in development)

### Steps

**1. Clone the repository**

```bash
git clone https://github.com/gayann-au/rentritz.git
cd rentritz
```

**2. Create and activate a virtual environment**

```bash
python -m venv venv

# Windows
venv\Scripts\activate

# macOS / Linux
source venv/bin/activate
```

**3. Install dependencies**

```bash
pip install -r requirements.txt
```

**4. Create a PostgreSQL database**

```sql
CREATE DATABASE rentritz;
```

**5. Configure environment variables**

```bash
cp .env.example .env
```

Open `.env` and fill in all required values (see Environment Variables section below).

**6. Generate a SECRET_KEY**

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

Paste the output as your `SECRET_KEY` in `.env`.

**7. Run the app**

```bash
python run.py
```

The app will start on `http://localhost:5000`. On first run it automatically creates all database tables and seeds the admin user from your `.env` values.

---

## Environment Variables

Copy `.env.example` to `.env` and set every value before running.

| Variable | Required | Description |
|---|---|---|
| `DATABASE_URL` | Yes | PostgreSQL connection string, e.g. `postgresql://user:password@localhost:5432/rentritz` |
| `SECRET_KEY` | Yes | Flask session secret, minimum 32 characters. Generate with `secrets.token_hex(32)` |
| `ADMIN_EMAIL` | Yes | Email address for the admin account created on first startup |
| `ADMIN_PASSWORD` | Yes | Password for the admin account created on first startup |
| `DEBUG` | No | Set to `true` in local development only. Defaults to `false` |
| `NGENIUS_OUTLET_ID` | No | nGenius outlet ID for payment processing |
| `NGENIUS_API_KEY` | No | nGenius API key for payment processing |
| `NGENIUS_ENV` | No | `TEST` or `LIVE`. Defaults to `TEST` |

The app will **refuse to start** if `DATABASE_URL`, `SECRET_KEY`, `ADMIN_EMAIL`, or `ADMIN_PASSWORD` are missing or invalid.

---

## Project Structure

```
rentritz/
├── app/
│   ├── __init__.py          # App factory, blueprints, error handlers
│   ├── models.py            # SQLAlchemy models
│   ├── admin/               # Admin panel routes (/manage)
│   ├── api/                 # Internal API routes (/api/v1)
│   ├── auth/                # Registration and login (/auth)
│   ├── core/                # Wizard, answer, dashboard (/
│   └── payments/            # nGenius payment routes (/pay)
├── config/
│   └── settings.py          # Environment-based configuration
├── templates/
│   ├── admin/               # Admin panel templates
│   ├── auth/                # Login and registration templates
│   ├── core/                # Main app templates (wizard, answer, dashboard)
│   └── errors/              # 403, 404, 500 error pages
├── static/
│   ├── css/                 # Stylesheets
│   ├── js/                  # Client-side scripts
│   ├── manifest.json        # PWA manifest
│   └── sw.js                # Service worker
├── run.py                   # Production entry point (Waitress)
├── requirements.txt
├── .env.example
└── .gitignore
```

---

## Credit Packs

| Pack | Credits | Price (AED) | Per consultation |
|---|---|---|---|
| Starter | 3 | 24.99 | 8.33 |
| Standard | 7 | 48.99 | 6.99 |
| Pro | 15 | 88.99 | 5.93 |

New users receive **2 free credits** on signup.

---

## Legal Basis

All scenario content is based on:

- **Law No. 26 of 2007** - Regulating the relationship between landlords and tenants in Dubai
- **Law No. 33 of 2008** - Amending Law No. 26 of 2007
- **Decree No. 26 of 2013** - Concerning the Rental Disputes Settlement Centre (RDSC)
- **RERA rent increase guidelines** (Decree No. 43 of 2013)
- **DTCM Holiday Home Regulations** (Executive Council Resolution No. 8 of 2012)
