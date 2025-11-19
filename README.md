## 🛠️ Config Changes & Upgrade Notes

### Config Versioning
The `watchdog_config.yaml` file now includes a `version` field. When upgrading RadMac, always check the config version and the changelog below. If your config is missing new keys or structure, review the latest `watchdog_config.yaml.example` and update your config as needed.

**Upgrade best practices:**
- Never overwrite your existing `watchdog_config.yaml` during upgrades or deployments.
- Always mount your own config as a volume (see `docker-compose.yml`).
- Review the config change log and update your config if new keys or structure are introduced.

### Config Change Log
- **v1.2.1 (2025-09-02):**
	- Added direct `health_url` for db and radius services
	- Added `version` field and config change log
	- Changed `default_interval` key for clarity

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


## 🩺 Health Endpoints & Watchdog Configuration

### Health Endpoints

RadMac exposes `/health` endpoints for all core services:

- **App**: `/health` (aggregates app, db, and radius status)
- **Database**: `/health` (directly on the db container, port 8080)
- **Radius**: `/health` (directly on the radius container, port 8080)

You can test the app's health endpoint (aggregated) with:

```sh
curl -i http://localhost:8080/health
```

Or test the direct endpoints (from the host):

```sh
curl -i http://localhost:8082/health   # Database
curl -i http://localhost:8083/health   # Radius
```

### Watchdog Configuration: .env vs. YAML

- **watchdog_config.yaml**: Use this file for all per-service health URLs, intervals, and actions. It is version-controlled and should be your primary config for service monitoring.
- **.env**: Use for secrets, notification tokens, and deployment-time overrides. Only set environment variables for values you want to override or keep secret.

**Precedence:**
- If a value is set in `watchdog_config.yaml`, it takes precedence.
- If not set in the config, the watchdog will look for an environment variable (e.g., `WATCHDOG_CHECK_INTERVAL` or `WATCHDOG_CHECK_INTERVAL_APP`).
- If neither is set, the built-in default is used.

**Best Practice:**
- Use `watchdog_config.yaml` for all per-service health checks, intervals, and actions.
- Use `.env` for secrets, notification tokens, and any value you want to override at deployment time without editing the config file.
- Do not duplicate values unless you want override behavior.

---

📄 License

---


## 📝 Changelog


### v1.3.0 (2025-11-19)
- Added a **RADIUS Test** button in the web UI so operators can validate MAC auth flows directly from RadMac.
- Bundled a minimal RADIUS dictionary with the Flask app and added an override (`RADIUS_DICTIONARY_PATH`) so the test endpoint always has access to the necessary attributes.
- Enhanced the bundled RADIUS service to autodetect its dictionary inside Docker/Swarm deployments and log the path it uses, preventing false "dictionary not found" failures.
- Published refreshed multi-arch Docker images (`radmac-app` and `radmac-radius`) containing these updates and the new troubleshooting UX.

### v1.2.1 (2025-09-02)
- Added direct `/health` endpoints to db and radius containers for robust, independent health monitoring
- Updated Dockerfiles to run both main service and health endpoint via supervisord
- Updated `docker-compose.yml` to use HTTP healthchecks for db and radius
- Updated `watchdog_config.yaml` to use direct health endpoints for db and radius
- Documented configuration precedence and best practices for `.env` vs. `watchdog_config.yaml`

### v1.2.0 (2025-09-02)
- Added `/health` API endpoint for service monitoring (see Health Endpoints & Watchdog Configuration section)
- Improved documentation and setup instructions

### v1.1.0
- Previous stable release (see tag v1.1.0 for details)

### v1.0
- Initial public release

---

MIT — do whatever you want, no guarantees.