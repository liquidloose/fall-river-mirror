# Configuration Guide

## Environment Variables

This application uses environment variables for configuration. Create a `.env` file in the project root with the following variables:

### Required Variables

#### YouTube API Configuration
```bash
# Get your API key at: https://console.cloud.google.com/apis/credentials
YOUTUBE_API_KEY=your_youtube_api_key_here

# OAuth 2.0 credentials for caption access (required for transcript fetching)
# Download from Google Cloud Console -> APIs & Services -> Credentials -> Create OAuth 2.0 Client ID
YOUTUBE_OAUTH_CREDENTIALS_PATH=/path/to/credentials.json

# OAuth token storage path (tokens are stored here after first authorization)
YOUTUBE_OAUTH_TOKEN_PATH=youtube_token.json
```

#### Default YouTube Channel
```bash
# Default channel for automatic transcript queue building
# Used by /transcript/fetch/{amount} endpoint when channel_url not explicitly provided
# Example: https://www.youtube.com/@FallRiverCityCouncil
DEFAULT_YOUTUBE_CHANNEL_URL=https://www.youtube.com/@YourChannelHandle
```

### Optional Variables

#### xAI/Grok API (for article generation)
```bash
XAI_API_KEY=your_xai_api_key_here
```

#### OpenAI API (for Whisper transcription fallback)
```bash
OPENAI_API_KEY=your_openai_api_key_here
```

#### DALL-E API (for image generation)
```bash
DALLE_API_KEY=your_dalle_api_key_here
```

#### WordPress sync (create-article, update-article, repair featured image)
```bash
WORDPRESS_BASE_URL=https://yoursite.com
WORDPRESS_JWT_TOKEN=your_jwt_here
```
The app calls WordPress at `WORDPRESS_BASE_URL` + `/wp-json/fr-mirror/v2/...` (create-article, update-article, article-youtube-ids). **The theme's `/includes` that register these REST routes are not in this repo** (submodule or separate deploy). If that code is missing, WordPress returns **404** and we return **404** to the client—no success. Success from our side only when WordPress actually returns 2xx.

#### Webshare proxy (cloud/VPS – YouTube blocks datacenter IPs)
Transcript checks and transcript API use `WEBSHARE_PROXY_USERNAME` and `WEBSHARE_PROXY_PASSWORD` only.  
For Whisper fallback (yt-dlp), you can optionally set `WEBSHARE_PROXY_HOST` and `WEBSHARE_PROXY_PORT` (one proxy IP from your Webshare list) so audio downloads go through the proxy.

## Setting Up Your .env File

1. Copy the example below to a new file named `.env` in the project root:
   ```bash
   YOUTUBE_API_KEY=your_youtube_api_key_here
   DEFAULT_YOUTUBE_CHANNEL_URL=https://www.youtube.com/@FallRiverCityCouncil
   XAI_API_KEY=your_xai_api_key_here
   OPENAI_API_KEY=your_openai_api_key_here
   ```

2. Replace the placeholder values with your actual API keys

3. For Fall River local news, set:
   ```bash
   DEFAULT_YOUTUBE_CHANNEL_URL=https://www.youtube.com/@FallRiverCityCouncil
   ```

## How DEFAULT_YOUTUBE_CHANNEL_URL Works

When you call the bulk transcript fetch endpoint:

```bash
# Simple call - uses DEFAULT_YOUTUBE_CHANNEL_URL from .env
curl -X POST "http://localhost:8001/transcript/fetch/25"
```

The endpoint will:
1. Check if queue has at least 25 videos
2. If not, automatically build queue from `DEFAULT_YOUTUBE_CHANNEL_URL`
3. Fetch up to 25 transcripts

You can override the default channel for a specific request:

```bash
# Override with a different channel
curl -X POST "http://localhost:8001/transcript/fetch/25" \
  -H "Content-Type: application/json" \
  -d '{"channel_url": "https://www.youtube.com/@DifferentChannel"}'
```

## Troubleshooting: "Could not find channel ID"

If the pipeline or queue build fails with `Could not find channel ID for: https://www.youtube.com/@...`:

1. **Check logs** – The app logs the YouTube API response: `YouTube channels API response: status=..., items_count=..., error=...`. If `error` is set, that’s the reason (e.g. quota, forbidden). If `items_count=0`, the API returned no channel for that handle.
2. **Use the channel ID URL** – To avoid handle lookup, set `DEFAULT_YOUTUBE_CHANNEL_URL` to the direct channel URL: `https://www.youtube.com/channel/UCxxxxxxxxxxxxxxxxxx` (get the ID from the channel page or from the logs once lookup works).
3. **Prod env** – Ensure `YOUTUBE_API_KEY` is set in the environment used by the running app (e.g. in `.env.prod` or the prod compose env), and that YouTube Data API v3 is enabled and has quota in Google Cloud.

## Getting API Keys

### YouTube Data API v3
1. Go to [Google Cloud Console](https://console.cloud.google.com/apis/credentials)
2. Create a new project or select existing
3. Enable "YouTube Data API v3"
4. Create credentials → API Key
5. Copy the key to your `.env` file

### xAI/Grok API
1. Visit [xAI Console](https://console.x.ai/)
2. Create an API key
3. Copy to `.env` file

### OpenAI API (Whisper & DALL-E)
1. Visit [OpenAI Platform](https://platform.openai.com/api-keys)
2. Create an API key
3. Copy to `.env` file

