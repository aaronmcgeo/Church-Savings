from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_mysqldb import MySQL
from datetime import datetime

app = Flask(__name__)
app.secret_key = 'Church Savings'

# MySQL Configuration
app.config['MYSQL_HOST'] = 'localhost'
app.config['MYSQL_USER'] = 'root'
app.config['MYSQL_PASSWORD'] = 'Aaron123456789'
app.config['MYSQL_DB'] = 'church_savings'
app.config['MYSQL_CURSORCLASS'] = 'DictCursor'

mysql = MySQL(app)

def init_db():
    try:
        cur = mysql.connection.cursor()
        cur.execute('''
            CREATE TABLE IF NOT EXISTS members (
                id VARCHAR(50) PRIMARY KEY,
                name VARCHAR(255) NOT NULL,
                address TEXT NOT NULL,
                contact VARCHAR(20),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        cur.execute('''
            CREATE TABLE IF NOT EXISTS savings (
                id INT AUTO_INCREMENT PRIMARY KEY,
                member_id VARCHAR(50),
                date DATE NOT NULL,
                amount DECIMAL(10, 2) NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (member_id) REFERENCES members(id) ON DELETE CASCADE
            )
        ''')
        cur.execute('''
            CREATE TABLE IF NOT EXISTS loans (
                id INT AUTO_INCREMENT PRIMARY KEY,
                member_id VARCHAR(50),
                date DATE NOT NULL,
                amount DECIMAL(10, 2) NOT NULL,
                interest_rate DECIMAL(5, 2) NOT NULL,
                interest_amount DECIMAL(10, 2) DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (member_id) REFERENCES members(id) ON DELETE CASCADE
            )
        ''')
        cur.execute('''
            CREATE TABLE IF NOT EXISTS loan_repayments (
                id INT AUTO_INCREMENT PRIMARY KEY,
                loan_id INT,
                date DATE NOT NULL,
                principal_paid DECIMAL(10, 2) DEFAULT 0,
                interest_paid DECIMAL(10, 2) DEFAULT 0,
                total_amount DECIMAL(10, 2) NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (loan_id) REFERENCES loans(id) ON DELETE CASCADE
            )
        ''')
        mysql.connection.commit()
        cur.close()
        print("✅ Database tables created successfully!")
    except Exception as e:
        print(f"❌ Error creating database tables: {e}")

def calculate_interest(loan_date, amount, interest_rate):
    from datetime import datetime, date
    current_date = date.today()
    if isinstance(loan_date, str):
        loan_date_obj = datetime.strptime(loan_date, '%Y-%m-%d').date()
    elif isinstance(loan_date, datetime):
        loan_date_obj = loan_date.date()
    else:
        loan_date_obj = loan_date
    months_diff = (current_date.year - loan_date_obj.year) * 12 + (current_date.month - loan_date_obj.month)
    if months_diff < 0:
        months_diff = 0
    interest = (float(amount) * float(interest_rate) * months_diff) / 100
    return round(interest, 2)

@app.route('/')
def index():
    cur = mysql.connection.cursor()
    cur.execute('SELECT COUNT(*) as count FROM members')
    total_members = cur.fetchone()['count']
    cur.execute('SELECT COALESCE(SUM(amount), 0) as total FROM savings')
    total_savings = float(cur.fetchone()['total'])
    cur.execute('SELECT COALESCE(SUM(amount), 0) as total FROM loans')
    total_loans = float(cur.fetchone()['total'])
    cur.execute('SELECT COALESCE(SUM(interest_paid), 0) as total FROM loan_repayments')
    total_profit = float(cur.fetchone()['total'])
    search_query = request.args.get('search', '')
    if search_query:
        cur.execute('SELECT * FROM members WHERE id LIKE %s OR name LIKE %s ORDER BY name',
                    (f'%{search_query}%', f'%{search_query}%'))
    else:
        cur.execute('SELECT * FROM members ORDER BY name')
    members = cur.fetchall()
    for member in members:
        cur.execute('SELECT COALESCE(SUM(amount), 0) as total FROM savings WHERE member_id = %s', [member['id']])
        member['total_savings'] = float(cur.fetchone()['total'])
        cur.execute('SELECT COALESCE(SUM(amount), 0) as total FROM loans WHERE member_id = %s', [member['id']])
        member['total_loans'] = float(cur.fetchone()['total'])
    cur.close()
    return render_template('index.html', total_members=total_members, total_savings=total_savings,
                           total_loans=total_loans, total_profit=total_profit, members=members, search_query=search_query)

@app.route('/member/<member_id>')
def view_member(member_id):
    cur = mysql.connection.cursor()
    cur.execute('SELECT * FROM members WHERE id = %s', [member_id])
    member = cur.fetchone()
    if not member:
        flash('Member not found', 'danger')
        return redirect(url_for('index'))
    cur.execute('SELECT * FROM savings WHERE member_id = %s ORDER BY date DESC', [member_id])
    savings = cur.fetchall()
    total_savings = sum(float(s['amount']) for s in savings)
    cur.execute('SELECT * FROM loans WHERE member_id = %s ORDER BY date DESC', [member_id])
    loans = cur.fetchall()
    total_interest_earned = 0
    for loan in loans:
        cur.execute('SELECT * FROM loan_repayments WHERE loan_id = %s ORDER BY date DESC', [loan['id']])
        loan['repayments'] = cur.fetchall()
        loan['principal_repaid'] = sum(float(r.get('principal_paid', 0)) for r in loan['repayments'])
        loan['interest_repaid'] = sum(float(r.get('interest_paid', 0)) for r in loan['repayments'])
        loan['total_repayments'] = loan['principal_repaid'] + loan['interest_repaid']
        loan['interest'] = calculate_interest(loan['date'], loan['amount'], loan['interest_rate'])
        total_interest_earned += loan['interest_repaid']
        loan['principal_remaining'] = float(loan['amount']) - loan['principal_repaid']
        loan['interest_remaining'] = loan['interest'] - loan['interest_repaid']
        loan['total_due'] = float(loan['amount']) + loan['interest']
        loan['remaining'] = loan['total_due'] - loan['total_repayments']
    total_loans = sum(float(l['amount']) for l in loans)
    cur.close()
    return render_template('member_profile.html', member=member, savings=savings, total_savings=total_savings,
                           loans=loans, total_loans=total_loans, total_interest_earned=total_interest_earned)

@app.route('/add_member', methods=['GET', 'POST'])
def add_member():
    if request.method == 'POST':
        member_id = request.form['member_id'].strip()
        name = request.form['name'].strip()
        address = request.form['address'].strip()
        contact = request.form.get('contact', '').strip()
        if not member_id or not name or not address:
            flash('Please fill in all required fields', 'danger')
            return redirect(url_for('add_member'))
        cur = mysql.connection.cursor()
        cur.execute('SELECT id FROM members WHERE id = %s', [member_id])
        if cur.fetchone():
            flash('Member ID already exists!', 'danger')
            cur.close()
            return redirect(url_for('add_member'))
        try:
            cur.execute('INSERT INTO members (id, name, address, contact) VALUES (%s, %s, %s, %s)',
                        (member_id, name, address, contact))
            mysql.connection.commit()
            flash('✅ Member added successfully!', 'success')
            cur.close()
            return redirect(url_for('index'))
        except Exception as e:
            flash(f'Error: {str(e)}', 'danger')
            cur.close()
            return redirect(url_for('add_member'))
    return render_template('add_member.html')

@app.route('/edit_member/<member_id>', methods=['GET', 'POST'])
def edit_member(member_id):
    cur = mysql.connection.cursor()
    if request.method == 'POST':
        name = request.form['name'].strip()
        address = request.form['address'].strip()
        contact = request.form.get('contact', '').strip()
        if not name or not address:
            flash('Please fill in all required fields', 'danger')
            return redirect(url_for('edit_member', member_id=member_id))
        try:
            cur.execute('UPDATE members SET name = %s, address = %s, contact = %s WHERE id = %s',
                        (name, address, contact, member_id))
            mysql.connection.commit()
            flash('✅ Member updated successfully!', 'success')
            cur.close()
            return redirect(url_for('view_member', member_id=member_id))
        except Exception as e:
            flash(f'Error: {str(e)}', 'danger')
            cur.close()
            return redirect(url_for('edit_member', member_id=member_id))
    cur.execute('SELECT * FROM members WHERE id = %s', [member_id])
    member = cur.fetchone()
    cur.close()
    if not member:
        flash('Member not found', 'danger')
        return redirect(url_for('index'))
    return render_template('edit_member.html', member=member)

@app.route('/delete_member/<member_id>')
def delete_member(member_id):
    cur = mysql.connection.cursor()
    cur.execute('DELETE FROM members WHERE id = %s', [member_id])
    mysql.connection.commit()
    cur.close()
    flash('✅ Member deleted successfully!', 'success')
    return redirect(url_for('index'))

@app.route('/add_savings/<member_id>', methods=['GET', 'POST'])
def add_savings(member_id):
    if request.method == 'POST':
        date = request.form['date']
        amount = request.form['amount']
        if not date or not amount:
            flash('Please fill in all required fields', 'danger')
            return redirect(url_for('add_savings', member_id=member_id))
        cur = mysql.connection.cursor()
        cur.execute('INSERT INTO savings (member_id, date, amount) VALUES (%s, %s, %s)', (member_id, date, amount))
        mysql.connection.commit()
        cur.close()
        flash('✅ Savings added successfully!', 'success')
        return redirect(url_for('view_member', member_id=member_id))
    cur = mysql.connection.cursor()
    cur.execute('SELECT * FROM members WHERE id = %s', [member_id])
    member = cur.fetchone()
    cur.close()
    return render_template('add_savings.html', member=member, today=datetime.now().strftime('%Y-%m-%d'))

@app.route('/add_loan/<member_id>', methods=['GET', 'POST'])
def add_loan(member_id):
    if request.method == 'POST':
        date = request.form['date']
        amount = request.form['amount']
        interest_rate = request.form['interest_rate']
        if not date or not amount or not interest_rate:
            flash('Please fill in all required fields', 'danger')
            return redirect(url_for('add_loan', member_id=member_id))
        cur = mysql.connection.cursor()
        cur.execute('INSERT INTO loans (member_id, date, amount, interest_rate, interest_amount) VALUES (%s, %s, %s, %s, 0)',
                    (member_id, date, amount, interest_rate))
        mysql.connection.commit()
        cur.close()
        flash('✅ Loan added successfully!', 'success')
        return redirect(url_for('view_member', member_id=member_id))
    cur = mysql.connection.cursor()
    cur.execute('SELECT * FROM members WHERE id = %s', [member_id])
    member = cur.fetchone()
    cur.close()
    return render_template('add_loan.html', member=member, today=datetime.now().strftime('%Y-%m-%d'))

@app.route('/edit_loan/<int:loan_id>', methods=['GET', 'POST'])
def edit_loan(loan_id):
    cur = mysql.connection.cursor()
    if request.method == 'POST':
        date = request.form['date']
        amount = request.form['amount']
        interest_rate = request.form['interest_rate']
        if not date or not amount or not interest_rate:
            flash('Please fill in all required fields', 'danger')
            return redirect(url_for('edit_loan', loan_id=loan_id))
        cur.execute('SELECT member_id FROM loans WHERE id = %s', [loan_id])
        member_id = cur.fetchone()['member_id']
        cur.execute('UPDATE loans SET date = %s, amount = %s, interest_rate = %s WHERE id = %s',
                    (date, amount, interest_rate, loan_id))
        mysql.connection.commit()
        cur.close()
        flash('✅ Loan updated successfully!', 'success')
        return redirect(url_for('view_member', member_id=member_id))
    cur.execute('SELECT l.*, m.name as member_name, m.id as member_id FROM loans l JOIN members m ON l.member_id = m.id WHERE l.id = %s', [loan_id])
    loan = cur.fetchone()
    cur.close()
    if not loan:
        flash('Loan not found', 'danger')
        return redirect(url_for('index'))
    return render_template('edit_loan.html', loan=loan)

@app.route('/delete_loan/<int:loan_id>')
def delete_loan(loan_id):
    cur = mysql.connection.cursor()
    cur.execute('SELECT member_id FROM loans WHERE id = %s', [loan_id])
    result = cur.fetchone()
    if result:
        member_id = result['member_id']
        cur.execute('DELETE FROM loans WHERE id = %s', [loan_id])
        mysql.connection.commit()
        flash('✅ Loan deleted successfully!', 'success')
        cur.close()
        return redirect(url_for('view_member', member_id=member_id))
    cur.close()
    flash('Loan not found', 'danger')
    return redirect(url_for('index'))

@app.route('/edit_savings/<int:savings_id>', methods=['GET', 'POST'])
def edit_savings(savings_id):
    cur = mysql.connection.cursor()
    if request.method == 'POST':
        date = request.form['date']
        amount = request.form['amount']
        if not date or not amount:
            flash('Please fill in all required fields', 'danger')
            return redirect(url_for('edit_savings', savings_id=savings_id))
        cur.execute('SELECT member_id FROM savings WHERE id = %s', [savings_id])
        member_id = cur.fetchone()['member_id']
        cur.execute('UPDATE savings SET date = %s, amount = %s WHERE id = %s', (date, amount, savings_id))
        mysql.connection.commit()
        cur.close()
        flash('✅ Savings updated successfully!', 'success')
        return redirect(url_for('view_member', member_id=member_id))
    cur.execute('SELECT s.*, m.name as member_name, m.id as member_id FROM savings s JOIN members m ON s.member_id = m.id WHERE s.id = %s', [savings_id])
    saving = cur.fetchone()
    cur.close()
    if not saving:
        flash('Savings record not found', 'danger')
        return redirect(url_for('index'))
    return render_template('edit_savings.html', saving=saving)

@app.route('/delete_savings/<int:savings_id>')
def delete_savings(savings_id):
    cur = mysql.connection.cursor()
    cur.execute('SELECT member_id FROM savings WHERE id = %s', [savings_id])
    result = cur.fetchone()
    if result:
        member_id = result['member_id']
        cur.execute('DELETE FROM savings WHERE id = %s', [savings_id])
        mysql.connection.commit()
        flash('✅ Savings deleted successfully!', 'success')
        cur.close()
        return redirect(url_for('view_member', member_id=member_id))
    cur.close()
    flash('Savings record not found', 'danger')
    return redirect(url_for('index'))

@app.route('/add_repayment/<int:loan_id>', methods=['GET', 'POST'])
def add_repayment(loan_id):
    if request.method == 'POST':
        date = request.form['date']
        principal_paid = request.form.get('principal_paid', 0)
        interest_paid = request.form.get('interest_paid', 0)
        total_amount = float(principal_paid) + float(interest_paid)
        if not date or total_amount <= 0:
            flash('Please enter at least one payment amount', 'danger')
            return redirect(url_for('add_repayment', loan_id=loan_id))
        cur = mysql.connection.cursor()
        cur.execute('SELECT member_id FROM loans WHERE id = %s', [loan_id])
        loan = cur.fetchone()
        cur.execute('INSERT INTO loan_repayments (loan_id, date, principal_paid, interest_paid, total_amount) VALUES (%s, %s, %s, %s, %s)',
                    (loan_id, date, principal_paid, interest_paid, total_amount))
        mysql.connection.commit()
        cur.close()
        flash('✅ Payment recorded successfully!', 'success')
        return redirect(url_for('view_member', member_id=loan['member_id']))
    cur = mysql.connection.cursor()
    cur.execute('SELECT l.*, m.name as member_name, m.id as member_id FROM loans l JOIN members m ON l.member_id = m.id WHERE l.id = %s', [loan_id])
    loan = cur.fetchone()
    cur.execute('SELECT * FROM loan_repayments WHERE loan_id = %s', [loan_id])
    repayments = cur.fetchall()
    principal_paid = sum(float(r.get('principal_paid', 0)) for r in repayments)
    interest_paid = sum(float(r.get('interest_paid', 0)) for r in repayments)
    principal_remaining = float(loan['amount']) - principal_paid
    interest_remaining = float(loan['interest_amount']) - interest_paid
    cur.close()
    return render_template('add_repayment.html', loan=loan, principal_remaining=principal_remaining,
                           interest_remaining=interest_remaining, today=datetime.now().strftime('%Y-%m-%d'))

@app.route('/savings_report')
def savings_report():
    cur = mysql.connection.cursor()
    cur.execute('SELECT s.*, m.name as member_name, m.id as member_id FROM savings s JOIN members m ON s.member_id = m.id ORDER BY s.date DESC')
    all_savings = cur.fetchall()
    cur.execute('''SELECT m.id, m.name, COALESCE(SUM(s.amount), 0) as total_savings, COUNT(s.id) as transaction_count
                   FROM members m LEFT JOIN savings s ON m.id = s.member_id GROUP BY m.id, m.name
                   HAVING total_savings > 0 ORDER BY total_savings DESC''')
    member_summary = cur.fetchall()
    cur.execute('SELECT COALESCE(SUM(amount), 0) as total FROM savings')
    total_savings = float(cur.fetchone()['total'])
    cur.close()
    return render_template('savings_report.html', all_savings=all_savings, member_summary=member_summary, total_savings=total_savings)

@app.route('/bulk_savings', methods=['GET', 'POST'])
def bulk_savings():
    cur = mysql.connection.cursor()
    if request.method == 'POST':
        date = request.form.get('date')
        if not date:
            flash('Please select a date', 'danger')
            return redirect(url_for('bulk_savings'))
        success_count = 0
        error_count = 0
        for key in request.form:
            if key.startswith('amount_'):
                member_id = key.replace('amount_', '')
                amount = request.form.get(key)
                if amount and float(amount) > 0:
                    try:
                        cur.execute('INSERT INTO savings (member_id, date, amount) VALUES (%s, %s, %s)', (member_id, date, amount))
                        success_count += 1
                    except Exception as e:
                        error_count += 1
        mysql.connection.commit()
        if success_count > 0:
            flash(f'✅ Successfully added savings for {success_count} member(s)!', 'success')
        if error_count > 0:
            flash(f'⚠️ Failed to add savings for {error_count} member(s)', 'danger')
        cur.close()
        return redirect(url_for('bulk_savings'))
    cur.execute('''SELECT m.id, m.name, COALESCE(SUM(s.amount), 0) as total_savings, MAX(s.date) as last_savings_date
                   FROM members m LEFT JOIN savings s ON m.id = s.member_id GROUP BY m.id, m.name ORDER BY m.name''')
    members = cur.fetchall()
    cur.close()
    return render_template('bulk_savings.html', members=members, today=datetime.now().strftime('%Y-%m-%d'))

@app.route('/ai_reports')
def ai_reports():
    cur = mysql.connection.cursor()
    cur.execute('SELECT COUNT(*) as count FROM members')
    total_members = cur.fetchone()['count']
    cur.execute('SELECT COALESCE(SUM(amount), 0) as total FROM savings')
    total_savings = float(cur.fetchone()['total'])
    cur.execute('SELECT COALESCE(SUM(amount), 0) as total FROM loans')
    total_loans = float(cur.fetchone()['total'])
    cur.execute('SELECT COALESCE(SUM(interest_paid), 0) as total FROM loan_repayments')
    total_profit = float(cur.fetchone()['total'])
    cur.close()
    context = {'total_members': total_members, 'total_savings': total_savings, 'total_loans': total_loans, 'total_profit': total_profit}
    return render_template('ai_reports.html', context=context)

@app.route('/ai_generate_report', methods=['POST'])
def ai_generate_report():
    query = request.json.get('query', '').lower()
    cur = mysql.connection.cursor()
    report_data = {}
    report_type = 'unknown'

    try:
        # Normalize query - remove punctuation and extra spaces
        import re
        query = re.sub(r'[^\w\s]', ' ', query)
        query = ' '.join(query.split())

        # SMART PATTERN MATCHING - Check for various question patterns

        # Pattern 1: Top/Highest/Best/Maximum SAVERS
        if any(word in query for word in ['top', 'highest', 'best', 'most', 'maximum', 'max', 'biggest', 'largest']) and \
                any(word in query for word in ['saver', 'saving', 'savings', 'saved', 'deposit']):
            cur.execute('''SELECT m.id, m.name, COALESCE(SUM(s.amount), 0) as total FROM members m
                           LEFT JOIN savings s ON m.id = s.member_id GROUP BY m.id, m.name 
                           HAVING total > 0 ORDER BY total DESC LIMIT 10''')
            report_data['members'] = cur.fetchall()
            report_type = 'top_savers'

        # Pattern 2: Top/Highest/Maximum LOAN TAKERS/BORROWERS
        elif any(word in query for word in ['top', 'highest', 'best', 'most', 'maximum', 'max', 'biggest', 'largest']) and \
                any(word in query for word in ['loan', 'borrow', 'borrowed', 'borrower', 'debt', 'credit', 'taken', 'took']):
            cur.execute('''SELECT m.id, m.name, COALESCE(SUM(l.amount), 0) as total FROM members m
                           LEFT JOIN loans l ON m.id = l.member_id GROUP BY m.id, m.name 
                           HAVING total > 0 ORDER BY total DESC LIMIT 10''')
            report_data['members'] = cur.fetchall()
            report_type = 'top_borrowers'

        # Pattern 3: Lowest/Minimum/Least SAVERS
        elif any(word in query for word in ['lowest', 'minimum', 'min', 'least', 'smallest', 'bottom']) and \
                any(word in query for word in ['saver', 'saving', 'savings', 'saved', 'deposit']):
            cur.execute('''SELECT m.id, m.name, COALESCE(SUM(s.amount), 0) as total FROM members m
                           LEFT JOIN savings s ON m.id = s.member_id GROUP BY m.id, m.name 
                           HAVING total > 0 ORDER BY total ASC LIMIT 10''')
            report_data['members'] = cur.fetchall()
            report_type = 'lowest_savers'

        # Pattern 4: Members WITHOUT savings / NO savings / ZERO savings
        elif any(phrase in query for phrase in ['without saving', 'no saving', 'zero saving', 'not saved', 'havent saved',
                                                'didnt save', 'never saved', 'no deposit', 'without deposit']):
            cur.execute('''SELECT m.id, m.name, m.contact FROM members m 
                           LEFT JOIN savings s ON m.id = s.member_id
                           GROUP BY m.id, m.name, m.contact 
                           HAVING COALESCE(SUM(s.amount), 0) = 0''')
            report_data['members'] = cur.fetchall()
            report_type = 'no_savings'

        # Pattern 5: Outstanding/Pending/Unpaid LOANS
        elif any(word in query for word in ['outstanding', 'pending', 'due', 'unpaid', 'not paid', 'havent paid',
                                            'didnt pay', 'remaining', 'balance', 'owe', 'owes', 'owing']):
            cur.execute('''SELECT m.id, m.name, l.id as loan_id, l.amount, l.date, 
                           COALESCE(SUM(lr.principal_paid), 0) as repaid
                           FROM members m JOIN loans l ON m.id = l.member_id 
                           LEFT JOIN loan_repayments lr ON l.id = lr.loan_id
                           GROUP BY m.id, m.name, l.id, l.amount, l.date 
                           HAVING l.amount > COALESCE(SUM(lr.principal_paid), 0)''')
            report_data['loans'] = cur.fetchall()
            report_type = 'outstanding_loans'

        # Pattern 6: Fully PAID loans / Completed loans
        elif any(word in query for word in ['paid', 'completed', 'finished', 'cleared', 'settled', 'closed']) and \
                any(word in query for word in ['loan', 'loans']):
            cur.execute('''SELECT m.id, m.name, l.id as loan_id, l.amount, l.date,
                           COALESCE(SUM(lr.principal_paid), 0) as repaid
                           FROM members m JOIN loans l ON m.id = l.member_id 
                           LEFT JOIN loan_repayments lr ON l.id = lr.loan_id
                           GROUP BY m.id, m.name, l.id, l.amount, l.date 
                           HAVING l.amount <= COALESCE(SUM(lr.principal_paid), 0)''')
            report_data['loans'] = cur.fetchall()
            report_type = 'paid_loans'

        # Pattern 7: Monthly SAVINGS report
        elif any(word in query for word in ['monthly', 'month', 'months', 'per month']) and \
                any(word in query for word in ['saving', 'savings', 'saved', 'deposit']):
            cur.execute('''SELECT DATE_FORMAT(date, '%Y-%m') as month, COUNT(*) as transactions, 
                           SUM(amount) as total FROM savings 
                           GROUP BY month ORDER BY month DESC LIMIT 12''')
            report_data['monthly'] = cur.fetchall()
            report_type = 'monthly_savings'

        # Pattern 8: Monthly LOANS report
        elif any(word in query for word in ['monthly', 'month', 'months', 'per month']) and \
                any(word in query for word in ['loan', 'loans', 'borrowed', 'borrow']):
            cur.execute('''SELECT DATE_FORMAT(date, '%Y-%m') as month, COUNT(*) as loans_given, 
                           SUM(amount) as total FROM loans 
                           GROUP BY month ORDER BY month DESC LIMIT 12''')
            report_data['monthly'] = cur.fetchall()
            report_type = 'monthly_loans'

        # Pattern 9: Recent/Latest SAVINGS
        elif any(word in query for word in ['recent', 'latest', 'last', 'new']) and \
                any(word in query for word in ['saving', 'savings', 'saved', 'deposit', 'transaction']):
            cur.execute('''SELECT s.date, m.name, s.amount FROM savings s 
                           JOIN members m ON s.member_id = m.id
                           ORDER BY s.date DESC, s.created_at DESC LIMIT 20''')
            report_data['transactions'] = cur.fetchall()
            report_type = 'recent_savings'

        # Pattern 10: Recent/Latest LOANS
        elif any(word in query for word in ['recent', 'latest', 'last', 'new']) and \
                any(word in query for word in ['loan', 'loans', 'borrowed', 'borrow']):
            cur.execute('''SELECT l.date, m.name, l.amount, l.interest_rate FROM loans l 
                           JOIN members m ON l.member_id = m.id
                           ORDER BY l.date DESC, l.created_at DESC LIMIT 20''')
            report_data['loans_recent'] = cur.fetchall()
            report_type = 'recent_loans'

        # Pattern 11: PROFIT/INTEREST report
        elif any(word in query for word in ['profit', 'interest', 'income', 'earn', 'earned', 'earnings']):
            cur.execute('''SELECT DATE_FORMAT(lr.date, '%Y-%m') as month, 
                           SUM(lr.interest_paid) as interest_earned
                           FROM loan_repayments lr 
                           GROUP BY month ORDER BY month DESC LIMIT 12''')
            report_data['monthly'] = cur.fetchall()
            cur.execute('SELECT COALESCE(SUM(interest_paid), 0) as total FROM loan_repayments')
            report_data['total_profit'] = float(cur.fetchone()['total'])
            report_type = 'profit_report'

        # Pattern 12: TOTAL/ALL savings
        elif any(word in query for word in ['total', 'all', 'entire', 'complete']) and \
                any(word in query for word in ['saving', 'savings', 'saved']):
            cur.execute('''SELECT COUNT(DISTINCT member_id) as active_savers, 
                           COUNT(*) as total_transactions,
                           SUM(amount) as total_amount, AVG(amount) as avg_amount, 
                           MIN(amount) as min_amount, MAX(amount) as max_amount
                           FROM savings''')
            report_data['summary'] = cur.fetchone()
            report_type = 'savings_summary'

        # Pattern 13: TOTAL/ALL loans
        elif any(word in query for word in ['total', 'all', 'entire', 'complete']) and \
                any(word in query for word in ['loan', 'loans', 'borrowed']):
            cur.execute('''SELECT COUNT(*) as total_loans, SUM(l.amount) as total_amount, 
                           SUM(COALESCE(lr.principal_paid, 0)) as total_repaid,
                           SUM(l.amount) - SUM(COALESCE(lr.principal_paid, 0)) as outstanding 
                           FROM loans l
                           LEFT JOIN (SELECT loan_id, SUM(principal_paid) as principal_paid 
                                      FROM loan_repayments GROUP BY loan_id) lr
                           ON l.id = lr.loan_id''')
            report_data['summary'] = cur.fetchone()
            report_type = 'loans_summary'

        # Pattern 14: ALL/LIST of members
        elif any(word in query for word in ['all', 'list', 'show']) and \
                any(word in query for word in ['member', 'members', 'people', 'person']):
            cur.execute('''SELECT m.id, m.name, COALESCE(SUM(s.amount), 0) as total_savings, 
                           COALESCE(SUM(l.amount), 0) as total_loans
                           FROM members m 
                           LEFT JOIN savings s ON m.id = s.member_id 
                           LEFT JOIN loans l ON m.id = l.member_id
                           GROUP BY m.id, m.name ORDER BY m.name''')
            report_data['members'] = cur.fetchall()
            report_type = 'all_members'

        # Pattern 15: SUMMARY/OVERVIEW/DASHBOARD
        elif any(word in query for word in ['summary', 'overview', 'dashboard', 'stats', 'statistics', 'report']):
            cur.execute('SELECT COUNT(*) as count FROM members')
            report_data['total_members'] = cur.fetchone()['count']
            cur.execute('SELECT COALESCE(SUM(amount), 0) as total FROM savings')
            report_data['total_savings'] = float(cur.fetchone()['total'])
            cur.execute('SELECT COALESCE(SUM(amount), 0) as total FROM loans')
            report_data['total_loans'] = float(cur.fetchone()['total'])
            cur.execute('SELECT COALESCE(SUM(interest_paid), 0) as total FROM loan_repayments')
            report_data['total_profit'] = float(cur.fetchone()['total'])
            report_type = 'summary'

        # Pattern 16: ACTIVE/INACTIVE members
        elif 'active' in query or 'inactive' in query:
            if 'inactive' in query:
                cur.execute('''SELECT m.id, m.name, m.contact FROM members m 
                               LEFT JOIN savings s ON m.id = s.member_id
                               WHERE s.id IS NULL OR s.date < DATE_SUB(CURDATE(), INTERVAL 3 MONTH)
                               GROUP BY m.id, m.name, m.contact''')
                report_data['members'] = cur.fetchall()
                report_type = 'inactive_members'
            else:
                cur.execute('''SELECT m.id, m.name, MAX(s.date) as last_transaction FROM members m 
                               JOIN savings s ON m.id = s.member_id
                               GROUP BY m.id, m.name
                               HAVING last_transaction >= DATE_SUB(CURDATE(), INTERVAL 3 MONTH)
                               ORDER BY last_transaction DESC''')
                report_data['members'] = cur.fetchall()
                report_type = 'active_members'

        # Default: Help message
        else:
            report_type = 'help'

        cur.close()
        return jsonify({'success': True, 'report_type': report_type, 'data': report_data, 'query': query})

    except Exception as e:
        cur.close()
        return jsonify({'success': False, 'error': str(e)})

if __name__ == '__main__':
    with app.app_context():
        init_db()
    print("\n" + "="*60)
    print("🎉 Church Savings Management System Starting...")
    print("="*60)
    print("🌐 Open: http://localhost:5000")
    print("="*60 + "\n")
    app.run(debug=True, host='0.0.0.0', port=5000)