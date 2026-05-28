"""Google authentication helper — shared OAuth2 flow for Gmail, Calendar, Keep."""

from __future__ import annotations

import os
import pickle
from pathlib import Path

from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

from multiagent.config import get_settings

# If modifying scopes, delete token.pickle to re-auth
SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/calendar.readonly",
    "https://mail.google.com/",
]

TOKEN_PATH = Path("credentials/token.pickle")


def get_google_creds():
    """Get or refresh Google OAuth2 credentials. Opens browser on first run."""
    creds = None

    if TOKEN_PATH.exists():
        with open(TOKEN_PATH, "rb") as f:
            creds = pickle.load(f)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            settings = get_settings()
            creds_path = settings.google_credentials_path
            if not os.path.exists(creds_path):
                raise FileNotFoundError(
                    f"Google credentials not found at {creds_path}. "
                    "Download from Google Cloud Console → APIs & Services → Credentials."
                )
            flow = InstalledAppFlow.from_client_secrets_file(creds_path, SCOPES)
            creds = flow.run_local_server(port=0)

        TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(TOKEN_PATH, "wb") as f:
            pickle.dump(creds, f)

    return creds


def get_gmail_service():
    """Get an authenticated Gmail API service."""
    return build("gmail", "v1", credentials=get_google_creds())


def get_calendar_service():
    """Get an authenticated Calendar API service."""
    return build("calendar", "v3", credentials=get_google_creds())
