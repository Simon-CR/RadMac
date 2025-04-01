import os, pytz

class Config:
    DEBUG = False
    TESTING = False
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SECRET_KEY = os.getenv('FLASK_SECRET_KEY', 'default-insecure-key')

    # Logging
    LOG_TO_FILE = os.getenv('LOG_TO_FILE', 'false').lower() == 'true'
    LOG_FILE_PATH = os.getenv('LOG_FILE_PATH', '/app/logs/app.log')

    # MAC Lookup API
    OUI_API_URL = os.getenv('OUI_API_URL', 'https://api.maclookup.app/v2/macs/{}')
    OUI_API_KEY = os.getenv('OUI_API_KEY', '')
    OUI_API_LIMIT_PER_SEC = int(os.getenv('OUI_API_LIMIT_PER_SEC', '2'))
    OUI_API_DAILY_LIMIT = int(os.getenv('OUI_API_DAILY_LIMIT', '10000')) 

    # These get set in __init__
    APP_TIMEZONE = 'UTC'
    TZ = pytz.utc

    def __init__(self):
        tz_name = os.getenv('APP_TIMEZONE', 'UTC')
        self.APP_TIMEZONE = tz_name
        self.TZ = pytz.timezone(tz_name)

class DevelopmentConfig(Config):
    """Development configuration."""
    DEBUG = True
    MYSQL_HOST = os.getenv('MYSQL_HOST', '192.168.60.150')
    MYSQL_USER = os.getenv('MYSQL_USER', 'user_92z0Kj')
    MYSQL_PASSWORD = os.getenv('MYSQL_PASSWORD', '5B3UXZV8vyrB')
    MYSQL_DATABASE = os.getenv('MYSQL_DATABASE', 'radius_NIaIuT')

class ProductionConfig(Config):
    """Production configuration."""
    MYSQL_HOST = os.getenv('MYSQL_HOST')
    MYSQL_USER = os.getenv('MYSQL_USER')
    MYSQL_PASSWORD = os.getenv('MYSQL_PASSWORD')
    MYSQL_DATABASE = os.getenv('MYSQL_DATABASE')

# Use the correct config based on environment
if os.getenv('FLASK_ENV') == 'production':
    app_config = ProductionConfig
else:
    app_config = DevelopmentConfig
