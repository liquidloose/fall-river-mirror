# Configuration Guide

Environment variables are loaded from a **`.env`** file in the project root. The tracked **`.env.sample`** is the reference template—copy it and fill in real values.

For **`fr-mirror-ai`** and **`caddy`**, Compose loads **`.env`** then **`.env.prod`** (when present), so production-only overrides can live in `.env.prod` without editing `.env`.

> **Note:** `.env.sample` has historically repeated some keys (e.g. `WEBSHARE_PROXY_*`, `DEFAULT_YOUTUBE_CHANNEL_URL`, `XAI_API_KEY`). In your real `.env`, define **each variable only once**.

---

## Docker Compose (ports and database)

Used by `docker-compose.yml` for the dev WordPress stack, phpMyAdmin, and API port mapping.

```bash
WEB_PORT=9004
PHP_MYADMIN_PORT=9094
API_PORT=3004

MYSQL_ROOT_PASSWORD=your_mysql_root_password
DB_NAME=your_database_name
DB_USER=your_database_user
DB_PASSWORD=your_database_password
```

The compose file defines the Docker network as **`fr-mirror-bridge`**; a `network=...` line in older samples is not used by this compose file.

---

## WordPress and JWT

**WordPress container (`JWT_AUTH_SECRET_KEY`)** — signing key for the JWT Auth plugin (must match `wp-config.php` / plugin expectations).

```bash
JWT_AUTH_SECRET_KEY=your_jwt_secret_key_here
```

**FastAPI → WordPress REST (`wordpress_sync_service`)** — base URL and JWT used when the API calls WordPress.

```bash
WORDPRESS_BASE_URL=https://yoursite.com
WORDPRESS_JWT_TOKEN=your_wordpress_jwt_token_here
WORDPRESS_JWT_USER=your_wordpress_jwt_user
WORDPRESS_JWT_PASSWORD=your_wordpress_jwt_password
```

Optional path overrides (defaults exist in code): `WORDPRESS_API_PATH_CREATE_ARTICLE`, `WORDPRESS_API_PATH_UPDATE_ARTICLE`, `WORDPRESS_API_PATH_ARTICLE_YOUTUBE_IDS`.

For local dev with the compose WordPress service, `WORDPRESS_BASE_URL` is often `http://wordpress:80` or `http://localhost:${WEB_PORT}` from the host.

**GCP offload (WordPress)** — path to the service account JSON referenced from `wp-config.php`:

```bash
GCP_KEY_FILE_PATH=/code/your-gcp-key-file.json
```

---

## Git identity (AI container startup)

The `fr-mirror-ai` service runs `git config` using:

```bash
GIT_USER_EMAIL=you@example.com
GIT_USER_NAME=your_github_username
```

---

## AI application keys

```bash
XAI_API_KEY=your_xai_api_key_here
OPENAI_API_KEY=your_openai_api_key_here
YOUTUBE_API_KEY=your_youtube_api_key_here
```

**OpenAI** is used for Whisper transcription fallback and for image generation (`OPENAI_API_KEY`); there is no separate `DALLE_API_KEY` in this codebase.

---

## FastAPI database

Passed explicitly into the AI container by Compose:

```bash
DATABASE_URL=sqlite:///fr-mirror.db
```

Tests may override via `pytest.ini`.

---

## Typesense and public search host

```bash
TYPESENSE_API_KEY=your_typesense_api_key_here
# Hostname for Caddy HTTPS in front of Typesense (no scheme, no port). Used when the `caddy` service runs.
TYPESENSE_SEARCH_HOST=your.public.hostname.example
```

Inside Docker, apps reach Typesense at `http://typesense:8108`.

---

## YouTube: channel, transcripts, cookies, OAuth

```bash
DEFAULT_YOUTUBE_CHANNEL_URL=https://www.youtube.com/@YourChannel/videos
YOUTUBE_COOKIES_PATH=/code/youtube_cookies.txt
```

