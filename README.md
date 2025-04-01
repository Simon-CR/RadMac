
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
CREATE TABLE IF NOT EXISTS rad_description (
    username VARCHAR(64) PRIMARY KEY,
    description TEXT
);

CREATE TABLE IF NOT EXISTS mac_vendor_cache (
    mac_prefix VARCHAR(6) PRIMARY KEY,
    vendor_name VARCHAR(255),
    last_updated TIMESTAMP
);
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