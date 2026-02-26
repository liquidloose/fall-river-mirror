# Plan: Dev vs production mode

Description of how the system should look **after** this change. Use this when implementing (e.g. tomorrow).

## Goal

- **Development**: Full local stack — WordPress + MySQL start with the app; FastAPI talks to local WordPress. Use local URLs in config.
- **Production**: Only FastAPI runs; no local WordPress or MySQL. FastAPI talks to the **live** WordPress instance. Use production URLs in config.

## Two modes

| Aspect | Development | Production |
|--------|-------------|------------|
| **What runs** | mirror-ai (FastAPI) + db (MySQL) + wordpress + my-wpcli + phpmyadmin | mirror-ai (FastAPI) only |
| **WordPress** | Local container (same compose network) | Not started; use live site |
| **MySQL** | Local container | Not started |
| **How to start** | e.g. `docker compose --profile dev up` | e.g. `docker compose up` (no profile) |
| **WORDPRESS_BASE_URL** | Local address (e.g. `http://wordpress:80` from inside container, or host port like `http://localhost:9004` if applicable) | Public URL of live WordPress (e.g. `https://yoursite.com`) |
| **Other env** | Dev-specific if any (e.g. debug, local API keys) | Production values |

## Env / config (no duplication)

Use **one base `.env`** with all shared variables (API keys, ports, DB, etc.). Only the vars that **differ by mode** go in small override files — so you never list everything twice.

- **`.env`** — full set of variables (same for both modes).
- **`.env.dev`** — only overrides for development, e.g.:
  - `WORDPRESS_BASE_URL=http://wordpress:80`
  - `APP_ENV=development`
- **`.env.production`** — only overrides for production, e.g.:
  - `WORDPRESS_BASE_URL=https://your-live-site.com`
  - `APP_ENV=production`

Compose can load multiple `env_file` entries for a service; later files override earlier. So `mirror-ai` gets `env_file: [.env, .env.dev]` when running dev and `[.env, .env.production]` when running prod (e.g. via two small compose override files that each set the right second file). Result: one place for all shared vars, two tiny files with just the 2–3 mode-specific values.

## Docker Compose

- Services that are **dev-only**: `db`, `wordpress`, `my-wpcli`, `phpmyadmin` — add a profile (e.g. `profiles: ["dev"]`) so they only start when the dev profile is used.
- **mirror-ai**: No profile; always runs. Gets `WORDPRESS_BASE_URL` (and optional `APP_ENV`) from the active env file so it knows whether to talk to local or live WordPress.

## After implementation

- README (or this doc) should state:
  - **Dev:** e.g. `docker compose -f docker-compose.yml -f docker-compose.dev.yml --profile dev up` (override adds `env_file: [.env, .env.dev]` for mirror-ai).
  - **Prod:** e.g. `docker compose -f docker-compose.yml -f docker-compose.prod.yml up` (override adds `env_file: [.env, .env.production]` for mirror-ai).
- `.env.sample` = full list; add `.env.dev.example` and `.env.production.example` with only the 2–3 override vars so new setups don’t duplicate.

---

*Use this spec when implementing the dev/production mode.*
