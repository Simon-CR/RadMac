import os

class Config:
    DEBUG = False
    TESTING = False
    SECRET_KEY = os.getenv('FLASK_SECRET_KEY', 'insecure-default-key')

    # Database connection info
    DB_HOST = os.getenv('DB_HOST', 'localhost')
    DB_PORT = int(os.getenv('DB_PORT', '3306'))
    DB_USER = os.getenv('DB_USER', 'radiususer')
    DB_PASSWORD = os.getenv('DB_PASSWORD', 'radiuspass')
    DB_NAME = os.getenv('DB_NAME', 'radius')

    # Logging
    LOG_TO_FILE = os.getenv('LOG_TO_FILE', 'false').lower() == 'true'
    LOG_FILE_PATH = os.getenv('LOG_FILE_PATH', '/app/logs/app.log')

    # MAC Lookup API
    OUI_API_URL = os.getenv('OUI_API_URL', 'https://api.maclookup.app/v2/macs/{}')
    OUI_API_KEY = os.getenv('OUI_API_KEY', '')
    OUI_API_LIMIT_PER_SEC = int(os.getenv('OUI_API_LIMIT_PER_SEC', '2'))
    OUI_API_DAILY_LIMIT = int(os.getenv('OUI_API_DAILY_LIMIT', '10000'))

    # Timezone
    APP_TIMEZONE = os.getenv('APP_TIMEZONE', 'UTC')

    # RADIUS Configuration
    RADIUS_HOST = os.getenv('RADIUS_HOST', 'radius')
    RADIUS_PORT = int(os.getenv('RADIUS_PORT', '1812'))
    RADIUS_SECRET = os.getenv('RADIUS_SECRET', 'testing123')

class DevelopmentConfig(Config):
    DEBUG = True

class ProductionConfig(Config):
    DEBUG = False

# Runtime selection
if os.getenv('FLASK_ENV') == 'production':
    app_config = ProductionConfig
else:
    app_config = DevelopmentConfig
