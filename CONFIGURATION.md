# Configuration Guide

## Environment Variables

This application uses environment variables for configuration. Create a `.env` file in the project root with the following variables:

### Required Variables

#### YouTube API Configuration
```bash
# Get your API key at: https://console.cloud.google.com/apis/credentials
YOUTUBE_API_KEY=your_youtube_api_key_here
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

