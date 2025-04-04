from flask import Flask, render_template, request, redirect, url_for, flash, send_file, make_response
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
from io import BytesIO
from xhtml2pdf import pisa
import os
import csv
from os import environ

app = Flask(__name__)

# Production configurations
app.config['SECRET_KEY'] = environ.get('SECRET_KEY', 'dev_secret_key')
app.config['SESSION_COOKIE_SECURE'] = environ.get('PRODUCTION', False)
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['PERMANENT_SESSION_LIFETIME'] = 1800  # 30 minutes

# Database configuration
database_url = environ.get('DATABASE_URL')
if database_url and database_url.startswith('postgres://'):
    database_url = database_url.replace('postgres://', 'postgresql://', 1)
app.config['SQLALCHEMY_DATABASE_URI'] = database_url or 'sqlite:///billing.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# File upload configuration
app.config['UPLOAD_FOLDER'] = 'static/uploads'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size

# Configure logging for production
if environ.get('PRODUCTION'):
    import logging
    from logging.handlers import RotatingFileHandler
    logging.basicConfig(level=logging.INFO)
    handler = RotatingFileHandler('app.log', maxBytes=10000, backupCount=3)
    handler.setLevel(logging.INFO)
    app.logger.addHandler(handler)
db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

# ------------------ MODELS ------------------

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(150), unique=True, nullable=False)
    password_hash = db.Column(db.String(150), nullable=False)
    email = db.Column(db.String(150), unique=True)
    role = db.Column(db.String(20), default='user')  # admin or user
    is_active = db.Column(db.Boolean, default=True)
    last_login = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    permissions = db.Column(db.JSON)  # Store user permissions as JSON
    branch_id = db.Column(db.Integer)  # For multi-branch support

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)
    
    def has_permission(self, permission):
        if self.role == 'admin':
            return True
        return self.permissions and permission in self.permissions
    
    def is_admin(self):
        return self.role == 'admin'

