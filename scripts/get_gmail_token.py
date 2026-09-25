"""One-time OAuth consent flow to get GMAIL_REFRESH_TOKEN.

Creates credentials.json from .env vars, opens browser for Google consent
(with authuser=5 to select the 5th Google account), prints the refresh token.
Add it to .env as GMAIL_REFRESH_TOKEN=<token>.

Usage:
  python scripts/get_gmail_token.py
"""

import json
import os
import sys
import tempfile
import webbrowser
from pathlib import Path

# Load .env
env_path = Path(__file__).parent.parent / ".env"
if env_path.exists():
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, value = line.partition("=")
                os.environ[key.strip()] = value.strip()

CLIENT_ID = os.getenv("GMAIL_APP_CLIENT_ID")
CLIENT_SECRET = os.getenv("GMAIL_APP_CLIENT_SECRET")

if not CLIENT_ID or not CLIENT_SECRET:
    print("ERROR: GMAIL_APP_CLIENT_ID and GMAIL_APP_CLIENT_SECRET must be set in .env")
    sys.exit(1)

SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]

# Build credentials.json from env vars
creds_data = {
    "installed": {
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "redirect_uris": ["http://localhost"],
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
    }
}

# Write to temp file
tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8")
json.dump(creds_data, tmp)
tmp.close()

print(f"Created temporary credentials at {tmp.name}")
print("Opening browser for Google OAuth consent with authuser=5...")
print()
print("NOTE: If you see 'Google hasn't verified this app', click:")
print("  Advanced -> Go to [Your App] (unsafe)")
print()

try:
    from google_auth_oauthlib.flow import InstalledAppFlow

    # Monkey-patch webbrowser.open to inject authuser=5 into the OAuth URL
    _orig_open = webbrowser.open

    def _patched_open(url, *args, **kwargs):
        if "accounts.google.com" in url and "authuser" not in url:
            url += "&authuser=5"
            print("Injected authuser=5 into OAuth URL")
        return _orig_open(url, *args, **kwargs)

    webbrowser.open = _patched_open

    flow = InstalledAppFlow.from_client_secrets_file(tmp.name, SCOPES)
    creds = flow.run_local_server(port=8080)

    print()
    print("=" * 60)
    print("SUCCESS! Add this line to your .env file:")
    print("=" * 60)
    print(f"GMAIL_REFRESH_TOKEN={creds.refresh_token}")
    print()
    print("Then you can run:")
    print("  python scripts/gmail_filter_eval.py --send-first 3")

finally:
    os.unlink(tmp.name)
