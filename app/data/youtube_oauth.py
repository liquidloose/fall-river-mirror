"""
YouTube OAuth 2.0 Authentication Module

This module handles OAuth 2.0 authentication for YouTube Data API v3 caption access.
Captions require OAuth 2.0 authentication (not just an API key) because they can be
user-specific.

Requirements:
    - OAuth 2.0 credentials JSON file from Google Cloud Console
    - Set YOUTUBE_OAUTH_CREDENTIALS_PATH environment variable
    - Set YOUTUBE_OAUTH_TOKEN_PATH environment variable for token storage

Example Usage:
    >>> from youtube_oauth import YouTubeOAuth
    >>> oauth = YouTubeOAuth()
    >>> credentials = oauth.get_credentials()
    >>> # Use credentials with YouTube Data API client
"""

import os
import json
import logging
import sys
import http.server
import socketserver
import urllib.parse
from typing import Optional
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.exceptions import RefreshError

logger = logging.getLogger(__name__)

# Scopes required for YouTube Data API v3 captions
SCOPES = ["https://www.googleapis.com/auth/youtube.force-ssl"]


class YouTubeOAuth:
    """
    Handles OAuth 2.0 authentication for YouTube Data API v3 caption access.

    This class manages the OAuth flow, token storage, and token refresh.
    Tokens are stored securely in a file (not in git) and automatically refreshed.
    """

    def __init__(
        self, credentials_path: Optional[str] = None, token_path: Optional[str] = None
    ):
        """
        Initialize YouTube OAuth handler.

        Args:
            credentials_path: Path to OAuth credentials JSON file from Google Cloud Console.
                           If not provided, reads from YOUTUBE_OAUTH_CREDENTIALS_PATH env var.
            token_path: Path to store/load OAuth tokens. If not provided, reads from
                       YOUTUBE_OAUTH_TOKEN_PATH env var.

        Raises:
            ValueError: If credentials_path is not provided or file doesn't exist.
        """
        self.credentials_path = credentials_path or os.getenv(
            "YOUTUBE_OAUTH_CREDENTIALS_PATH"
        )
        self.token_path = token_path or os.getenv(
            "YOUTUBE_OAUTH_TOKEN_PATH", "youtube_token.json"
        )

        if not self.credentials_path:
            raise ValueError(
                "OAuth credentials path is required. Set YOUTUBE_OAUTH_CREDENTIALS_PATH "
                "environment variable or pass credentials_path parameter."
            )

        if not os.path.exists(self.credentials_path):
            raise ValueError(
                f"OAuth credentials file not found: {self.credentials_path}. "
                "Please download credentials from Google Cloud Console."
            )

        logger.info(
            f"YouTube OAuth initialized with credentials: {self.credentials_path}"
        )

    def get_credentials(self) -> Credentials:
        """
        Get valid OAuth 2.0 credentials, refreshing if necessary.

        This method:
        1. Checks for existing stored tokens
        2. Refreshes tokens if expired
        3. Initiates OAuth flow if no tokens exist
        4. Stores tokens for future use

        Returns:
            google.oauth2.credentials.Credentials: Valid OAuth 2.0 credentials

        Raises:
            Exception: If OAuth flow fails or credentials cannot be obtained
        """
        credentials = None

        # Try to load existing tokens
        if os.path.exists(self.token_path):
            try:
                credentials = Credentials.from_authorized_user_file(
                    self.token_path, SCOPES
                )
                logger.debug(f"Loaded existing credentials from {self.token_path}")
            except Exception as e:
                logger.warning(
                    f"Failed to load credentials from {self.token_path}: {str(e)}"
                )

        # Refresh credentials if expired
        if credentials and credentials.expired and credentials.refresh_token:
            try:
                logger.info("Refreshing expired OAuth credentials")
                credentials.refresh(Request())
                self._save_credentials(credentials)
                logger.info("Successfully refreshed OAuth credentials")
            except RefreshError as e:
                logger.warning(
                    f"Failed to refresh credentials: {str(e)}. Starting new OAuth flow."
                )
                credentials = None

        # Start OAuth flow if no valid credentials
        if not credentials or not credentials.valid:
            logger.info("No valid credentials found. Starting OAuth flow...")
            credentials = self._run_oauth_flow()
            self._save_credentials(credentials)
            logger.info("OAuth flow completed. Credentials saved.")

        return credentials

    def _run_oauth_flow(self) -> Credentials:
        """
        Run the OAuth 2.0 authorization flow.

        Uses local server flow with a fixed port (8080) for Docker compatibility.
        The port is exposed in docker-compose so the OAuth redirect callback works.

        Steps:
        1. Authorization URL will be printed to logs
        2. User visits URL in their browser (on host machine)
        3. User authorizes the application
        4. Google redirects to localhost:8080 (which is exposed from container)
        5. Local server receives the authorization code and completes the flow

        Returns:
            google.oauth2.credentials.Credentials: Authorized credentials

        Raises:
            Exception: If OAuth flow fails
        """
        try:
            flow = InstalledAppFlow.from_client_secrets_file(
                self.credentials_path, SCOPES
            )

            # Explicitly set redirect_uri (must match client_secret.json)
            flow.redirect_uri = "http://localhost:8080"

            # Log instructions BEFORE starting the server
            logger.info("=" * 80)
            logger.info(
                "OAuth authorization required. Starting local server on port 8080..."
            )
            logger.info("=" * 80)
            sys.stdout.flush()
            sys.stderr.flush()

            # Generate authorization URL explicitly
            auth_url, _ = flow.authorization_url(
                access_type="offline",
                prompt="consent",
            )

            # Explicitly log the authorization URL
            logger.info("")
            logger.info("=" * 80)
            logger.info("AUTHORIZATION URL (copy and paste this in your browser):")
            logger.info(auth_url)
            logger.info("=" * 80)
            logger.info("")

            # Also print directly to stdout
            print("", flush=True)
            print("=" * 80, flush=True)
            print(
                "AUTHORIZATION URL (copy and paste this in your browser):", flush=True
            )
            print(auth_url, flush=True)
            print("=" * 80, flush=True)
            print("", flush=True)
            sys.stdout.flush()
            sys.stderr.flush()

            # Manual callback handler
            authorization_code = None
            error = None

            class CallbackHandler(http.server.SimpleHTTPRequestHandler):
                def do_GET(self):
                    nonlocal authorization_code, error
                    parsed_path = urllib.parse.urlparse(self.path)
                    query_params = urllib.parse.parse_qs(parsed_path.query)

                    if "code" in query_params:
                        authorization_code = query_params["code"][0]
                        self.send_response(200)
                        self.send_header("Content-type", "text/html")
                        self.end_headers()
                        self.wfile.write(
                            b"<html><body><h1>Authorization successful!</h1>"
                            b"<p>You can close this window and return to the application.</p></body></html>"
                        )
                    elif "error" in query_params:
                        error = query_params["error"][0]
                        self.send_response(400)
                        self.send_header("Content-type", "text/html")
                        self.end_headers()
                        self.wfile.write(
                            f"<html><body><h1>Authorization failed</h1>"
                            f"<p>Error: {error}</p></body></html>".encode()
                        )
                    else:
                        self.send_response(400)
                        self.send_header("Content-type", "text/html")
                        self.end_headers()
                        self.wfile.write(
                            b"<html><body><h1>Invalid request</h1></body></html>"
                        )

                def log_message(self, format, *args):
                    # Suppress default HTTP server logs
                    pass

            # Start local server
            logger.info("Starting local callback server on port 8080...")
            logger.info("Waiting for authorization callback...")
            sys.stdout.flush()

            with socketserver.TCPServer(("", 8080), CallbackHandler) as httpd:
                httpd.timeout = 300  # 5 minute timeout
                httpd.handle_request()  # Handle one request (the callback)

            if error:
                raise Exception(f"OAuth authorization error: {error}")

            if not authorization_code:
                raise Exception("No authorization code received. Please try again.")

            # Exchange authorization code for tokens
            logger.info("Received authorization code, exchanging for tokens...")
            flow.fetch_token(code=authorization_code)
            credentials = flow.credentials

            logger.info("OAuth flow completed successfully")
            return credentials
        except Exception as e:
            logger.error(f"OAuth flow failed: {str(e)}")
            raise Exception(
                f"Failed to complete OAuth flow: {str(e)}. "
                "Please ensure credentials file is valid and you have internet access. "
                "Also verify that port 8080 is exposed in docker-compose.yml."
            ) from e

    def _save_credentials(self, credentials: Credentials) -> None:
        """
        Save credentials to token file.

        Args:
            credentials: OAuth credentials to save
        """
        try:
            # Create directory if it doesn't exist
            token_dir = os.path.dirname(self.token_path)
            if token_dir and not os.path.exists(token_dir):
                os.makedirs(token_dir, exist_ok=True)

            # Save credentials
            with open(self.token_path, "w") as token_file:
                token_file.write(credentials.to_json())
            logger.debug(f"Saved credentials to {self.token_path}")
        except Exception as e:
            logger.error(f"Failed to save credentials: {str(e)}")
            # Don't raise - credentials are still valid in memory
