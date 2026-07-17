# City Agent RISE — AWS Deployment Guide

**RISE** = Replenishment Intelligence & Stock Engine.

Deploy the City Agent RISE operator app (Overview, forecasting, ordering, model management) on a
**single AWS EC2 host** using Docker Compose. Caddy fronts the stack and gets a free TLS
certificate automatically.

```
                          EC2 (single host)
  Internet ──443/80──►  Caddy ──/api/*──►  api  (FastAPI, 1 worker, ODBC→Fabric)
                          │    ──/*──────►  web  (SvelteKit, Node)
                          └ auto-TLS (Let's Encrypt)
  Persisted: appstore volume (SQLite) + ./data ./models ./reports (mounted)
```

---

## 1. Provision the instance

| Item | Value |
|---|---|
| OS | Ubuntu 22.04 / 24.04 |
| Size | **t3.large or bigger** (≥ 8 GB RAM — training + DuckDB need headroom) |
| Disk | 30 GB gp3 |
| Network | **Elastic IP** (stable DNS target) |
| Security group inbound | `22` (SSH), `80`, `443` |
| Outbound | allow `1433` if reading Microsoft Fabric |

---

## 2. Install Docker

```bash
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER && newgrp docker
docker compose version          # confirm Compose v2 plugin
```

---

## 3. Get the code (and data) onto the box

```bash
git clone <your-repo> cfc && cd cfc
```

The stack mounts `./data`, `./models`, `./reports`. You need data by **one** of:

- **Fabric (recommended)** — set `USE_FABRIC=1` + creds (step 4). The app reads results live;
  no big files to ship.
- **Local files** — copy the forecasting artifacts up:
  ```bash
  # from your workstation:
  rsync -avz data models reports ubuntu@<EC2_IP>:~/cfc/
  ```

`.env.prod` is **gitignored** — never commit it; create it fresh (step 4).

---

## 4. Configure `.env.prod`

```bash
cp .env.example .env.prod
python3 -c "import secrets;print(secrets.token_hex(32))"   # → SECRET_KEY
nano .env.prod
```

Set the **production** values:

```ini
APP_ENV=production
SECRET_KEY=<hex from above>
AUTH_DISABLED=0

# public address (real domain → auto-HTTPS)
DOMAIN=cfc.yourcompany.com
ORIGIN=https://cfc.yourcompany.com
ALLOWED_ORIGINS=https://cfc.yourcompany.com
HTTP_PORT=80
HTTPS_PORT=443

# login (superadmin). role=admin. plaintext by design — keep this file out of git.
SUPERADMIN_EMAIL=admin@cityfood.com
SUPERADMIN_PASSWORD=<strong password>
# optional extra users: "email:password:role,..."  role ∈ viewer|ops|finance|admin
AUTH_USERS=
SESSION_DAYS=1
REMEMBER_DAYS=30

# Microsoft Fabric — live reads + notebook jobs (your Entra login)
USE_FABRIC=1
FABRIC_USER=you@yourtenant.com
FABRIC_PASSWORD=<password>          # ActiveDirectoryPassword — MFA must be OFF
FABRIC_TENANT_ID=<tenant guid>
FABRIC_SQL_ENDPOINT=<lakehouse>.datawarehouse.fabric.microsoft.com
FABRIC_SQL_DB=LK_CFC_Sales
FABRIC_SCHEMA=dbo
FABRIC_WORKSPACE_ID=<HUB-AI workspace guid>
FABRIC_NOTEBOOK_ID=<CFC_ML_Pipeline notebook guid>

# in-container training memory guard (keep ON unless the box is large)
CFC_TRAIN_LEAN=1
CFC_MAX_ROWS=1500000

# optional LLM narration (Explain / Autopilot) — OpenRouter only
OPENROUTER_API_KEY=
```

> Boot **fails closed** if `SECRET_KEY` is unset/default or `AUTH_DISABLED=1`. That is intentional.

---

## 5. DNS

Add an **A record**: `cfc.yourcompany.com → <Elastic IP>`. Let it resolve *before* first run so
Caddy can issue the TLS certificate.

No domain yet? Set `DOMAIN=:80`, `HTTP_PORT=80`, drop HTTPS for HTTP-only on the public IP.
Note: the login cookie is `Secure`, so it only sticks over **https** on a real domain — use a
domain + TLS for real use.

---

## 6. Run

