"""
Upload a video to YouTube with full metadata.
Usage: python youtube_upload.py <video.mp4> <metadata.txt>
Credentials must be set up first via: python youtube_auth.py
"""
import sys, os, json, re
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request

CREDS_FILE = r"D:\ShortsPipeline\secrets\yt_credentials.json"
SCOPES = ["https://www.googleapis.com/auth/youtube.upload",
          "https://www.googleapis.com/auth/youtube"]


def load_creds():
    if not os.path.exists(CREDS_FILE):
        print("ERROR: No credentials found. Run youtube_auth.py first.")
        sys.exit(1)
    creds = Credentials.from_authorized_user_file(CREDS_FILE, SCOPES)
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        with open(CREDS_FILE, "w") as f:
            f.write(creds.to_json())
    return creds


def parse_metadata(path):
    lines = open(path, encoding="utf-8").read().splitlines()
    title, description, tags = "", [], []
    section = None
    for i, line in enumerate(lines):
        if re.match(r"TITLE \(pick one", line):
            # First recommended title
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r"1\.\s+(.+)", lines[j])
                if m:
                    title = m.group(1).strip()
                    break
        elif line.startswith("DESCRIPTION"):
            section = "desc"
        elif line.startswith("TAGS"):
            section = "tags"
        elif line.startswith("UPLOAD SETTINGS") or line.startswith("FACT CHECK"):
            section = None
        elif section == "desc" and line.strip():
            description.append(line)
        elif section == "tags" and line.strip():
            raw = line.strip()
            tags = [t.strip() for t in raw.split(",") if t.strip()]
    return title, "\n".join(description), tags


def upload(video_path, metadata_path):
    title, description, tags = parse_metadata(metadata_path)
    if not title:
        title = os.path.splitext(os.path.basename(video_path))[0]

    print(f"Uploading: {title}")
    print(f"File: {video_path} ({os.path.getsize(video_path) // 1024 // 1024} MB)")

    creds = load_creds()
    yt = build("youtube", "v3", credentials=creds)

    body = {
        "snippet": {
            "title": title,
            "description": description,
            "tags": tags,
            "categoryId": "27",   # Education
            "defaultLanguage": "en",
        },
        "status": {
            "privacyStatus": "private",   # private first — review before publishing
            "selfDeclaredMadeForKids": False,
            "containsSyntheticMedia": True,
        },
    }

    media = MediaFileUpload(video_path, chunksize=10 * 1024 * 1024, resumable=True)
    request = yt.videos().insert(part="snippet,status", body=body, media_body=media)

    response = None
    while response is None:
        status, response = request.next_chunk()
        if status:
            pct = int(status.progress() * 100)
            print(f"  Upload {pct}%")

    video_id = response["id"]
    print(f"SUCCESS: https://youtu.be/{video_id}")
    print(f"Studio: https://studio.youtube.com/video/{video_id}/edit")
    return video_id


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python youtube_upload.py <video.mp4> <metadata.txt>")
        sys.exit(1)
    upload(sys.argv[1], sys.argv[2])
