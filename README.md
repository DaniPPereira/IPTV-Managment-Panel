# IPTV Provisioning & Management Panel

Self-hosted web application for managing IPTV clients and provisioning access (M3U, EPG/XMLTV, Xtream-compatible credentials). **This is not a video player and does not proxy streams.**

## Stack

- **Backend:** Python 3.12, FastAPI, SQLAlchemy 2 (async), Alembic, PostgreSQL 16
- **Frontend:** React, TypeScript, Vite, TanStack Query, Tailwind CSS
- **Deploy:** Docker Compose (`postgres`, `backend`, `frontend`, `nginx`)

## Quick start

```bash
cp .env.example .env
# Edit secrets: POSTGRES_PASSWORD, APP_SECRET_KEY, DATA_ENCRYPTION_KEY, ADMIN_INITIAL_PASSWORD

docker compose up -d --build
```

Open [http://localhost](http://localhost) (or the host/port set in `HTTP_PORT` / `PUBLIC_BASE_URL`).

Default admin (first boot only):

- Username: value of `ADMIN_USERNAME` (default `admin`)
- Password: value of `ADMIN_INITIAL_PASSWORD`

Change the initial password after first login.

## What it does

- Create/edit/disable clients and subscriptions
- Store encrypted upstream M3U/EPG URLs
- Issue public tokens for `/m3u/{token}` and `/epg/{token}`
- Xtream-style `/player_api.php` and `/get.php`
- Device/MAC management
- Dashboard, renewals, token regeneration, audit logs, public setup page with QR codes

## Architecture

```
Internet → Nginx → React (admin UI)
                → FastAPI (admin API + public provisioning)
                     → PostgreSQL
                     → Upstream M3U/EPG (fetched server-side, cached)
```

Players receive playlists/credentials from this panel, then connect **directly** to the origin streams. Video is never relayed through this server.

## Useful URLs

| Path | Purpose |
|------|---------|
| `/admin/login` | Admin login |
| `/api/admin/*` | Authenticated admin API |
| `/m3u/{token}` | Public playlist |
| `/epg/{token}` | Public EPG |
| `/player_api.php` | Xtream user/server info |
| `/get.php` | Xtream playlist |
| `/setup/{token}` | Client self-setup page |
| `/stalker_portal/c/` | MAG/STB portal entry |
| `/stalker_portal/server/load.php` | Stalker API (handshake, profile, channels) |
| `/c/` | Alias portal entry |
| `/health` | Health check |

## Configuration

See `.env.example`. Important variables:

- `DATA_ENCRYPTION_KEY` — encrypts source M3U/EPG URLs at rest
- `PUBLIC_BASE_URL` — base URL shown to clients (M3U/EPG/Xtream)
- `ALLOW_PRIVATE_URLS` — allow fetching from private IPs (dev only)
- `M3U_CACHE_SECONDS` / `EPG_CACHE_SECONDS` — filesystem cache TTLs (`iptv_cache` volume)

## Backups

```bash
docker compose exec postgres pg_dump \
  -U iptv \
  iptv > backup.sql

cat backup.sql | docker compose exec -T postgres \
  psql -U iptv iptv
```

## Development

### Backend tests

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pytest
```

### Frontend (local)

```bash
cd frontend
npm install
npm run dev
```

## Security notes

- Source M3U/EPG URLs are encrypted and only returned on authenticated admin endpoints
- Public endpoints never expose upstream credentials from the database fields
- SSRF protection blocks private/link-local destinations unless `ALLOW_PRIVATE_URLS=true`
- Admin session uses JWT in an HttpOnly cookie (not localStorage)
- Postgres and backend ports are not published; only Nginx (80/optional 443)

## Milestone status

- **M1:** Admin login, clients, subscriptions, M3U/EPG public endpoints, dashboard, Docker
- **M2:** Xtream, setup page, QR codes, audit/access logs, regenerate tokens
- **M3:** Devices, MAC normalization, max devices
- **M4:** MAG/Stalker portal (`/stalker_portal/`, `/c/`) with MAC auth, handshake, profile, channels, create_link

## License / usage

Use only with legally authorized IPTV sources. This software provisions access metadata; it does not include media content.
