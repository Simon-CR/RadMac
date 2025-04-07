FreeRADIUS Manager
A lightweight web UI to manage MAC-based FreeRADIUS configurations, backed by a MySQL/MariaDB database and integrated with maclookup.app for vendor resolution.

✨ Features
Manage MAC-based users (add/edit/delete)

Assign users to VLANs via group mapping

View Access-Accept, Access-Reject, and Fallback logs

Filter logs by time range (e.g. last 5 min, last day)

Vendor lookup for MAC addresses (with local caching)

Asynchronous background updates to reduce API hits

Manual MAC vendor lookup with detailed results

Pagination for log history and user/group lists

Dark/light theme toggle, scroll position memory, and toasts

Admin actions to clean stale vendors and logs (planned)

🧱 Requirements
Existing FreeRADIUS installation with a compatible schema

Existing MariaDB or MySQL server

maclookup.app API key (optional, for vendor lookup)

🗃️ Required Tables
Make sure your database includes the following tables:

sql
Copy
Edit
CREATE TABLE `users` (
  `mac_address` VARCHAR(17) PRIMARY KEY,
  `description` VARCHAR(255),
  `vlan_id` INT
);

CREATE TABLE `groups` (
  `vlan_id` INT PRIMARY KEY,
  `description` VARCHAR(255)
);

CREATE TABLE `auth_logs` (
  `id` INT AUTO_INCREMENT PRIMARY KEY,
  `mac_address` VARCHAR(17),
  `reply` ENUM('Access-Accept','Access-Reject','Access-Fallback'),
  `result` TEXT,
  `timestamp` DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE `mac_vendors` (
  `mac_prefix` VARCHAR(6) PRIMARY KEY,
  `vendor_name` VARCHAR(255),
  `status` ENUM('found', 'not_found') DEFAULT 'found',
  `last_checked` DATETIME,
  `last_updated` DATETIME
);
⚙️ Configuration
Environment variables (via .env or Docker Compose):

OUI_API_URL: MAC vendor API URL (default: https://api.maclookup.app/v2/macs/{})

OUI_API_KEY: API key for maclookup.app

OUI_API_LIMIT_PER_SEC: API rate limit per second (default: 2)

OUI_API_DAILY_LIMIT: Max API calls per day (default: 10000)

APP_TIMEZONE: Display timezone (e.g., America/Toronto)

🚀 Usage
Run with Docker Compose or your preferred WSGI stack

Navigate to / for the dashboard

Browse /users, /groups, and /stats for more details