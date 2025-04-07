🛡️ RadMac — Web Manager and radius server for MAC-based authentication / VLAN Assignment
RadMac is a lightweight Flask web UI for managing MAC address-based access control and VLAN assignment, backed by a MariaDB/MySQL database. It incorporate a lightweight radius server.

✨ Features

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

📄 License
MIT — do whatever you want, no guarantees.