
```markdown
# FreeRADIUS Manager (Phase 1)

A lightweight web UI to manage MAC address-based FreeRADIUS configurations backed by a MariaDB/MySQL database.

## Features
- Add/edit/delete MAC-based users and VLAN assignments
- View Access-Accept and Access-Reject logs
- Lookup MAC vendors using maclookup.app API
- Dynamically populate vendor cache to reduce API usage

---

## Requirements (Phase 1)
- Existing FreeRADIUS installation
- Existing MariaDB or MySQL server with access credentials

### Required Tables
Add the following tables to your RADIUS database:

```sql
CREATE TABLE `rad_description` (
  `id` int(11) unsigned NOT NULL AUTO_INCREMENT,
  `username` char(12) DEFAULT NULL,
  `description` varchar(200) DEFAULT NULL,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

CREATE TABLE `mac_vendor_cache` (
  `mac_prefix` varchar(6) NOT NULL,
  `vendor_name` varchar(255) DEFAULT NULL,
  `status` enum('found','not_found') DEFAULT 'found',
  `last_checked` datetime DEFAULT current_timestamp(),
  `last_updated` datetime DEFAULT current_timestamp(),
  PRIMARY KEY (`mac_prefix`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
```

---

## Getting Started

### 1. Clone this repo
```bash
git clone https://github.com/yourname/freeradius-manager.git
cd freeradius-manager
```

### 2. Configure environment
Create a `.env` file or configure environment variables:

```env
FLASK_SECRET_KEY=super-secret-key
MYSQL_HOST=192.168.1.100
MYSQL_USER=radiususer
MYSQL_PASSWORD=yourpassword
MYSQL_DATABASE=radius
OUI_API_KEY= (leave empty for free tier)
OUI_API_LIMIT_PER_SEC=2
OUI_API_DAILY_LIMIT=10000
```

### 3. Run using Docker Compose
```bash
docker-compose up --build
```

---

## Notes
- The MAC vendor database will auto-populate as addresses are discovered
- Only MAC-based users are supported in this release

---

## Phase 2 Goals
- Integrate FreeRADIUS server into Docker Compose
- Optional MariaDB container
- Provide self-contained stack for local or cloud deployment
```