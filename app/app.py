from flask import Flask, redirect, url_for, render_template
from views.index_views import index
from views.user_views import user
from views.group_views import group
from config import app_config
from database import init_app

app = Flask(__name__)
app.config.from_object(app_config)

init_app(app)

app.register_blueprint(index)
app.register_blueprint(user, url_prefix='/user')
app.register_blueprint(group, url_prefix='/group')

@app.route('/user_list')
def legacy_user_list():
    return redirect(url_for('user.user_list'))

@app.route('/groups')
def legacy_group_list():
    return redirect(url_for('group.groups'))

@app.route('/')
def index_redirect():
    return render_template('index.html')

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=8080)