"""
Database migration script for RadMac: ensures auth_users table exists.
Run this at container startup before launching the app.
"""
from db_connection import get_connection
import os
import json
import subprocess
from datetime import datetime
from typing import Any, Dict, List, Tuple

CREATE_SCHEMA_VERSION_SQL = """
CREATE TABLE IF NOT EXISTS schema_version (
    version INT NOT NULL,
    applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""

CREATE_USERS_SQL = """
CREATE TABLE IF NOT EXISTS users (
    mac_address CHAR(12) NOT NULL PRIMARY KEY CHECK (mac_address REGEXP '^[0-9A-Fa-f]{12}$'),
    description VARCHAR(200),
    vlan_id VARCHAR(64) NOT NULL
);
"""

CREATE_AUTH_LOGS_SQL = """
CREATE TABLE IF NOT EXISTS auth_logs (
    id INT AUTO_INCREMENT PRIMARY KEY,
    mac_address CHAR(12) NOT NULL CHECK (mac_address REGEXP '^[0-9A-Fa-f]{12}$'),
    reply ENUM('Access-Accept', 'Access-Reject', 'Accept-Fallback') NOT NULL,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    result VARCHAR(500) DEFAULT NULL
);
"""

CREATE_MAC_VENDORS_SQL = """
CREATE TABLE IF NOT EXISTS mac_vendors (
    mac_prefix CHAR(6) NOT NULL PRIMARY KEY CHECK (mac_prefix REGEXP '^[0-9A-Fa-f]{6}$'),
    vendor_name VARCHAR(255),
    status ENUM('found', 'not_found') DEFAULT 'found',
    last_checked DATETIME DEFAULT CURRENT_TIMESTAMP,
    last_updated DATETIME DEFAULT CURRENT_TIMESTAMP
);
"""

CREATE_GROUPS_SQL = """
CREATE TABLE IF NOT EXISTS groups (
    vlan_id VARCHAR(64) NOT NULL PRIMARY KEY,
    description VARCHAR(200)
);
"""

CREATE_AUTH_USERS_SQL = """
CREATE TABLE IF NOT EXISTS auth_users (
    id INT AUTO_INCREMENT PRIMARY KEY,
    username VARCHAR(64) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""

CREATE_MONITOR_CHECKS_SQL = """
CREATE TABLE IF NOT EXISTS monitor_checks (
    id INT AUTO_INCREMENT PRIMARY KEY,
    service_name VARCHAR(64) NOT NULL UNIQUE,
    display_name VARCHAR(128) NOT NULL,
    host VARCHAR(255) NOT NULL,
    health_url VARCHAR(512) DEFAULT NULL,
    port INT DEFAULT NULL,
    check_type VARCHAR(32) NOT NULL,
    interval_seconds INT NOT NULL DEFAULT 30,
    startup_delay_seconds INT NOT NULL DEFAULT 60,
    actions TEXT NOT NULL DEFAULT '[]',
    enabled TINYINT(1) NOT NULL DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);
"""

CREATE_ALERT_DESTINATIONS_SQL = """
CREATE TABLE IF NOT EXISTS alert_destinations (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(128) NOT NULL UNIQUE,
    destination_type VARCHAR(32) NOT NULL,
    config_json TEXT NOT NULL,
    enabled TINYINT(1) NOT NULL DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);
"""

CREATE_MONITOR_CHECK_DESTINATIONS_SQL = """
CREATE TABLE IF NOT EXISTS monitor_check_destinations (
    check_id INT NOT NULL,
    destination_id INT NOT NULL,
    PRIMARY KEY (check_id, destination_id),
    CONSTRAINT fk_monitor_check_destinations_check
        FOREIGN KEY (check_id) REFERENCES monitor_checks(id) ON DELETE CASCADE,
    CONSTRAINT fk_monitor_check_destinations_destination
        FOREIGN KEY (destination_id) REFERENCES alert_destinations(id) ON DELETE CASCADE
);
"""

CREATE_MONITOR_CHECK_STATUS_SQL = """
CREATE TABLE IF NOT EXISTS monitor_check_status (
    check_id INT PRIMARY KEY,
    last_run TIMESTAMP NULL,
    dns_status ENUM('unknown', 'ok', 'fail') DEFAULT 'unknown',
    resolved_ip VARCHAR(64) DEFAULT NULL,
    ping_status ENUM('unknown', 'ok', 'fail') DEFAULT 'unknown',
    service_status ENUM('unknown', 'ok', 'fail') DEFAULT 'unknown',
    details TEXT DEFAULT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    CONSTRAINT fk_monitor_check_status_check
        FOREIGN KEY (check_id) REFERENCES monitor_checks(id) ON DELETE CASCADE
);
"""

CREATE_SMTP_SETTINGS_SQL = """
CREATE TABLE IF NOT EXISTS smtp_settings (
    id INT PRIMARY KEY,
    host VARCHAR(255) DEFAULT NULL,
    port INT DEFAULT 587,
    username VARCHAR(255) DEFAULT NULL,
    password VARCHAR(255) DEFAULT NULL,
    use_tls TINYINT(1) DEFAULT 1,
    use_ssl TINYINT(1) DEFAULT 0,
    from_email VARCHAR(255) DEFAULT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);
"""

DESIRED_TABLE_SCHEMAS: Dict[str, Dict[str, Any]] = {
    "schema_version": {
        "create_sql": CREATE_SCHEMA_VERSION_SQL,
        "columns": [
            ("version", {"type": "INT", "nullable": False}),
            ("applied_at", {
                "type": "TIMESTAMP",
                "nullable": True,
                "default": "CURRENT_TIMESTAMP",
                "default_is_function": True,
            }),
        ],
    },
    "users": {
        "create_sql": CREATE_USERS_SQL,
        "columns": [
            ("mac_address", {"type": "CHAR(12)", "nullable": False}),
            ("description", {"type": "VARCHAR(200)", "nullable": True}),
            ("vlan_id", {"type": "VARCHAR(64)", "nullable": False}),
        ],
    },
    "auth_logs": {
        "create_sql": CREATE_AUTH_LOGS_SQL,
        "columns": [
            ("id", {"type": "INT", "nullable": False, "extra": "AUTO_INCREMENT"}),
            ("mac_address", {"type": "CHAR(12)", "nullable": False}),
            ("reply", {"type": "ENUM('Access-Accept','Access-Reject','Accept-Fallback')", "nullable": False}),
            ("timestamp", {
                "type": "DATETIME",
                "nullable": True,
                "default": "CURRENT_TIMESTAMP",
                "default_is_function": True,
            }),
            ("result", {"type": "VARCHAR(500)", "nullable": True}),
        ],
    },
    "mac_vendors": {
        "create_sql": CREATE_MAC_VENDORS_SQL,
        "columns": [
            ("mac_prefix", {"type": "CHAR(6)", "nullable": False}),
            ("vendor_name", {"type": "VARCHAR(255)", "nullable": True}),
            ("status", {"type": "ENUM('found','not_found')", "nullable": True, "default": "found"}),
            ("last_checked", {
                "type": "DATETIME",
                "nullable": True,
                "default": "CURRENT_TIMESTAMP",
                "default_is_function": True,
            }),
            ("last_updated", {
                "type": "DATETIME",
                "nullable": True,
                "default": "CURRENT_TIMESTAMP",
                "default_is_function": True,
            }),
        ],
    },
    "groups": {
        "create_sql": CREATE_GROUPS_SQL,
        "columns": [
            ("vlan_id", {"type": "VARCHAR(64)", "nullable": False}),
            ("description", {"type": "VARCHAR(200)", "nullable": True}),
        ],
    },
    "auth_users": {
        "create_sql": CREATE_AUTH_USERS_SQL,
        "columns": [
            ("id", {"type": "INT", "nullable": False, "extra": "AUTO_INCREMENT"}),
            ("username", {"type": "VARCHAR(64)", "nullable": False}),
            ("password_hash", {"type": "VARCHAR(255)", "nullable": False}),
            ("created_at", {
                "type": "TIMESTAMP",
                "nullable": True,
                "default": "CURRENT_TIMESTAMP",
                "default_is_function": True,
            }),
        ],
    },
    "monitor_checks": {
        "create_sql": CREATE_MONITOR_CHECKS_SQL,
        "columns": [
            ("id", {"type": "INT", "nullable": False, "extra": "AUTO_INCREMENT"}),
            ("service_name", {"type": "VARCHAR(64)", "nullable": False}),
            ("display_name", {"type": "VARCHAR(128)", "nullable": False}),
            ("host", {"type": "VARCHAR(255)", "nullable": False}),
            ("health_url", {"type": "VARCHAR(512)", "nullable": True}),
            ("port", {"type": "INT", "nullable": True}),
            ("check_type", {"type": "VARCHAR(32)", "nullable": False}),
            ("interval_seconds", {"type": "INT", "nullable": False, "default": 30}),
            ("startup_delay_seconds", {"type": "INT", "nullable": False, "default": 60}),
            ("actions", {"type": "TEXT", "nullable": False}),
            ("enabled", {"type": "TINYINT(1)", "nullable": False, "default": 1}),
            ("created_at", {
                "type": "TIMESTAMP",
                "nullable": True,
                "default": "CURRENT_TIMESTAMP",
                "default_is_function": True,
            }),
            ("updated_at", {
                "type": "TIMESTAMP",
                "nullable": True,
                "default": "CURRENT_TIMESTAMP",
                "default_is_function": True,
                "on_update": "CURRENT_TIMESTAMP",
                "on_update_is_function": True,
            }),
        ],
    },
    "alert_destinations": {
        "create_sql": CREATE_ALERT_DESTINATIONS_SQL,
        "columns": [
            ("id", {"type": "INT", "nullable": False, "extra": "AUTO_INCREMENT"}),
            ("name", {"type": "VARCHAR(128)", "nullable": False}),
            ("destination_type", {"type": "VARCHAR(32)", "nullable": False}),
            ("config_json", {"type": "TEXT", "nullable": False}),
            ("enabled", {"type": "TINYINT(1)", "nullable": False, "default": 1}),
            ("created_at", {
                "type": "TIMESTAMP",
                "nullable": True,
                "default": "CURRENT_TIMESTAMP",
                "default_is_function": True,
            }),
            ("updated_at", {
                "type": "TIMESTAMP",
                "nullable": True,
                "default": "CURRENT_TIMESTAMP",
                "default_is_function": True,
                "on_update": "CURRENT_TIMESTAMP",
                "on_update_is_function": True,
            }),
        ],
    },
    "monitor_check_destinations": {
        "create_sql": CREATE_MONITOR_CHECK_DESTINATIONS_SQL,
        "columns": [
            ("check_id", {"type": "INT", "nullable": False}),
            ("destination_id", {"type": "INT", "nullable": False}),
        ],
    },
    "monitor_check_status": {
        "create_sql": CREATE_MONITOR_CHECK_STATUS_SQL,
        "columns": [
            ("check_id", {"type": "INT", "nullable": False}),
            ("last_run", {"type": "TIMESTAMP", "nullable": True}),
            ("dns_status", {"type": "ENUM('unknown','ok','fail')", "nullable": True, "default": "unknown"}),
            ("resolved_ip", {"type": "VARCHAR(64)", "nullable": True}),
            ("ping_status", {"type": "ENUM('unknown','ok','fail')", "nullable": True, "default": "unknown"}),
            ("service_status", {"type": "ENUM('unknown','ok','fail')", "nullable": True, "default": "unknown"}),
            ("details", {"type": "TEXT", "nullable": True}),
            ("updated_at", {
                "type": "TIMESTAMP",
                "nullable": True,
                "default": "CURRENT_TIMESTAMP",
                "default_is_function": True,
                "on_update": "CURRENT_TIMESTAMP",
                "on_update_is_function": True,
            }),
        ],
    },
    "smtp_settings": {
        "create_sql": CREATE_SMTP_SETTINGS_SQL,
        "columns": [
            ("id", {"type": "INT", "nullable": False}),
            ("host", {"type": "VARCHAR(255)", "nullable": True}),
            ("port", {"type": "INT", "nullable": True, "default": 587}),
            ("username", {"type": "VARCHAR(255)", "nullable": True}),
            ("password", {"type": "VARCHAR(255)", "nullable": True}),
            ("use_tls", {"type": "TINYINT(1)", "nullable": True, "default": 1}),
            ("use_ssl", {"type": "TINYINT(1)", "nullable": True, "default": 0}),
            ("from_email", {"type": "VARCHAR(255)", "nullable": True}),
            ("created_at", {
                "type": "TIMESTAMP",
                "nullable": True,
                "default": "CURRENT_TIMESTAMP",
                "default_is_function": True,
            }),
            ("updated_at", {
                "type": "TIMESTAMP",
                "nullable": True,
                "default": "CURRENT_TIMESTAMP",
                "default_is_function": True,
                "on_update": "CURRENT_TIMESTAMP",
                "on_update_is_function": True,
            }),
        ],
    },
}

DEFAULT_MONITOR_CHECKS = [
    {
        "service_name": "app",
        "display_name": "Web UI / Flask App",
        "host": os.environ.get("APP_HOST", "app"),
        "health_url": "http://app:8080/health",
        "port": 8080,
        "check_type": "app",
        "interval_seconds": 30,
        "startup_delay_seconds": 60,
        "actions": ["log"],
    },
    {
        "service_name": "nginx",
        "display_name": "Proxy / Web Entry",
        "host": os.environ.get("NGINX_HOST", "nginx"),
        "health_url": "http://nginx",
        "port": 80,
        "check_type": "nginx",
        "interval_seconds": 30,
        "startup_delay_seconds": 75,
        "actions": ["log"],
    },
    {
        "service_name": "database",
        "display_name": "Database",
        "host": os.environ.get("DB_HOST", "db"),
        "health_url": "http://db:8080/health",
        "port": int(os.environ.get("DB_PORT", 3306)),
        "check_type": "database",
        "interval_seconds": 30,
        "startup_delay_seconds": 90,
        "actions": ["log"],
    },
    {
        "service_name": "radius",
        "display_name": "Radius Server",
        "host": os.environ.get("RADIUS_HOST", "radius"),
        "health_url": "http://radius:8080/health",
        "port": int(os.environ.get("RADIUS_PORT", 1812)),
        "check_type": "radius",
        "interval_seconds": 30,
        "startup_delay_seconds": 90,
        "actions": ["log"],
    },
]

def get_current_schema_version(cursor):
    """Get the current schema version from the database."""
    try:
        cursor.execute("SELECT version FROM schema_version ORDER BY applied_at DESC LIMIT 1")
        row = cursor.fetchone()
        return row[0] if row else 0
    except Exception:
        # schema_version table doesn't exist yet
        return 0

def set_schema_version(cursor, version):
    """Set the current schema version in the database."""
    cursor.execute("INSERT INTO schema_version (version) VALUES (%s)", (version,))

def backup_database():
    """Create a backup of the database before migration."""
    try:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_filename = f"/app/logs/db_backup_pre_migration_{timestamp}.sql"
        
        # Ensure logs directory exists
        os.makedirs("/app/logs", exist_ok=True)
        
        # Get database connection details from environment
        db_host = os.environ.get('DB_HOST', 'localhost')
        db_user = os.environ.get('DB_USER', 'root')
        db_password = os.environ.get('DB_PASSWORD', '')
        db_name = os.environ.get('DB_NAME', 'radmac')
        
        # Create mysqldump command
        cmd = [
            'mysqldump',
            f'--host={db_host}',
            f'--user={db_user}',
            f'--password={db_password}',
            '--single-transaction',
            '--routines',
            '--triggers',
            db_name
        ]
        
        # Execute backup
        with open(backup_filename, 'w') as backup_file:
            result = subprocess.run(cmd, stdout=backup_file, stderr=subprocess.PIPE, text=True)
            
        if result.returncode == 0:
            print(f"[DB BACKUP] Database backup created: {backup_filename}")
            return True
        else:
            print(f"[DB BACKUP] Warning: Backup failed: {result.stderr}")
            return False
            
    except Exception as e:
        print(f"[DB BACKUP] Warning: Could not create backup: {e}")
        return False

def seed_monitor_checks(cursor):
    for check in DEFAULT_MONITOR_CHECKS:
        actions_json = json.dumps(check.get("actions", ["log"]))
        cursor.execute(
            """
            INSERT INTO monitor_checks (
                service_name, display_name, host, health_url, port, check_type,
                interval_seconds, startup_delay_seconds, actions, enabled
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 1)
            ON DUPLICATE KEY UPDATE
                display_name = VALUES(display_name),
                host = VALUES(host),
                health_url = VALUES(health_url),
                port = VALUES(port),
                check_type = VALUES(check_type),
                interval_seconds = VALUES(interval_seconds),
                startup_delay_seconds = VALUES(startup_delay_seconds),
                actions = VALUES(actions)
            """,
            (
                check["service_name"],
                check["display_name"],
                check["host"],
                check["health_url"],
                check.get("port"),
                check["check_type"],
                check["interval_seconds"],
                check["startup_delay_seconds"],
                actions_json,
            ),
        )

        cursor.execute(
            "SELECT id FROM monitor_checks WHERE service_name = %s",
            (check["service_name"],)
        )
        result = cursor.fetchone()
        if result:
            check_id = result[0]
            cursor.execute(
                "INSERT IGNORE INTO monitor_check_status (check_id) VALUES (%s)",
                (check_id,)
            )

def seed_smtp_settings(cursor):
    env_defaults = {
        "host": os.environ.get("SMTP_HOST") or os.environ.get("EMAIL_HOST"),
        "port": os.environ.get("SMTP_PORT") or os.environ.get("EMAIL_PORT") or 587,
        "username": os.environ.get("SMTP_USER") or os.environ.get("EMAIL_USER"),
        "password": os.environ.get("SMTP_PASSWORD") or os.environ.get("EMAIL_PASSWORD"),
        "from_email": os.environ.get("SMTP_FROM") or os.environ.get("EMAIL_FROM"),
        "use_tls": os.environ.get("SMTP_USE_TLS"),
        "use_ssl": os.environ.get("SMTP_USE_SSL"),
    }

    def _to_bool(value, default=True):
        if value is None:
            return 1 if default else 0
        if isinstance(value, str):
            return 1 if value.lower() in ("1", "true", "yes", "on") else 0
        return 1 if bool(value) else 0

    cursor.execute(
        """
        INSERT INTO smtp_settings (id, host, port, username, password, use_tls, use_ssl, from_email)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE
            host = COALESCE(VALUES(host), smtp_settings.host),
            port = VALUES(port),
            username = COALESCE(VALUES(username), smtp_settings.username),
            password = COALESCE(VALUES(password), smtp_settings.password),
            use_tls = VALUES(use_tls),
            use_ssl = VALUES(use_ssl),
            from_email = COALESCE(VALUES(from_email), smtp_settings.from_email)
        """,
        (
            1,
            env_defaults["host"],
            int(env_defaults["port"]) if str(env_defaults["port"]).isdigit() else 587,
            env_defaults["username"],
            env_defaults["password"],
            _to_bool(env_defaults["use_tls"], default=True),
            _to_bool(env_defaults["use_ssl"], default=False),
            env_defaults["from_email"],
        ),
    )


def _format_literal(value: Any) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, (int, float)):
        return str(value)
    escaped = str(value).replace("'", "''")
    return f"'{escaped}'"


