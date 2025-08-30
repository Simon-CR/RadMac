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

# Logout route
@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

# User menu (rename/change password)
@app.route('/user_menu', methods=['GET', 'POST'])
@login_required
def user_menu():
    message = error = None
    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'rename':
            new_username = request.form['username']
            if get_auth_user_by_username(new_username):
                error = 'Username already exists.'
            else:
                update_auth_username(current_user.id, new_username)
                message = 'Username updated.'
        elif action == 'change_password':
            pw1 = request.form['password']
            pw2 = request.form['password2']
            if pw1 != pw2:
                error = 'Passwords do not match.'
            else:
                update_auth_password(current_user.id, generate_password_hash(pw1))
                message = 'Password updated.'
    return render_template('user_menu.html', message=message, error=error)
from flask import Flask, redirect, url_for, render_template, request
from flask_login import LoginManager, login_required, current_user, UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from views.index_views import index
from views.user_views import user
from views.group_views import group
from views.stats_views import stats
from views.maintenance_views import maintenance
from config import app_config


import logging, os
from logging.handlers import RotatingFileHandler

app = Flask(__name__)
app.config.from_object(app_config)

# Flask-Login setup
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# User class for Flask-Login
class AuthUser(UserMixin):
    def __init__(self, id, username, password_hash):
        self.id = id
        self.username = username
        self.password_hash = password_hash

# User loader (to be implemented in db_interface)
from db_interface import get_auth_user_by_id
@login_manager.user_loader
def load_user(user_id):
    user = get_auth_user_by_id(user_id)
    if user:
        return AuthUser(user['id'], user['username'], user['password_hash'])
    return None

if app.config.get('LOG_TO_FILE'):
    log_file = app.config.get('LOG_FILE_PATH', '/app/logs/app.log')
    os.makedirs(os.path.dirname(log_file), exist_ok=True)
    handler = RotatingFileHandler(log_file, maxBytes=1_000_000, backupCount=3)
    handler.setLevel(logging.INFO)
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