"""
Pharmacy Inventory - License / Subscription Server
----------------------------------------------------
This is a SEPARATE small app from the pharmacy inventory software.
You (the software owner) host this ONE server. Every pharmacy's copy
of the inventory app "checks in" with it to confirm their subscription
is active. This is what lets you:
  - see how many pharmacies are using your software and when they
    last opened it
  - lock a pharmacy out automatically once their subscription expires
    (using THIS server's clock, not the pharmacy's PC clock, so
    changing the date on their computer does not extend their trial)
  - change the subscription price / payment details / an update
    message in ONE place (below, or via the admin panel) and have
    every connected pharmacy see it next time they open the app

Run:
    pip install -r requirements.txt
    python app.py
Then open: http://127.0.0.1:5001/admin  (see ADMIN_USERNAME / ADMIN_PASSWORD below)

See DEPLOY.md for how to put this online for free so pharmacies
outside your own PC can reach it.
"""

from flask import Flask, request, jsonify, render_template, redirect, url_for, session, flash
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timedelta
from functools import wraps
import os
import uuid
import secrets

# ----------------------------------------------------------------------
# DATABASE CONFIGURATION
# ----------------------------------------------------------------------
IS_VERCEL = bool(os.environ.get('VERCEL') or os.environ.get('VERCEL_ENV'))

raw_db_url = os.environ.get('DATABASE_URL')

if raw_db_url:
    # Fix legacy 'postgres://' URI prefix returned by some database hosts
    if raw_db_url.startswith("postgres://"):
        raw_db_url = raw_db_url.replace("postgres://", "postgresql://", 1)
    DB_URI = raw_db_url
    INSTANCE_PATH = '/tmp' if IS_VERCEL else None
elif IS_VERCEL:
    # Ephemeral fallback for Vercel if DATABASE_URL isn't set yet
    DB_URI = 'sqlite:////tmp/license_server.db'
    INSTANCE_PATH = '/tmp'
else:
    # Local development
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    INSTANCE_PATH = os.path.join(BASE_DIR, 'instance')
    os.makedirs(INSTANCE_PATH, exist_ok=True)
    DB_URI = 'sqlite:///' + os.path.join(INSTANCE_PATH, 'license_server.db')

app = Flask(__name__, instance_path=INSTANCE_PATH, instance_relative_config=True) if INSTANCE_PATH else Flask(__name__)

app.config['SQLALCHEMY_DATABASE_URI'] = DB_URI
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.secret_key = os.environ.get('ADMIN_SECRET_KEY', 'change-this-secret-key-too')

db = SQLAlchemy(app)

# ----------------------------------------------------------------------
# ADMIN CREDENTIALS
# ----------------------------------------------------------------------
ADMIN_USERNAME = os.environ.get('ADMIN_USERNAME', 'shehran')
ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD', '123')

TRIAL_DAYS_DEFAULT = 14
OFFLINE_GRACE_DAYS = 3


