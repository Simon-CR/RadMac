🛡️ RadMac v1.1 — Web Manager and radius server for MAC-based authentication / VLAN Assignment
RadMac is a lightweight Flask web UI for managing MAC address-based access control and VLAN assignment, backed by a MariaDB/MySQL database. It incorporate a lightweight radius server.

✨ New in v1.1: Authentication System

🔐 Web UI Authentication
- Secure login system for web interface access
- User enrollment on first access (if no users exist)
- Username and password management
- Session-based authentication with Flask-Login

🔑 Access Control
- Homepage accessible without authentication
- All management features protected by login
- User menu for account management (change username/password)

✨ Other Features

🔐 MAC-based User Management
Add/edit/delete MAC entries with descriptions and VLAN IDs.

🧠 MAC Vendor Lookup
Auto-lookup vendors using maclookup.app with rate-limited API integration and local caching.

📊 Auth Log Viewer
Filter Access-Accept / Reject / Fallback events with timestamps, MAC, vendor, and description.

🧹 Database Maintenance Tools
- View row counts for all tables
- Clear auth logs
- Backup the full database as a .sql file
- Restore from uploaded .sql files

🌗 Dark & Light Theme
Toggle between light and dark modes, with theme persistence.

🔁 Session-Friendly UX
Preserves scroll position, sticky headers, toast notifications.

📦 Setup (Docker Compose)
The project includes a ready-to-use docker-compose.yml.

⚠️ **Version 1.1 Upgrade Note**: This version introduces web authentication. On first access, you'll be prompted to create an admin user account. Existing installations will automatically migrate the database schema.

1. Clone the repository
bash
Copy
Edit
git clone https://github.com/Simon-CR/RadMac.git
cd RadMac

2. Create environment file
Copy .env.template to .env and edit:

- Fill in your MySQL credentials and other optional settings like OUI_API_KEY.

3. Run the stack

docker-compose up --build

The web UI will be available at: http://localhost:8080

� Database Management

**Authentication Users**
To manage authentication users directly via database (if needed):

```sql
-- Connect to database
docker exec -it radmac-db-1 mysql -u radmac -p radmac

-- View current auth users
SELECT id, username FROM auth_users;

-- Remove all auth users (forces re-enrollment)
DELETE FROM auth_users;

-- Remove specific user by username
DELETE FROM auth_users WHERE username = 'your_username';
```

**Database Backup & Restore**
The web UI includes maintenance tools for database operations, or use Docker directly:

```bash
# Backup database
docker exec radmac-db-1 mysqldump -u radmac -p radmac > backup.sql

# Restore database
docker exec -i radmac-db-1 mysql -u radmac -p radmac < backup.sql
```

�📄 License
MIT — do whatever you want, no guarantees.