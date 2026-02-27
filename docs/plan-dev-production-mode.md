# Dev vs production mode

How the system is set up after the prod-only compose change.

## Goal

- **Development**: Full local stack — WordPress + MySQL + mirror-ai (FastAPI). FastAPI talks to local WordPress. Use local URLs in `.env`.
- **Production**: Only mirror-ai (FastAPI) runs; no local WordPress or MySQL. FastAPI talks to the live WordPress instance at fallrivermirror.com. Use production values in `.env.prod`.

## Two modes

| Aspect | Development | Production |
|--------|-------------|------------|
| **What runs** | mirror-ai + db + wordpress + my-wpcli + phpmyadmin | mirror-ai only |
| **WordPress** | Local container (same compose network) | Not started; use live site |
| **MySQL** | Local container | Not started |
| **How to start** | `docker compose up` | `docker compose -f docker-compose.prod.yml up` |
| **Env file** | `.env` (local values, e.g. WORDPRESS_BASE_URL to local IP or `http://wordpress:80`) | `.env.prod` (production values; WORDPRESS_BASE_URL=https://fallrivermirror.com) |

## Env / config

- **`.env`** — used by both modes. Contains all variables for the full stack and mirror-ai (API keys, DB, ports, etc.). For dev, set `WORDPRESS_BASE_URL` to your local WordPress (e.g. `http://wordpress:80` or `http://localhost:9004`).
- **`.env.prod`** — used only by [docker-compose.prod.yml](../docker-compose.prod.yml), loaded *after* `.env` so it overrides. Contains only the values that differ in production; at minimum `WORDPRESS_BASE_URL=https://fallrivermirror.com`.

No override compose for dev; production is a standalone compose file with its own env file.

## Docker Compose

- **Development**: [docker-compose.yml](../docker-compose.yml) defines the full stack. mirror-ai uses `env_file: .env`.
- **Production**: [docker-compose.prod.yml](../docker-compose.prod.yml) defines only the mirror-ai service and uses `env_file: [.env, .env.prod]` so `.env.prod` overrides (e.g. WORDPRESS_BASE_URL). No merge with the base compose file.

## Usage summary

- **Dev:** `docker compose up` (from the directory containing docker-compose.yml and .env).
- **Prod:** `docker compose -f docker-compose.prod.yml up` (use .env.prod with production values, including WORDPRESS_BASE_URL=https://fallrivermirror.com).