def _column_definition_sql(name: str, spec: Dict[str, Any]) -> str:
    parts: List[str] = [f"`{name}`", spec["type"]]
    if spec.get("nullable", True):
        parts.append("NULL")
    else:
        parts.append("NOT NULL")
    if "default" in spec:
        default_value = spec.get("default")
        if default_value is None:
            parts.append("DEFAULT NULL")
        elif spec.get("default_is_function"):
            parts.append(f"DEFAULT {default_value}")
        else:
            parts.append(f"DEFAULT {_format_literal(default_value)}")
    elif spec.get("nullable", True):
        parts.append("DEFAULT NULL")
    if spec.get("extra"):
        parts.append(spec["extra"])
    if spec.get("on_update"):
        clause = spec["on_update"]
        if spec.get("on_update_is_function"):
            parts.append(f"ON UPDATE {clause}")
        else:
            parts.append(f"ON UPDATE {_format_literal(clause)}")
    return " ".join(parts)


def _normalize_type(value: str) -> str:
    return (value or "").strip().lower()


def _normalize_default(value: Any, is_function: bool = False) -> Any:
    if value is None:
        return None
    if is_function and isinstance(value, str):
        return value.strip().upper()
    return str(value)


def _column_matches(actual: Dict[str, Any], spec: Dict[str, Any]) -> bool:
    type_match = _normalize_type(actual.get("COLUMN_TYPE")) == _normalize_type(spec["type"])
    nullable_match = (actual.get("IS_NULLABLE") == "YES") == spec.get("nullable", True)

    default_match = True
    if "default" in spec:
        desired_default = _normalize_default(spec.get("default"), spec.get("default_is_function", False))
        actual_default = actual.get("COLUMN_DEFAULT")
        actual_default_norm = _normalize_default(actual_default, spec.get("default_is_function", False))
        default_match = actual_default_norm == desired_default

    extra_match = True
    required_extra = spec.get("extra")
    actual_extra = (actual.get("EXTRA") or "").lower()
    if required_extra:
        extra_match = required_extra.lower() in actual_extra

    if spec.get("on_update"):
        on_update_expected = f"on update {spec['on_update'].lower()}"
        if spec.get("on_update_is_function"):
            on_update_expected = on_update_expected
        extra_match = extra_match and (on_update_expected in actual_extra)

    return type_match and nullable_match and default_match and extra_match


