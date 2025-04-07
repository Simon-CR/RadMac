from flask import Flask, redirect, url_for, render_template
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

@app.route('/')
def index_redirect():
    return render_template('index.html')

@app.route('/maintenance')
def maintenance():
    return redirect(url_for('maintenance.maintenance'))