class Customer(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    contact = db.Column(db.String(100))
    email = db.Column(db.String(150))
    address = db.Column(db.Text)
    gst_number = db.Column(db.String(20))
    customer_type = db.Column(db.String(20))  # Regular, Walk-in
    due_date = db.Column(db.Date)
    credit_limit = db.Column(db.Float, default=0)
    status = db.Column(db.String(20))  # Active, Inactive
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_transaction_date = db.Column(db.DateTime)
    total_transactions = db.Column(db.Integer, default=0)
    total_spent = db.Column(db.Float, default=0)
    outstanding_balance = db.Column(db.Float, default=0)
    payment_terms = db.Column(db.Integer)  # Days
    preferred_payment_method = db.Column(db.String(50))
    alert_on_due = db.Column(db.Boolean, default=True)
    
    transactions = db.relationship('Transaction', backref='customer_info', lazy=True)
    
    def update_transaction_stats(self):
        self.total_transactions = len(self.transactions)
        self.total_spent = sum(t.amount for t in self.transactions)
        self.outstanding_balance = sum(t.balance for t in self.transactions if t.balance > 0)
        if self.transactions:
            self.last_transaction_date = max(t.transaction_date for t in self.transactions)
    
    def is_overdue(self):
        return self.due_date and self.due_date < datetime.now().date() and self.outstanding_balance > 0

class Service(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    type = db.Column(db.String(50))  # Per Hour, Per Square Feet, Per Piece
    min_price = db.Column(db.Float)
    max_price = db.Column(db.Float)
    variable_pricing = db.Column(db.Boolean, default=False)  # Flag for variable pricing
    price_factors = db.Column(db.JSON)  # Store pricing factors and rules
    custom_fields = db.Column(db.JSON)  # Store custom fields as JSON

class Transaction(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    customer_id = db.Column(db.Integer, db.ForeignKey('customer.id'))
    invoice_type = db.Column(db.String(50))  # Proforma, Tax Invoice, Credit Note
    amount = db.Column(db.Float, nullable=False)
    items = db.Column(db.String(200))
    unit_type = db.Column(db.String(50))
    quantity = db.Column(db.Float, default=1.0)
    unit_price = db.Column(db.Float)
    discount_percent = db.Column(db.Float, default=0)
    discount_flat = db.Column(db.Float, default=0)
    gst_type = db.Column(db.String(20))  # None, CGST-SGST, IGST
    paid = db.Column(db.Float, default=0)
    balance = db.Column(db.Float)
    transaction_date = db.Column(db.Date, default=datetime.utcnow)
    due_date = db.Column(db.Date)
    is_recurring = db.Column(db.Boolean, default=False)
    recurring_interval = db.Column(db.Integer)  # Days between recurring invoices
    next_recurring_date = db.Column(db.Date)
    status = db.Column(db.String(20))  # Draft, Pending, Paid, Overdue
    notes = db.Column(db.Text)
    proof_upload = db.Column(db.String(200))  # Path to uploaded proof file
    delivery_type = db.Column(db.String(20))  # Pickup or Delivery
    delivery_address = db.Column(db.Text)
    paper_type = db.Column(db.String(50))
    lamination = db.Column(db.Boolean, default=False)
    binding = db.Column(db.String(50))
    color_option = db.Column(db.String(20))  # Color or Black & White
    
    # Service-specific fields
    service_id = db.Column(db.Integer, db.ForeignKey('service.id'))
    variable_price = db.Column(db.Float)  # Price set by manager for variable pricing
    price_factors = db.Column(db.JSON)  # Store factors affecting the variable price
    service_details = db.Column(db.Text)  # Additional service details

    customer = db.relationship('Customer')

    def calculate_total(self):
        subtotal = self.unit_price * self.quantity
        discount = (subtotal * self.discount_percent / 100) + (self.discount_flat or 0)
        total = subtotal - discount
        
        if self.gst_type == 'CGST-SGST':
            total += subtotal * 0.18  # 9% CGST + 9% SGST
        elif self.gst_type == 'IGST':
            total += subtotal * 0.18  # 18% IGST
            
        self.amount = total
        self.balance = total - (self.paid or 0)
        return total

class Settings(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    # Branding
    logo = db.Column(db.String(100))
    company_name = db.Column(db.String(100))
    company_address = db.Column(db.Text)
    receipt_footer = db.Column(db.Text)
    theme_color = db.Column(db.String(20))
    font_family = db.Column(db.String(50))
    
    # Bank Account Information
    bank_name = db.Column(db.String(100))
    account_holder = db.Column(db.String(100))
    account_number = db.Column(db.String(50))
    ifsc_code = db.Column(db.String(20))
    swift_code = db.Column(db.String(20))
    
    # Receipt Templates
    receipt_template_a4 = db.Column(db.Text)
    receipt_template_a5 = db.Column(db.Text)
    receipt_template_thermal = db.Column(db.Text)
    qr_code_enabled = db.Column(db.Boolean, default=True)
    
    # Backup Settings
    auto_backup_enabled = db.Column(db.Boolean, default=True)
    backup_frequency = db.Column(db.Integer, default=24)  # Hours
    cloud_backup_provider = db.Column(db.String(20))  # Google Drive, Dropbox
    cloud_backup_path = db.Column(db.String(200))
    last_backup_date = db.Column(db.DateTime)
    
    # Notification Settings
    email_notifications = db.Column(db.Boolean, default=True)
    whatsapp_notifications = db.Column(db.Boolean, default=False)
    notification_email = db.Column(db.String(100))
    whatsapp_api_key = db.Column(db.String(100))
    
    # User Role Settings
    admin_timeout = db.Column(db.Integer, default=30)  # Minutes
    user_timeout = db.Column(db.Integer, default=15)  # Minutes

# ------------------ LOGIN ------------------

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        user = User.query.filter_by(username=request.form['username']).first()
        if user and user.check_password(request.form['password']):
            login_user(user)
            return redirect(url_for('home'))
        else:
            flash("Invalid username or password", "danger")
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

# ------------------ HOME ------------------

@app.route('/')
@login_required
def home():
    # Get all transactions
    transactions = Transaction.query.order_by(Transaction.transaction_date.desc()).all()
    
    # Calculate totals
    total = sum(t.amount for t in transactions)
    paid = sum(t.amount for t in transactions if t.status == 'Paid')
    pending = sum(t.amount for t in transactions if t.status == 'Pending')
    
    # Get customers with overdue payments
    overdue_customers = Customer.query.filter(Customer.due_date < datetime.now().date()).all()
    
    # Get upcoming dues
    upcoming_dues = Customer.query.filter(
        Customer.due_date >= datetime.now().date()
    ).order_by(Customer.due_date).limit(5).all()

    # Calculate monthly revenue data for the last 6 months
    today = datetime.now()
    revenue_labels = []
    revenue_data = []
    paid_data = []
    
    for i in range(5, -1, -1):
        month = today.month - i
        year = today.year
        if month <= 0:
            month += 12
            year -= 1
        
        start_date = datetime(year, month, 1)
        if month == 12:
            end_date = datetime(year + 1, 1, 1)
        else:
            end_date = datetime(year, month + 1, 1)
        
        month_transactions = Transaction.query.filter(
            Transaction.transaction_date >= start_date,
            Transaction.transaction_date < end_date
        ).all()
        
        month_revenue = sum(t.amount for t in month_transactions)
        month_paid = sum(t.amount for t in month_transactions if t.status == 'Paid')
        
        revenue_labels.append(start_date.strftime('%b %Y'))
        revenue_data.append(round(month_revenue, 2))
        paid_data.append(round(month_paid, 2))

    return render_template('home.html', total=total, paid=paid, pending=pending,
                         upcoming_dues=upcoming_dues, overdue_customers=overdue_customers,
                         transactions=transactions, revenue_labels=revenue_labels,
                         revenue_data=revenue_data, paid_data=paid_data)

# ------------------ CUSTOMERS ------------------

@app.route('/customers', methods=['GET', 'POST'])
@app.route('/customers/<int:customer_id>', methods=['GET', 'POST'])
@login_required
def customers(customer_id=None):
    customer = None
    if request.method == 'POST':
        name = request.form['name']
        contact = request.form['contact']
        due_date = datetime.strptime(request.form['due_date'], '%Y-%m-%d') if request.form['due_date'] else None
        status = request.form['status']

        if customer_id:
            customer = Customer.query.get_or_404(customer_id)
            customer.name = name
            customer.contact = contact
            customer.due_date = due_date
            customer.status = status
        else:
            db.session.add(Customer(name=name, contact=contact, due_date=due_date, status=status))

        db.session.commit()
        return redirect(url_for('customers'))

    if customer_id:
        customer = Customer.query.get_or_404(customer_id)

    return render_template('customers.html', customers=Customer.query.all(), customer=customer)

@app.route('/customers/delete/<int:customer_id>')
@login_required
def delete_customer(customer_id):
    db.session.delete(Customer.query.get_or_404(customer_id))
    db.session.commit()
    return redirect(url_for('customers'))

# ------------------ TRANSACTIONS ------------------

@app.route('/transactions', methods=['GET', 'POST'])
@login_required
def transactions():
    customers = Customer.query.all()
    services = Service.query.all()
    if request.method == 'POST':
        service = None
        if request.form.get('service_id'):
            service = Service.query.get(request.form['service_id'])
            
        transaction = Transaction(
            customer_id=request.form['customer_id'],
            service_id=request.form.get('service_id'),
            amount=request.form.get('variable_price') if service and service.variable_pricing else request.form['amount'],
            items=request.form['items'],
            unit_type=request.form['unit_type'],
            quantity=float(request.form.get('quantity', 1.0)),
            unit_price=float(request.form.get('unit_price', 0)),
            discount_percent=float(request.form.get('discount_percent') or 0),
            discount_flat=float(request.form.get('discount_flat') or 0),
            gst_type=request.form['gst_type'],
            paid=float(request.form.get('paid') or 0),
            transaction_date=datetime.strptime(request.form['transaction_date'], '%Y-%m-%d'),
            service_details=request.form.get('service_details'),
            variable_price=float(request.form.get('variable_price')) if service and service.variable_pricing else None)
        db.session.add(transaction)
        db.session.commit()
        return redirect(url_for('transactions'))
    return render_template('transaction_list.html', transactions=Transaction.query.all(), customers=customers)

@app.route('/api/service/<int:service_id>')
@login_required
def get_service(service_id):
    service = Service.query.get_or_404(service_id)
    return jsonify({
        'id': service.id,
        'name': service.name,
        'variable_pricing': service.variable_pricing,
        'min_price': service.min_price,
        'max_price': service.max_price
    })

@app.route('/transactions/receipt/<int:transaction_id>')
@login_required
def transaction_receipt(transaction_id):
    transaction = Transaction.query.get_or_404(transaction_id)
    settings = Settings.query.first()
    
    # Render the receipt template
    html = render_template('receipt.html', transaction=transaction, settings=settings)
    
    # Generate PDF if requested
    if request.args.get('format') == 'pdf':
        # Create PDF from HTML
        pdf_buffer = BytesIO()
        pisa.CreatePDF(html, dest=pdf_buffer)
        
        # Prepare response
        pdf_buffer.seek(0)
        response = make_response(pdf_buffer.getvalue())
        response.headers['Content-Type'] = 'application/pdf'
        response.headers['Content-Disposition'] = f'inline; filename=receipt_{transaction_id}.pdf'
        return response
    
    return html

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)