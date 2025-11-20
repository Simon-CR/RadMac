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
	- Generate a `MONITORING_API_TOKEN` so the app and watchdog share a secret for the monitoring API feed.
	- Point `WATCHDOG_CONFIG_API_URL` at the Flask app directly (e.g., `http://app:8080/monitoring/api/watchdog-config`) and set `WATCHDOG_CONFIG_API_TOKEN` to the same token so the watchdog can pull live config even if nginx is down.
	- (Optional) Set SMTP credentials (`WATCHDOG_SMTP_*`) if you plan to create email destinations in the new monitoring UI.

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

## 📊 Monitoring UI & Alert Destinations

RadMac now ships with a dedicated **Monitoring** page inside the web UI where you can:

- Review DNS resolution, discovered IPs, ping state, and service health for each monitored component (app, nginx, database, radius, and anything else you add).
- Adjust interval cadence, per-service startup delays, enabled actions, and "run now" without restarting containers.
- Assign one or more alert destinations (email, SMTP, webhook, Slack, Teams, Discord, Telegram, Pushbullet, etc.) to each check—all configuration lives in the database.

### How the watchdog consumes the new config

- The Flask app exposes `/monitoring/api/watchdog-config`, protected by `MONITORING_API_TOKEN`.
- Set `WATCHDOG_CONFIG_API_URL` (point it straight at the app container to bypass nginx) and `WATCHDOG_CONFIG_API_TOKEN` in the watchdog environment. The watchdog still reads `watchdog_config.yaml` on boot, but it now refreshes from the API every `WATCHDOG_CONFIG_REFRESH_SECONDS` (default 120s) and falls back to YAML only if the API is unreachable.
- Because the watchdog talks directly to the app, alerts can still be sent even when nginx or other proxy layers are unhealthy.

### Alert destinations & notifications

- Destinations are managed entirely in the UI—no more `.env` sprawl for webhook URLs or SMTP credentials.
- Each destination stores its own headers/payload overrides, so the watchdog can call services like Slack, Discord, Teams, Telegram, Pushbullet, or plain webhooks.
- Email/SMTP destinations can be configured with `email_from`, `email_to`, SMTP host/port/user/password, and TLS preferences. The watchdog uses those values when an assigned check goes unhealthy.

### Startup delays & health history

- Every check tracks `startup_delay_seconds` so you can give services time to warm up before alerts fire (e.g., nginx might wait 75 s, database 90 s).
- The `/health` endpoint now includes the recorded DNS/ping/service results from the monitoring service so external uptime monitors can read the same status that powers the UI.

---

📄 License

---


## � RADIUS Client Allow List

The bundled RADIUS server now supports flexible allow-list entries via the `RADIUS_ALLOWED_CLIENTS`
environment variable. Provide a comma-separated list of values in any of these forms:

- `192.168.1.50` – explicit IP address.
- `switch-01` – hostname (resolved inside the container to one or more IPs).
- `192.168.1.0/24` – CIDR network; any client IP inside the range is accepted.
- `*` / `any` / `0.0.0.0` – wildcard (accepts all clients; useful for labs, not production).
- Append `:secret` to override the default shared secret for that entry, e.g.,
  `192.168.1.50:mysecret` or `10.10.0.0/16:netsecret`.

If `RADIUS_ALLOWED_CLIENTS` is omitted, RadMac automatically attempts to allow localhost plus the
`app`, `nginx`, and `radius` service DNS names. Each hostname is resolved to its current IP so the
Flask test endpoint (`/test_radius`) and other containers can talk to the RADIUS server without
manual IP bookkeeping.



## �📝 Changelog


### v1.3.1 (2025-11-20)
- **RADIUS Server Improvements**:
  - Added support for `Calling-Station-Id` (Attribute 31) for MAC address lookup, prioritizing it over `User-Name`.
  - Implemented automatic MAC address normalization (strips `:`, `-`, `.`, and converts to uppercase) to handle various client formats (e.g., `aa:bb:cc...`).
  - Added robust byte-decoding for RADIUS attributes.
- **Web App & Database**:
  - Added automatic MAC address normalization in the Web UI when adding/updating users.
  - Added Database Migration v4 to automatically normalize all existing MAC addresses in `users` and `auth_logs` tables on startup.
- **Docker**:
  - Updated build process to ensure multi-arch support (`linux/amd64` and `linux/arm64`) for all images.

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