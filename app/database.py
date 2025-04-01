import mysql.connector
from flask import current_app, g
from mysql.connector import pooling

# Optional: Use a pool if desired
def init_db_pool():
    return pooling.MySQLConnectionPool(
        pool_name="mypool",
        pool_size=5,
        pool_reset_session=True,
        host=current_app.config['MYSQL_HOST'],
        user=current_app.config['MYSQL_USER'],
        password=current_app.config['MYSQL_PASSWORD'],
        database=current_app.config['MYSQL_DATABASE']
    )

def get_db():
    if 'db' not in g:
        if 'db_pool' not in current_app.config:
            current_app.config['db_pool'] = init_db_pool()
        g.db = current_app.config['db_pool'].get_connection()
    return g.db

def close_db(e=None):
    db = g.pop('db', None)
    if db is not None:
        try:
            db.close()  # returns connection to the pool
        except Exception as err:
            print(f"[DB Cleanup] Failed to close DB connection: {err}")


def init_app(app):
    app.teardown_appcontext(close_db)
