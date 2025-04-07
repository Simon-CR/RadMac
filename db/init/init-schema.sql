-- Create the database if it doesn't exist
CREATE DATABASE IF NOT EXISTS radius;
USE radius;

-- Create the user if it doesn't exist
CREATE USER IF NOT EXISTS 'radiususer'@'%' IDENTIFIED BY 'radiuspass';

-- Grant permissions to the user
GRANT ALL PRIVILEGES ON radius.* TO 'radiususer'@'%';

-- Apply the changes
FLUSH PRIVILEGES;

-- Table for registered users (MAC-based auth)
CREATE TABLE IF NOT EXISTS users (
    mac_address CHAR(12) NOT NULL PRIMARY KEY CHECK (mac_address REGEXP '^[0-9A-Fa-f]{12}$'),
    description VARCHAR(200),
    vlan_id VARCHAR(64) NOT NULL
);

-- Table for auth logs
CREATE TABLE IF NOT EXISTS auth_logs (
    id INT AUTO_INCREMENT PRIMARY KEY,
    mac_address CHAR(12) NOT NULL CHECK (mac_address REGEXP '^[0-9A-Fa-f]{12}$'),
    reply ENUM('Access-Accept', 'Access-Reject', 'Accept-Fallback') NOT NULL,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    result VARCHAR(500) DEFAULT NULL
);

-- Table for MAC vendor caching
CREATE TABLE IF NOT EXISTS mac_vendors (
    mac_prefix CHAR(6) NOT NULL PRIMARY KEY CHECK (mac_prefix REGEXP '^[0-9A-Fa-f]{6}$'),
    vendor_name VARCHAR(255),
    status ENUM('found', 'not_found') DEFAULT 'found',
    last_checked DATETIME DEFAULT CURRENT_TIMESTAMP,
    last_updated DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Table for VLAN groups
CREATE TABLE IF NOT EXISTS groups (
    vlan_id VARCHAR(64) NOT NULL PRIMARY KEY,
    description VARCHAR(200)
);