def _ensure_column(cursor, table_name: str, spec: Tuple[str, Dict[str, Any]], existing_columns: Dict[str, Dict[str, Any]], desired_order: List[str]) -> bool:
    column_name, column_def = spec
    lower_name = column_name.lower()
    if lower_name not in existing_columns:
        clause = _column_definition_sql(column_name, column_def)
        position_clause = "FIRST"
        current_index = desired_order.index(column_name)
        for prev_index in range(current_index - 1, -1, -1):
            prev_col = desired_order[prev_index]
            if prev_col.lower() in existing_columns:
                position_clause = f"AFTER `{prev_col}`"
                break
        cursor.execute(f"ALTER TABLE `{table_name}` ADD COLUMN {clause} {position_clause}")
        print(f"[DB MIGRATION] Added missing column {column_name} to {table_name}")
        return True

    actual = existing_columns[lower_name]
    if not _column_matches(actual, column_def):
        clause = _column_definition_sql(column_name, column_def)
        cursor.execute(f"ALTER TABLE `{table_name}` MODIFY COLUMN {clause}")
        print(f"[DB MIGRATION] Updated column {column_name} on {table_name}")
        return True
    return False


def sync_schema_with_desired(conn, db_name: str) -> bool:
    cursor = conn.cursor()
    alterations_made = False
    for table_name, schema in DESIRED_TABLE_SCHEMAS.items():
        cursor.execute(
            """
            SELECT COUNT(*) FROM information_schema.tables
            WHERE table_schema = %s AND table_name = %s
            """,
            (db_name, table_name),
        )
        exists = cursor.fetchone()[0] > 0
        if not exists:
            cursor.execute(schema["create_sql"])
            print(f"[DB MIGRATION] Created missing table {table_name}")
            alterations_made = True
            continue

        dict_cursor = conn.cursor(dictionary=True)
        dict_cursor.execute(
            """
            SELECT COLUMN_NAME, COLUMN_TYPE, IS_NULLABLE, COLUMN_DEFAULT, EXTRA
            FROM information_schema.columns
            WHERE table_schema = %s AND table_name = %s
            ORDER BY ORDINAL_POSITION
            """,
            (db_name, table_name),
        )
        rows = dict_cursor.fetchall()
        dict_cursor.close()
        existing_columns = {row["COLUMN_NAME"].lower(): row for row in rows}
        desired_order = [name for name, _ in schema.get("columns", [])]
        for column_spec in schema.get("columns", []):
            changed = _ensure_column(cursor, table_name, column_spec, existing_columns, desired_order)
            if changed:
                alterations_made = True
                # refresh metadata for subsequent positioning and comparisons
                dict_cursor = conn.cursor(dictionary=True)
                dict_cursor.execute(
                    """
                    SELECT COLUMN_NAME, COLUMN_TYPE, IS_NULLABLE, COLUMN_DEFAULT, EXTRA
                    FROM information_schema.columns
                    WHERE table_schema = %s AND table_name = %s
                    ORDER BY ORDINAL_POSITION
                    """,
                    (db_name, table_name),
                )
                rows = dict_cursor.fetchall()
                dict_cursor.close()
                existing_columns = {row["COLUMN_NAME"].lower(): row for row in rows}
    cursor.close()
    if alterations_made:
        conn.commit()
    return alterations_made


