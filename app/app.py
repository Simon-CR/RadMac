# Authentication and user management routes
from flask import render_template, request, redirect, url_for, flash
from flask_login import login_user, logout_user, login_required, current_user
from db_interface import get_auth_user_by_username, add_auth_user, update_auth_username, update_auth_password, count_auth_users
from werkzeug.security import generate_password_hash, check_password_hash

# Enrollment route (first user setup)
@app.route('/enroll', methods=['GET', 'POST'])
def enroll():
    if count_auth_users() > 0:
        return redirect(url_for('login'))
    error = None
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        password2 = request.form['password2']
        if password != password2:
            error = 'Passwords do not match.'
        elif get_auth_user_by_username(username):
            error = 'Username already exists.'
        else:
            add_auth_user(username, generate_password_hash(password))
            flash('Account created. Please log in.')
            return redirect(url_for('login'))
    return render_template('enroll.html', error=error)

# Login route
@app.route('/login', methods=['GET', 'POST'])
def login():
    if count_auth_users() == 0:
        return redirect(url_for('enroll'))
    error = None
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = get_auth_user_by_username(username)
        if user and check_password_hash(user['password_hash'], password):
            login_user(AuthUser(user['id'], user['username'], user['password_hash']))
            return redirect(url_for('index_redirect'))
        else:
            error = 'Invalid username or password.'
    return render_template('login.html', error=error)
            from flask import render_template, request, redirect, url_for, flash
            from flask_login import login_user, logout_user, login_required, current_user
            from db_interface import get_auth_user_by_username, add_auth_user, update_auth_username, update_auth_password, count_auth_users
            from werkzeug.security import generate_password_hash, check_password_hash

            # Authentication and user management routes (must be after app is defined)
            # Enrollment route (first user setup)
    app.logger.addHandler(handler)

app.logger.setLevel(logging.INFO)

# Route setup
app.register_blueprint(index)
app.register_blueprint(user, url_prefix='/user')
app.register_blueprint(group, url_prefix='/group')
app.register_blueprint(stats, url_prefix='/stats')
app.register_blueprint(maintenance, url_prefix='/maintenance')

@app.route('/user_list')
def legacy_user_list():
    return redirect(url_for('user.user_list'))

@app.route('/groups')
def legacy_group_list():
    return redirect(url_for('group.group_list'))


# Protect all routes except homepage
@app.before_request
def require_login():
    allowed = ['index_redirect', 'login', 'enroll', 'static']
    if request.endpoint not in allowed and not current_user.is_authenticated:
        return redirect(url_for('login'))

@app.route('/')
def index_redirect():
    return render_template('index.html')

@app.route('/maintenance')
def maintenance():
    return redirect(url_for('maintenance.maintenance'))