**OAuth paths** (caption/OAuth flows — see `app/data/youtube_oauth.py`):

```bash
YOUTUBE_OAUTH_CREDENTIALS_PATH=/code/client_secret.json
YOUTUBE_OAUTH_TOKEN_PATH=youtube_token.json
```

---

## Webshare proxy

Present in `.env.sample` for egress through Webshare when Google/YouTube blocks datacenter IPs.

```bash
WEBSHARE_PROXY_USERNAME=your_proxy_username
WEBSHARE_PROXY_PASSWORD=your_proxy_password
WEBSHARE_PROXY_HOST=your_proxy_host
# Optional if not using default port:
# WEBSHARE_PROXY_PORT=80
```

**Transcript fetching** (`youtube-transcript-api` in `transcript_manager` / `video_queue_manager`): uses **`WEBSHARE_PROXY_USERNAME`** and **`WEBSHARE_PROXY_PASSWORD`** when both are set.

**Whisper fallback (`yt-dlp`)**: uses **`YOUTUBE_COOKIES_PATH`** when the file exists. **`WEBSHARE_PROXY_HOST` / `WEBSHARE_PROXY_PORT` appear in `.env.sample`; `WhisperProcessor._get_proxy_url()` does not use them yet**, so yt-dlp still uses cookies plus default egress unless you add proxy URL wiring there.

---

## Optional FastAPI toggles (not in `.env.sample`)

```bash
DOCS_SECRET=
QUEUE_BUILD_RATE_LIMIT=5
QUEUE_BUILD_WINDOW_SECONDS=60
```

---

## yt-dlp version / rebuild

If YouTube audio downloads fail or behave oddly, rebuild the AI image so `requirements.txt` pins a current `yt-dlp`:

```bash
docker compose --profile dev build --no-cache fr-mirror-ai
docker compose --profile dev up -d fr-mirror-ai
docker compose --profile dev exec fr-mirror-ai python -m yt_dlp --version
```

(`README.md` may mention older service names; the compose service for the FastAPI app is **`fr-mirror-ai`**.)

---

## Minimal first-time `.env` checklist

1. Copy `.env.sample` → `.env` and remove duplicate keys.
2. Set `YOUTUBE_API_KEY`, `DEFAULT_YOUTUBE_CHANNEL_URL`, and any keys you need for Grok (`XAI_API_KEY`), Whisper fallback (`OPENAI_API_KEY`), and WordPress sync (`WORDPRESS_BASE_URL`, `WORDPRESS_JWT_*`).
3. For Docker AI + Typesense: set `DATABASE_URL`, `TYPESENSE_API_KEY`, and (prod) `TYPESENSE_SEARCH_HOST`.

---

## How `DEFAULT_YOUTUBE_CHANNEL_URL` works

Bulk transcript fetch can rely on the default channel:

```bash
curl -X POST "http://localhost:${API_PORT}/transcript/fetch/25"
```

Override per request:

```bash
curl -X POST "http://localhost:${API_PORT}/transcript/fetch/25" \
  -H "Content-Type: application/json" \
  -d '{"channel_url": "https://www.youtube.com/@DifferentChannel"}'
```

---

## Troubleshooting: "Could not find channel ID"

1. **Logs** — Check `YouTube channels API response: status=..., items_count=..., error=...`.
2. **Channel ID URL** — Use `https://www.youtube.com/channel/UC...` instead of a `@handle` if lookup fails.
3. **Environment** — Ensure `YOUTUBE_API_KEY` is set where the app runs (including `.env.prod` on servers).

---

## Getting API keys

### YouTube Data API v3

1. [Google Cloud Console](https://console.cloud.google.com/apis/credentials) → enable **YouTube Data API v3** → create an API key.

### xAI / Grok

1. [xAI Console](https://console.x.ai/) → create an API key.

### OpenAI (Whisper + images)

1. [OpenAI Platform](https://platform.openai.com/api-keys) → create an API key.
