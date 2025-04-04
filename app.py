from flask import Flask, render_template, request, redirect, url_for, flash, send_file, make_response
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from datetime import datetime
from io import BytesIO
from xhtml2pdf import pisa
import csv
import os
import json

# App config
app = Flask(__name__)
app.config['SECRET_KEY'] = 'your_secret_key'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///billing.db'
app.config['UPLOAD_FOLDER'] = 'static/uploads'
db = SQLAlchemy(app)

# Login config
login_manager = LoginManager(app)
login_manager.login_view = 'login'

# Settings file path
SETTINGS_FILE = 'settings.json'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Models
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(150), unique=True, nullable=False)
    password_hash = db.Column(db.String(150), nullable=False)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class Customer(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    contact = db.Column(db.String(100))
    due_date = db.Column(db.Date)
    status = db.Column(db.String(20))

class Transaction(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    customer_id = db.Column(db.Integer, db.ForeignKey('customer.id'), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    items = db.Column(db.String(200))
    unit_type = db.Column(db.String(50))
    discount_percent = db.Column(db.Float)
    discount_flat = db.Column(db.Float)
    gst_type = db.Column(db.String(10))
    paid = db.Column(db.Float)
    transaction_date = db.Column(db.Date, default=datetime.utcnow)
    customer = db.relationship('Customer')

# Helper functions
def load_settings():
    if os.path.exists(SETTINGS_FILE):
        with open(SETTINGS_FILE, 'r') as f:
            return json.load(f)
    return {}

def save_settings(settings):
    with open(SETTINGS_FILE, 'w') as f:
        json.dump(settings, f)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.context_processor
def inject_settings():
    return dict(load_settings=load_settings)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# Routes
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        user = User.query.filter_by(username=request.form['username']).first()
        if user and user.check_password(request.form['password']):
            login_user(user)
            return redirect(url_for('home'))
        flash('❌ Invalid credentials', 'danger')
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route('/')
@login_required
def home():
    total_revenue = db.session.query(db.func.sum(Transaction.amount)).scalar() or 0
    total_paid = db.session.query(db.func.sum(Transaction.paid)).scalar() or 0
    pending = total_revenue - total_paid
    upcoming_dues = Customer.query.filter(Customer.due_date >= datetime.today()).order_by(Customer.due_date).limit(5).all()
    overdue_customers = Customer.query.filter(Customer.due_date < datetime.today()).all()
    return render_template('home.html', total=total_revenue, paid=total_paid, pending=pending,
                           upcoming_dues=upcoming_dues, overdue_customers=overdue_customers)

@app.route('/customers', methods=['GET', 'POST'])
@app.route('/customers/<int:customer_id>', methods=['GET', 'POST'])
@login_required
def manage_customers(customer_id=None):
    customer_to_edit = None
    if request.method == 'POST':
        name = request.form['name']
        contact = request.form['contact']
        due_date_str = request.form['due_date']
        status = request.form['status']
        due_date = datetime.strptime(due_date_str, '%Y-%m-%d').date() if due_date_str else None

        if customer_id:
            customer = Customer.query.get_or_404(customer_id)
            customer.name = name
            customer.contact = contact
            customer.due_date = due_date
            customer.status = status
        else:
            customer = Customer(name=name, contact=contact, due_date=due_date, status=status)
            db.session.add(customer)

        db.session.commit()
        flash('✅ Customer saved', 'success')
        return redirect(url_for('manage_customers'))

    if customer_id:
        customer_to_edit = Customer.query.get_or_404(customer_id)

    customers = Customer.query.all()
    return render_template('customers.html', customers=customers, customer_to_edit=customer_to_edit)

@app.route('/customers/delete/<int:customer_id>')
@login_required
def delete_customer(customer_id):
    customer = Customer.query.get_or_404(customer_id)
    db.session.delete(customer)
    db.session.commit()
    flash('✅ Customer deleted', 'success')
    return redirect(url_for('manage_customers'))

@app.route('/transactions', methods=['GET', 'POST'])
@login_required
def transactions():
    customers = Customer.query.all()
    if request.method == 'POST':
        transaction = Transaction(
            customer_id=request.form['customer_id'],
            amount=float(request.form['amount']),
            items=request.form['items'],
            unit_type=request.form['unit_type'],
            discount_percent=float(request.form.get('discount_percent') or 0),
            discount_flat=float(request.form.get('discount_flat') or 0),
            gst_type=request.form['gst_type'],
            paid=float(request.form['paid']),
            transaction_date=datetime.strptime(request.form['transaction_date'], '%Y-%m-%d')
        )
        db.session.add(transaction)
        db.session.commit()
        flash('✅ Transaction added', 'success')
        return redirect(url_for('transactions'))

    all_transactions = Transaction.query.all()
    return render_template('transaction_list.html', transactions=all_transactions, customers=customers)

@app.route('/transactions/delete/<int:transaction_id>')
@login_required
def delete_transaction(transaction_id):
    transaction = Transaction.query.get_or_404(transaction_id)
    db.session.delete(transaction)
    db.session.commit()
    flash('✅ Transaction deleted', 'success')
    return redirect(url_for('transactions'))

@app.route('/transactions/receipt/<int:transaction_id>')
@login_required
def receipt(transaction_id):
    transaction = Transaction.query.get_or_404(transaction_id)
    rendered = render_template('receipt.html', transaction=transaction)
    pdf = BytesIO()
    pisa.CreatePDF(BytesIO(rendered.encode('utf-8')), dest=pdf)
    pdf.seek(0)
    return send_file(pdf, download_name='receipt.pdf', as_attachment=True)

@app.route('/transactions/export/csv')
@login_required
def export_csv():
    transactions = Transaction.query.all()
    output = BytesIO()
    writer = csv.writer(output)
    writer.writerow(['ID', 'Customer', 'Amount', 'Paid', 'Date'])
    for t in transactions:
        writer.writerow([t.id, t.customer.name, t.amount, t.paid, t.transaction_date])
    output.seek(0)
    return send_file(output, mimetype='text/csv', download_name='transactions.csv', as_attachment=True)

@app.route('/settings', methods=['GET', 'POST'])
@login_required
def settings():
    settings_data = load_settings()
    if request.method == 'POST':
        if 'logo' in request.files:
            logo = request.files['logo']
            if logo and allowed_file(logo.filename):
                filename = secure_filename(logo.filename)
                filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                logo.save(filepath)
                settings_data['logo_path'] = filepath

        settings_data['company_address'] = request.form.get('company_address')
        settings_data['receipt_footer'] = request.form.get('receipt_footer')

        save_settings(settings_data)
        flash("✅ Settings updated!", "success")
        return redirect(url_for('settings'))

    return render_template(
        'settings.html',
        logo_url='/' + settings_data.get('logo_path', '') if settings_data.get('logo_path') else None,
        company_address=settings_data.get('company_address', ''),
        receipt_footer=settings_data.get('receipt_footer', '')
    )

# App start
if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        if not User.query.filter_by(username='admin').first():
            admin = User(username='admin')
            admin.set_password('admin123')
            db.session.add(admin)
            db.session.commit()
            print("🔧 Default admin user created. Login with admin/admin123")
    app.run(debug=True)