def migrate():
    # Define the current schema version
    CURRENT_VERSION = 4
    
    try:
        conn = get_connection()
        cursor = conn.cursor()
        db_name = os.environ.get("DB_NAME", os.environ.get("MYSQL_DATABASE", "radmac"))
        
        # Ensure schema_version table exists first
        cursor.execute(CREATE_SCHEMA_VERSION_SQL)
        conn.commit()
        
        # Check for schema drift and reconcile automatically
        drift_fixed = sync_schema_with_desired(conn, db_name)
        if drift_fixed:
            print("[DB MIGRATION] Schema differences detected and patched.")

        # Check current version
        current_version = get_current_schema_version(cursor)
        print(f"[DB MIGRATION] Current schema version: {current_version}")
        
        if current_version >= CURRENT_VERSION:
            print(f"[DB MIGRATION] Schema is up to date (version {current_version}). No migration needed.")
            cursor.close()
            conn.close()
            return
        
        # Create backup before migration
        print(f"[DB MIGRATION] Upgrading schema from version {current_version} to {CURRENT_VERSION}")
        backup_database()
        
        # Apply migrations based on current version
        if current_version < 1:
            # Migration to version 1: ensure auth_users table and column size
            cursor.execute(CREATE_AUTH_USERS_SQL)
            try:
                cursor.execute("ALTER TABLE auth_users MODIFY COLUMN password_hash VARCHAR(255) NOT NULL")
                print("[DB MIGRATION] auth_users.password_hash column updated to VARCHAR(255).")
            except Exception as e:
                # Column might already be correct size or table might not exist yet
                pass
            
            set_schema_version(cursor, 1)
            print("[DB MIGRATION] Upgraded to schema version 1.")

        if current_version < 2:
            # Migration to version 2: monitoring and alert tables
            cursor.execute(CREATE_MONITOR_CHECKS_SQL)
            cursor.execute(CREATE_ALERT_DESTINATIONS_SQL)
            cursor.execute(CREATE_MONITOR_CHECK_DESTINATIONS_SQL)
            cursor.execute(CREATE_MONITOR_CHECK_STATUS_SQL)

            seed_monitor_checks(cursor)

            set_schema_version(cursor, 2)
            print("[DB MIGRATION] Upgraded to schema version 2.")
        if current_version < 3:
            cursor.execute(CREATE_SMTP_SETTINGS_SQL)
            seed_smtp_settings(cursor)
            set_schema_version(cursor, 3)
            print("[DB MIGRATION] Upgraded to schema version 3.")

        if current_version < 4:
            # Migration to version 4: Normalize MAC addresses
            print("[DB MIGRATION] Normalizing MAC addresses in users and auth_logs...")
            try:
                # Disable foreign key checks temporarily just in case
                cursor.execute("SET FOREIGN_KEY_CHECKS=0")
                
                # Normalize users table
                # We use IGNORE to skip duplicates if they exist (though they shouldn't ideally)
                cursor.execute("""
                    UPDATE IGNORE users 
                    SET mac_address = UPPER(REPLACE(REPLACE(REPLACE(mac_address, ':', ''), '-', ''), '.', ''))
                """)
                print(f"[DB MIGRATION] Normalized {cursor.rowcount} rows in users table.")
                
                # Normalize auth_logs table
                cursor.execute("""
                    UPDATE auth_logs 
                    SET mac_address = UPPER(REPLACE(REPLACE(REPLACE(mac_address, ':', ''), '-', ''), '.', ''))
                """)
                print(f"[DB MIGRATION] Normalized {cursor.rowcount} rows in auth_logs table.")
                
                cursor.execute("SET FOREIGN_KEY_CHECKS=1")
                
                set_schema_version(cursor, 4)
                print("[DB MIGRATION] Upgraded to schema version 4.")
                
            except Exception as e:
                print(f"[DB MIGRATION] Error normalizing MACs: {e}")
        
        # Future migrations would go here:
        # if current_version < 2:
        #     # Migration to version 2
        #     cursor.execute("ALTER TABLE users ADD COLUMN new_field VARCHAR(255)")
        #     set_schema_version(cursor, 2)
        #     print("[DB MIGRATION] Upgraded to schema version 2.")
        
        conn.commit()
        cursor.close()
        conn.close()
        print("[DB MIGRATION] Migration completed successfully.")
        
    except Exception as e:
        print(f"[DB MIGRATION] Warning: Could not connect to database: {e}")
        print("[DB MIGRATION] Skipping migration - database may not be ready yet.")
        # Don't exit with error code, let the app start anyway

if __name__ == "__main__":
    migrate()
