# Dev vs production mode

How the system is set up after the prod-only compose change.

## Goal

- **Development**: Full local stack — WordPress + MySQL + mirror-ai (FastAPI). FastAPI talks to local WordPress. Use local URLs in `.env`.
- **Production**: mirror-ai (FastAPI) plus prod support services (e.g. Typesense, Caddy); no local WordPress or MySQL. FastAPI talks to the live WordPress instance at fallrivermirror.com. Use production values in `.env.prod`.

## Two modes

| Aspect | Development | Production |
|--------|-------------|------------|
| **What runs** | mirror-ai + db + wordpress + my-wpcli + phpmyadmin (+ shared e.g. Typesense) | mirror-ai + Typesense + Caddy (no WordPress/MySQL) |
| **WordPress** | Local container (same compose network) | Not started; use live site |
| **MySQL** | Local container | Not started |
| **How to start** | `docker compose --profile=dev up` (or `... down`) | `docker compose --profile=prod up` (or `... down`) |
| **Env file** | `.env` (local values, e.g. WORDPRESS_BASE_URL to local IP or `http://wordpress:80`) | `.env.prod` (production values; WORDPRESS_BASE_URL=https://fallrivermirror.com) |

## Env / config

- **`.env`** — used by both modes. Contains all variables for the full stack and mirror-ai (API keys, DB, ports, etc.). For dev, set `WORDPRESS_BASE_URL` to your local WordPress (e.g. `http://wordpress:80` or `http://localhost:9004`).
- **`.env.prod`** — loaded by prod-profile services in [docker-compose.yml](../docker-compose.yml) (e.g. `mirror-ai-prod`, `caddy`) *after* `.env` so it overrides. Contains only the values that differ in production; at minimum `WORDPRESS_BASE_URL=https://fallrivermirror.com`.

Both modes use the same [docker-compose.yml](../docker-compose.yml); pass `--profile=dev` or `--profile=prod` so Compose starts the right services.

## Docker Compose

- **Development**: [docker-compose.yml](../docker-compose.yml) with `--profile=dev` starts the full stack (WordPress, MySQL, dev tooling, `mirror-ai-dev`, shared services such as Typesense). Dev mirror-ai uses `env_file: [.env, .env.dev]`.
- **Production**: Same file with `--profile=prod` starts prod-only services (`mirror-ai-prod`, Caddy, Typesense, etc.) and uses `env_file: [.env, .env.prod]` on those services so `.env.prod` overrides (e.g. `WORDPRESS_BASE_URL`).

## Usage summary

- **Dev:** `docker compose --profile=dev up` or `docker compose --profile=dev down` (from the directory containing `docker-compose.yml` and `.env`).
- **Prod:** `docker compose --profile=prod up` or `docker compose --profile=prod down` (same directory; keep `.env.prod` with production values, including `WORDPRESS_BASE_URL=https://fallrivermirror.com`).
