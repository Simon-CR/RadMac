-- init-schema.sql

-- Create users table
CREATE TABLE IF NOT EXISTS users (
    mac_address CHAR(12) NOT NULL PRIMARY KEY CHECK (mac_address REGEXP '^[0-9A-Fa-f]{12}$'),
    description VARCHAR(200),
    vlan_id VARCHAR(64) NOT NULL
);

-- Create auth_logs table
CREATE TABLE IF NOT EXISTS auth_logs (
    id INT AUTO_INCREMENT PRIMARY KEY,
    mac_address CHAR(12) NOT NULL CHECK (mac_address REGEXP '^[0-9A-Fa-f]{12}$'),
    reply ENUM('Access-Accept', 'Access-Reject', 'Accept-Fallback') NOT NULL,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    result VARCHAR(500) DEFAULT NULL
);

-- Create mac_vendors table
CREATE TABLE IF NOT EXISTS mac_vendors (
    mac_prefix CHAR(6) NOT NULL PRIMARY KEY CHECK (mac_prefix REGEXP '^[0-9A-Fa-f]{6}$'),
    vendor_name VARCHAR(255),
    status ENUM('found', 'not_found') DEFAULT 'found',
    last_checked DATETIME DEFAULT CURRENT_TIMESTAMP,
    last_updated DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS groups (
    vlan_id VARCHAR(64) NOT NULL PRIMARY KEY,
    description VARCHAR(200)
);

-- Create auth_users table for web UI authentication
CREATE TABLE IF NOT EXISTS auth_users (
    id INT AUTO_INCREMENT PRIMARY KEY,
    username VARCHAR(64) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Monitoring configuration tables
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

CREATE TABLE IF NOT EXISTS alert_destinations (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(128) NOT NULL UNIQUE,
    destination_type VARCHAR(32) NOT NULL,
    config_json TEXT NOT NULL,
    enabled TINYINT(1) NOT NULL DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS monitor_check_destinations (
    check_id INT NOT NULL,
    destination_id INT NOT NULL,
    PRIMARY KEY (check_id, destination_id),
    CONSTRAINT fk_monitor_check_destinations_check
        FOREIGN KEY (check_id) REFERENCES monitor_checks(id) ON DELETE CASCADE,
    CONSTRAINT fk_monitor_check_destinations_destination
        FOREIGN KEY (destination_id) REFERENCES alert_destinations(id) ON DELETE CASCADE
);

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

-- Seed default monitor checks
INSERT INTO monitor_checks (
    service_name, display_name, host, health_url, port, check_type,
    interval_seconds, startup_delay_seconds, actions, enabled
) VALUES
('app', 'Web UI / Flask App', 'app', 'http://app:8080/health', 8080, 'app', 30, 60, '["log"]', 1),
('nginx', 'Proxy / Web Entry', 'nginx', 'http://nginx', 80, 'nginx', 30, 75, '["log"]', 1),
('database', 'Database', 'db', 'http://db:8080/health', 3306, 'database', 30, 90, '["log"]', 1),
('radius', 'Radius Server', 'radius', 'http://radius:8080/health', 1812, 'radius', 30, 90, '["log"]', 1)
ON DUPLICATE KEY UPDATE
    display_name = VALUES(display_name),
    host = VALUES(host),
    health_url = VALUES(health_url),
    port = VALUES(port),
    check_type = VALUES(check_type),
    interval_seconds = VALUES(interval_seconds),
    startup_delay_seconds = VALUES(startup_delay_seconds),
    actions = VALUES(actions);

INSERT IGNORE INTO monitor_check_status (check_id)
SELECT id FROM monitor_checks;

INSERT INTO smtp_settings (id, host, port, username, password, use_tls, use_ssl, from_email)
VALUES (1, NULL, 587, NULL, NULL, 1, 0, NULL)
ON DUPLICATE KEY UPDATE
    host = COALESCE(VALUES(host), smtp_settings.host),
    port = VALUES(port),
    username = COALESCE(VALUES(username), smtp_settings.username),
    password = COALESCE(VALUES(password), smtp_settings.password),
    use_tls = VALUES(use_tls),
    use_ssl = VALUES(use_ssl),
    from_email = COALESCE(VALUES(from_email), smtp_settings.from_email);
