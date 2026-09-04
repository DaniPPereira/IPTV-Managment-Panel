# IPTV Provisioning & Management Panel

Self-hosted panel for managing IPTV clients and provisioning access (M3U, EPG/XMLTV, Xtream, Stalker/MAG).
**Not a video player and does not proxy live streams.**

Players connect **directly** to the upstream provider after receiving playlists/links from this panel.

## Stack

- Backend: Python 3.12, FastAPI, SQLAlchemy 2 (async), Alembic, PostgreSQL 16
- Frontend: React, TypeScript, Vite, TanStack Query, Tailwind
- Deploy: Docker Compose (`iptv-postgres`, `iptv-backend`, `iptv-frontend`, `iptv-nginx`)

## Quick start

```bash
cp .env.example .env
# Set POSTGRES_PASSWORD, APP_SECRET_KEY, DATA_ENCRYPTION_KEY, ADMIN_INITIAL_PASSWORD
# Set PUBLIC_BASE_URL / STALKER_PORTAL_URL to your public host

docker compose up -d --build
docker compose exec iptv-nginx nginx -t
```

Default admin is created from `ADMIN_USERNAME` / `ADMIN_INITIAL_PASSWORD` on first boot.

## Multi-device policy

You can configure the **same subscription on several devices**.

Simultaneous stream limits are enforced by the **upstream IPTV provider**, not by this panel.

- Do **not** block locally by device count / Device ID / concurrent streams
- MAC is used for Stalker/MAG provisioning identity
- Device ID / serial / UA are stored as metadata for troubleshooting only

## How to use

### 1. Create a client + subscription

Admin → Clients → Create client:

- Name, optional email/phone/notes
- M3U source URL (encrypted at rest)
- Optional EPG source URL
- Expiration
- Optional first device MAC

### 2. Add several devices / MACs

On the client detail page, add one device per box/app:

- Device name
- Type (`MAG`, `ANDROID_TV`, …)
- MAC (`00:1A:79:…`)

Each MAG/Pocket STB uses its own MAC against the same portal URL.

### 3. M3U / EPG URLs

Copied from the client detail page:

- `https://iptv.danielpereira6.pt/m3u/<token>`
- `https://iptv.danielpereira6.pt/epg/<token>`

### 4. Stalker / MAG / Pocket STB

Recommended portal URL:

```text
https://iptv.danielpereira6.pt/c/
```

Also accepted:

- `/stalker_portal/c/`
- `/stalker_portal/server/load.php`
- `/server/load.php`
- `/portal.php`

In the app set:

- Portal: `https://iptv.danielpereira6.pt/c/`
- MAC: the device MAC registered in the panel

## Cloudflare / security

| Surface | Protect with Cloudflare Access? |
|---------|----------------------------------|
| Admin UI (`/`, `/admin/login`, `/api/admin/*`) | Yes |
| Playback (`/m3u/`, `/epg/`, `/c/`, `/stalker_portal/`, `/server/load.php`, `/portal.php`) | **No** — players cannot pass Access |

Rotate provider credentials if they ever appear in logs. Enable `LOG_MASK_PROVIDER_CREDENTIALS=true`.

## Useful env vars

```env
PUBLIC_BASE_URL=https://iptv.danielpereira6.pt
STALKER_PORTAL_URL=https://iptv.danielpereira6.pt/c/
STALKER_CREATE_LINK_PREFIX=none
STALKER_ALLOW_MULTIPLE_DEVICES=true
LOG_MASK_PROVIDER_CREDENTIALS=true
HTTP_PORT=8092
```

`STALKER_CREATE_LINK_PREFIX`: `none` | `ffmpeg` | `auto` — prefixes returned by `create_link`.

## Backups

```bash
docker compose exec iptv-postgres pg_dump -U iptv iptv > backup.sql
cat backup.sql | docker compose exec -T iptv-postgres psql -U iptv iptv
```

## Tests

```bash
cd backend
pip install -r requirements.txt
pytest
```

## License / usage

Use only with legally authorized IPTV sources. This software provisions access metadata; it does not include media content.