**Easiest — one command (recommended, no hand-editing):**
```bash
bash deploy/up.sh          # Nginx front (default)
bash deploy/up.sh caddy    # Caddy front (auto-TLS)
```
It stops any old stack, builds, starts the full stack (front + api + web), and prints the URL.

---

Or run compose directly. Pick a front proxy. **Both give 3 containers (front + api + web); always
reach the app through the front port, never the api port directly.**

**Option A — Caddy (auto-TLS, simplest):**
```bash
docker compose -f docker-compose.prod.yml --env-file .env.prod up -d --build
docker compose -f docker-compose.prod.yml logs -f api      # watch startup
```

**Option B — Nginx:**
```bash
docker compose -f docker-compose.nginx.yml --env-file .env.prod up -d --build
```
Nginx (`deploy/nginx.conf`) publishes `HTTP_PORT` and proxies `/api/*`→api (strips `/api`) and
`/*`→web. Terminate TLS at Nginx yourself (no auto-cert).

> ⚠️ Common mistake: running only api+web (no front) and hitting the api port (e.g. `:8001`) →
> `{"detail":"Not Found"}` — the api has **no `/` page**. Front it with Caddy **or** Nginx and open
> the **front** port (`HTTP_PORT`).

On first boot the API **background-builds the Overview snapshot** (`data/cache/overview.json`)
from Fabric + local files, so the dashboard loads instantly. It does **not** train or extract —
it reads existing results.

---

## 7. Verify

```bash
curl -s https://cfc.yourcompany.com/api/health            # {"ok":true,...}
```

Open `https://cfc.yourcompany.com` → sign in with the superadmin email/password. On **Overview**,
click **Sync live** to pull fresh numbers from Fabric and re-cache.

Check Fabric connected:
```bash
# after logging in (cookie), or with an admin token:
curl -s https://cfc.yourcompany.com/api/workflow/status | grep -o '"fabric":[a-z]*'   # want true
```
If creds are wrong/unreachable the app silently falls back to local parquet (`"fabric":false`).

---

## 8. Day-2 operations

| Task | Command |
|---|---|
| **Deploy code changes** (images are baked — a plain restart serves stale code) | `git pull && docker compose -f docker-compose.prod.yml --env-file .env.prod up -d --build api web` |
| Restart | `docker compose -f docker-compose.prod.yml --env-file .env.prod restart` |
| Stop / start | `... down` / `... up -d` |
| Logs | `docker compose -f docker-compose.prod.yml logs -f` |
| Status | `docker compose -f docker-compose.prod.yml ps` |

**Keep the snapshot fresh automatically** (instead of clicking *Sync live*) — add a nightly cron
that re-pulls from Fabric:
```bash
# /etc/cron.d/cfc-sync
0 3 * * * ubuntu curl -s -X POST -H "X-CFC-Token: <admin-token>" http://localhost/api/overview/sync
```
Issue an admin token inside the api container:
```bash
docker compose -f docker-compose.prod.yml exec api \
  python -c "from deps.auth import make_token; print(make_token('admin', 365, 'admin@cityfood.com'))"
```

---

## 9. Backup

Durable state to back up:
- Docker volume **`appstore`** — SQLite (users, audit, jobs).
- Mounted **`models/`** (champion + registry) and **`data/`** (parquet + cache).

```bash
docker run --rm -v cfc_appstore:/v -v $PWD:/b alpine tar czf /b/appstore-backup.tgz -C /v .
tar czf data-models-backup.tgz data models reports
```

---

## Notes & limits

- **Single node only.** The API runs **one worker** — heavy-run lock + job registry are
  in-process. Scale **up** (bigger instance), not out. Multi-node would need a shared (Redis) lock.
- **Training memory.** In-container LightGBM training is capped by `CFC_TRAIN_LEAN=1` so it doesn't
  OOM (exit −9). Heavy full-fidelity training belongs on Fabric. Raise `CFC_MAX_ROWS` / set
  `CFC_TRAIN_LEAN=0` only on a large box.
- **Secrets.** `.env.prod` holds plaintext credentials — keep it off git, restrict file perms
  (`chmod 600 .env.prod`), rotate `FABRIC_PASSWORD` and the superadmin password periodically.
- **Fabric auth** uses `ActiveDirectoryPassword` (MFA off) with read access to the Lakehouse.

See `../CLAUDE.md` for full app architecture and `../HANDOFF.md` for the ML pipeline runbook.
```
