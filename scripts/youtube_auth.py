"""
ONE-TIME setup: authenticates with YouTube and saves credentials.
Run this ONCE from any terminal (browser will open for Google login).
Usage: python youtube_auth.py
"""
import os, json
from google_auth_oauthlib.flow import InstalledAppFlow
from google.oauth2.credentials import Credentials

SECRETS_DIR  = r"D:\ShortsPipeline\secrets"
CLIENT_FILE  = os.path.join(SECRETS_DIR, "client_secret.json")
CREDS_FILE   = os.path.join(SECRETS_DIR, "yt_credentials.json")
SCOPES = ["https://www.googleapis.com/auth/youtube.upload",
          "https://www.googleapis.com/auth/youtube"]

os.makedirs(SECRETS_DIR, exist_ok=True)

if not os.path.exists(CLIENT_FILE):
    print("=" * 60)
    print("SETUP REQUIRED")
    print("=" * 60)
    print("1. Go to: https://console.cloud.google.com/")
    print("2. Create a project (or pick existing)")
    print("3. APIs & Services -> Enable APIs -> search 'YouTube Data API v3' -> Enable")
    print("4. APIs & Services -> Credentials -> Create Credentials -> OAuth client ID")
    print("5. Application type: Desktop app  ->  Name: ShortsPipeline  ->  Create")
    print("6. Download JSON -> rename to 'client_secret.json'")
    print(f"7. Save it to: {CLIENT_FILE}")
    print("Then run this script again.")
    raise SystemExit()

print("Opening browser for Google login...")
flow = InstalledAppFlow.from_client_secrets_file(CLIENT_FILE, SCOPES)
creds = flow.run_local_server(port=0, open_browser=True)

with open(CREDS_FILE, "w") as f:
    f.write(creds.to_json())

print(f"\nCredentials saved to: {CREDS_FILE}")
print("YouTube upload is now fully automated.")
