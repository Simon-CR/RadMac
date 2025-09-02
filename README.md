🛡️ RadMac — Web Manager and radius server for MAC-based authentication / VLAN Assignment
RadMac is a lightweight Flask web UI for managing MAC address-based access control and VLAN assignment, backed by a MariaDB/MySQL database. It incorporate a lightweight radius server.

✨ Some Features

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

git clone https://github.com/Simon-CR/RadMac.git
docker-compose up --build

📦 Setup (Docker Compose)
The project includes a ready-to-use docker-compose.yml.

1. Clone the repository
	git clone https://github.com/Simon-CR/RadMac.git
	cd RadMac

2. Create environment file
	Copy .env.template to .env and edit:
	- Fill in your MySQL credentials and other optional settings like OUI_API_KEY.

3. Run the stack
	docker-compose up --build
	The web UI will be available at: http://localhost:8080

---

## 🩺 Health API

RadMac exposes a `/health` endpoint for monitoring the status of all core services (app, database, radius, etc). This endpoint returns a JSON object with per-service health and a global status, e.g.:

```json
{
  "message": "All services are operational",
  "services": {
	 "app": {"message": "Flask application is running", "status": "healthy"},
	 "database": {"message": "Database connection successful", "status": "healthy"},
	 "radius": {"message": "RADIUS server host radius is reachable", "status": "healthy"}
  },
  "status": "healthy",
  "timestamp": "2025-09-02T12:47:41.597104Z"
}
```

You can test the health endpoint with:

```sh
curl -i http://localhost:8080/health
```

This endpoint is designed for use with external monitoring tools, load balancers, or the built-in watchdog (see separate documentation).

📄 License
MIT — do whatever you want, no guarantees.