# ----------------------------------------------------------------------
# MODELS
# ----------------------------------------------------------------------
class Pharmacy(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    license_key = db.Column(db.String(64), unique=True, nullable=False)
    name = db.Column(db.String(150))
    owner_name = db.Column(db.String(150))
    address = db.Column(db.String(250))
    city = db.Column(db.String(100))
    contact = db.Column(db.String(150))
    subscription_expiry = db.Column(db.DateTime, nullable=False)
    last_checkin = db.Column(db.DateTime)
    app_version = db.Column(db.String(30))
    created_on = db.Column(db.DateTime, default=datetime.utcnow)
    disabled = db.Column(db.Boolean, default=False)
    has_paid = db.Column(db.Boolean, default=False)

    @property
    def is_active(self):
        return (not self.disabled) and datetime.utcnow() <= self.subscription_expiry

    @property
    def days_left(self):
        return (self.subscription_expiry - datetime.utcnow()).days

@app.route('/')
def home():
    return redirect(url_for('admin_login'))

class PaymentClaim(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    pharmacy_id = db.Column(db.Integer, db.ForeignKey('pharmacy.id'), nullable=False)
    method = db.Column(db.String(30))
    note = db.Column(db.String(300))
    status = db.Column(db.String(20), default='pending')
    created_on = db.Column(db.DateTime, default=datetime.utcnow)
    resolved_on = db.Column(db.DateTime)
    pharmacy = db.relationship('Pharmacy')


class Setting(db.Model):
    key = db.Column(db.String(50), primary_key=True)
    value = db.Column(db.String(500))


DEFAULT_SETTINGS = {
    'subscription_fee': '2000',
    'billing_period': 'month',
    'plan1_label': '1 Month', 'plan1_days': '30', 'plan1_fee': '2000',
    'plan2_label': '3 Months', 'plan2_days': '90', 'plan2_fee': '5500',
    'plan3_label': '12 Months', 'plan3_days': '365', 'plan3_fee': '20000',
    'bank_details': 'Bank: (add your bank name)\nAccount Title: (add name)\nAccount No: (add number)',
    'jazzcash_number': '(add your JazzCash number)',
    'easypaisa_number': '(add your Easypaisa number)',
    'update_message': '',
}


def get_setting(key):
    row = Setting.query.get(key)
    return row.value if row else DEFAULT_SETTINGS.get(key, '')


def get_plans():
    plans = []
    for n in (1, 2, 3):
        label = get_setting(f'plan{n}_label').strip()
        if not label:
            continue
        try:
            days = int(get_setting(f'plan{n}_days') or 0)
        except ValueError:
            days = 0
        plans.append({
            'label': label,
            'days': days,
            'fee': get_setting(f'plan{n}_fee'),
        })
    if not plans:
        plans.append({
            'label': get_setting('billing_period') or '1 Month',
            'days': 30,
            'fee': get_setting('subscription_fee'),
        })
    return plans


def set_setting(key, value):
    row = Setting.query.get(key)
    if row:
        row.value = value
    else:
        row = Setting(key=key, value=value)
        db.session.add(row)


def ensure_defaults():
    for k, v in DEFAULT_SETTINGS.items():
        if not Setting.query.get(k):
            db.session.add(Setting(key=k, value=v))
    db.session.commit()


def migrate_existing_db():
    from sqlalchemy import text
    try:
        with db.engine.connect() as conn:
            existing_cols = {row[1] for row in conn.execute(text("PRAGMA table_info(pharmacy)"))}
            for col in ('owner_name', 'address', 'city'):
                if col not in existing_cols:
                    conn.execute(text(f"ALTER TABLE pharmacy ADD COLUMN {col} VARCHAR(250)"))
            if 'has_paid' not in existing_cols:
                conn.execute(text("ALTER TABLE pharmacy ADD COLUMN has_paid BOOLEAN DEFAULT 0"))
            conn.commit()
    except Exception:
        pass


# ----------------------------------------------------------------------
# ADMIN AUTH HELPER
# ----------------------------------------------------------------------
def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get('is_admin'):
            return redirect(url_for('admin_login'))
        return view(*args, **kwargs)
    return wrapped


# ----------------------------------------------------------------------
# PUBLIC API
# ----------------------------------------------------------------------
@app.route('/api/pricing', methods=['GET'])
def api_pricing():
    return jsonify({
        'subscription_fee': get_setting('subscription_fee'),
        'billing_period': get_setting('billing_period'),
        'plans': get_plans(),
        'trial_days': TRIAL_DAYS_DEFAULT,
        'bank_details': get_setting('bank_details'),
        'jazzcash_number': get_setting('jazzcash_number'),
        'easypaisa_number': get_setting('easypaisa_number'),
    })


@app.route('/api/register', methods=['POST'])
def api_register():
    data = request.get_json(silent=True) or {}
    name = (data.get('pharmacy_name') or 'Unnamed Pharmacy').strip()[:150]
    owner_name = (data.get('owner_name') or '').strip()[:150]
    address = (data.get('address') or '').strip()[:250]
    city = (data.get('city') or '').strip()[:100]
    contact = (data.get('contact') or '').strip()[:150]

    license_key = uuid.uuid4().hex + secrets.token_hex(4)
    expiry = datetime.utcnow() + timedelta(days=TRIAL_DAYS_DEFAULT)

    pharmacy = Pharmacy(license_key=license_key, name=name, owner_name=owner_name,
                         address=address, city=city, contact=contact,
                         subscription_expiry=expiry, last_checkin=datetime.utcnow())
    db.session.add(pharmacy)
    db.session.commit()

    return jsonify({
        'license_key': license_key,
        'status': 'trial',
        'server_time': datetime.utcnow().isoformat(),
        'subscription_expiry': expiry.isoformat(),
        'trial_days': TRIAL_DAYS_DEFAULT,
        'pharmacy_name': name,
        'address': address,
        'city': city,
        'contact': contact,
    })


@app.route('/api/checkin', methods=['POST'])
def api_checkin():
    data = request.get_json(silent=True) or {}
    license_key = (data.get('license_key') or '').strip()
    app_version = (data.get('app_version') or '').strip()[:30]

    pharmacy = Pharmacy.query.filter_by(license_key=license_key).first()
    if not pharmacy:
        return jsonify({'status': 'unknown_license', 'server_time': datetime.utcnow().isoformat()}), 404

    pharmacy.last_checkin = datetime.utcnow()
    if app_version:
        pharmacy.app_version = app_version
    db.session.commit()

    return jsonify({
        'status': ('active' if pharmacy.has_paid else 'trial') if pharmacy.is_active else 'expired',
        'disabled': pharmacy.disabled,
        'server_time': datetime.utcnow().isoformat(),
        'subscription_expiry': pharmacy.subscription_expiry.isoformat(),
        'days_left': pharmacy.days_left,
        'pharmacy_name': pharmacy.name,
        'owner_name': pharmacy.owner_name,
        'address': pharmacy.address,
        'city': pharmacy.city,
        'contact': pharmacy.contact,
        'subscription_fee': get_setting('subscription_fee'),
        'billing_period': get_setting('billing_period'),
        'plans': get_plans(),
        'bank_details': get_setting('bank_details'),
        'jazzcash_number': get_setting('jazzcash_number'),
        'easypaisa_number': get_setting('easypaisa_number'),
        'update_message': get_setting('update_message'),
    })


@app.route('/api/update_details', methods=['POST'])
def api_update_details():
    data = request.get_json(silent=True) or {}
    license_key = (data.get('license_key') or '').strip()
    pharmacy = Pharmacy.query.filter_by(license_key=license_key).first()
    if not pharmacy:
        return jsonify({'status': 'unknown_license'}), 404

    for field, maxlen in (('name', 150), ('owner_name', 150), ('address', 250),
                          ('city', 100), ('contact', 150)):
        if field in data:
            setattr(pharmacy, field, (data.get(field) or '').strip()[:maxlen])
    db.session.commit()
    return jsonify({
        'status': 'ok',
        'pharmacy_name': pharmacy.name,
        'owner_name': pharmacy.owner_name,
        'address': pharmacy.address,
        'city': pharmacy.city,
        'contact': pharmacy.contact,
    })


@app.route('/api/payment_claim', methods=['POST'])
def api_payment_claim():
    data = request.get_json(silent=True) or {}
    license_key = (data.get('license_key') or '').strip()
    method = (data.get('method') or '').strip()[:30]
    note = (data.get('note') or '').strip()[:300]

    pharmacy = Pharmacy.query.filter_by(license_key=license_key).first()
    if not pharmacy:
        return jsonify({'status': 'unknown_license'}), 404

    claim = PaymentClaim(pharmacy_id=pharmacy.id, method=method, note=note)
    db.session.add(claim)
    db.session.commit()
    return jsonify({'status': 'received'})


# ----------------------------------------------------------------------
# ADMIN PANEL
# ----------------------------------------------------------------------
@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        username = request.form.get('username', '')
        password = request.form.get('password', '')
        if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
            session['is_admin'] = True
            return redirect(url_for('admin_dashboard'))
        flash('Wrong username or password.', 'danger')
    return render_template('admin_login.html')


@app.route('/admin/logout')
def admin_logout():
    session.pop('is_admin', None)
    return redirect(url_for('admin_login'))


@app.route('/admin')
@admin_required
def admin_dashboard():
    pharmacies = Pharmacy.query.order_by(Pharmacy.created_on.desc()).all()
    pending_claims = (PaymentClaim.query
                       .filter_by(status='pending')
                       .order_by(PaymentClaim.created_on.desc())
                       .all())
    active_count = sum(1 for p in pharmacies if p.is_active)
    return render_template('admin_dashboard.html',
                            pharmacies=pharmacies,
                            pending_claims=pending_claims,
                            active_count=active_count,
                            total_count=len(pharmacies),
                            plans=get_plans(),
                            now=datetime.utcnow())


@app.route('/admin/pharmacy/<int:pharmacy_id>/extend', methods=['POST'])
@admin_required
def admin_extend(pharmacy_id):
    pharmacy = Pharmacy.query.get_or_404(pharmacy_id)
    try:
        days = int(request.form.get('days', '30'))
    except ValueError:
        days = 30
    base = max(datetime.utcnow(), pharmacy.subscription_expiry)
    pharmacy.subscription_expiry = base + timedelta(days=days)
    pharmacy.has_paid = True
    db.session.commit()
    flash(f'{pharmacy.name}: extended by {days} days. New expiry: '
          f'{pharmacy.subscription_expiry.strftime("%Y-%m-%d")}.', 'success')
    return redirect(url_for('admin_dashboard'))


@app.route('/admin/pharmacy/<int:pharmacy_id>/toggle_disabled', methods=['POST'])
@admin_required
def admin_toggle_disabled(pharmacy_id):
    pharmacy = Pharmacy.query.get_or_404(pharmacy_id)
    pharmacy.disabled = not pharmacy.disabled
    db.session.commit()
    flash(f'{pharmacy.name}: {"disabled" if pharmacy.disabled else "re-enabled"}.', 'success')
    return redirect(url_for('admin_dashboard'))


@app.route('/admin/pharmacy/<int:pharmacy_id>/unsubscribe', methods=['POST'])
@admin_required
def admin_unsubscribe(pharmacy_id):
    pharmacy = Pharmacy.query.get_or_404(pharmacy_id)
    pharmacy.subscription_expiry = datetime.utcnow()
    pharmacy.disabled = True
    db.session.commit()
    flash(f'{pharmacy.name}: unsubscribed - their app will lock on next check-in.', 'success')
    return redirect(url_for('admin_dashboard'))


@app.route('/admin/pharmacy/add', methods=['GET', 'POST'])
@admin_required
def admin_add_pharmacy():
    if request.method == 'POST':
        name = (request.form.get('pharmacy_name') or 'Unnamed Pharmacy').strip()[:150]
        owner_name = (request.form.get('owner_name') or '').strip()[:150]
        address = (request.form.get('address') or '').strip()[:250]
        city = (request.form.get('city') or '').strip()[:100]
        contact = (request.form.get('contact') or '').strip()[:150]
        try:
            days = int(request.form.get('days', str(TRIAL_DAYS_DEFAULT)))
        except ValueError:
            days = TRIAL_DAYS_DEFAULT
        mark_paid = bool(request.form.get('mark_paid'))

        license_key = uuid.uuid4().hex + secrets.token_hex(4)
        pharmacy = Pharmacy(license_key=license_key, name=name, owner_name=owner_name,
                             address=address, city=city, contact=contact,
                             subscription_expiry=datetime.utcnow() + timedelta(days=days),
                             last_checkin=None, has_paid=mark_paid)
        db.session.add(pharmacy)
        db.session.commit()
        flash(f'{name} added. Give them this license key to enter on their app\'s '
              f'setup screen: {license_key}', 'success')
        return redirect(url_for('admin_dashboard'))

    return render_template('admin_add_pharmacy.html', default_days=TRIAL_DAYS_DEFAULT)


@app.route('/admin/claim/<int:claim_id>/<action>', methods=['POST'])
@admin_required
def admin_resolve_claim(claim_id, action):
    claim = PaymentClaim.query.get_or_404(claim_id)
    if action == 'confirm':
        base = max(datetime.utcnow(), claim.pharmacy.subscription_expiry)
        claim.pharmacy.subscription_expiry = base + timedelta(days=30)
        claim.pharmacy.has_paid = True
        claim.status = 'confirmed'
        flash(f'Payment confirmed for {claim.pharmacy.name} - extended 30 days.', 'success')
    else:
        claim.status = 'dismissed'
        flash('Claim dismissed.', 'secondary')
    claim.resolved_on = datetime.utcnow()
    db.session.commit()
    return redirect(url_for('admin_dashboard'))


@app.route('/admin/settings', methods=['GET', 'POST'])
@admin_required
def admin_settings():
    if request.method == 'POST':
        for key in DEFAULT_SETTINGS:
            set_setting(key, request.form.get(key, ''))
        db.session.commit()
        flash('Settings saved. Every pharmacy will see the change on their next check-in.', 'success')
        return redirect(url_for('admin_settings'))
    values = {k: get_setting(k) for k in DEFAULT_SETTINGS}
    return render_template('admin_settings.html', values=values)


with app.app_context():
    db.create_all()
    ensure_defaults()
    migrate_existing_db()

if __name__ == '__main__':
    app.run(port=5001, debug=False)
                                        
