"""
Upload a video to YouTube (PUBLIC, owner's standing rule) with full metadata.
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


EMOJI = re.compile("[\U0001F300-\U0001FAFF\u2600-\u27BF]")


def title_problems(title):
    """Zack D title format (templates/STYLE_GUIDE.md): 4-7 words, exactly one emoji at the end, no quotes,
    colons, hashtags or ellipses, at most 70 characters."""
    out = []
    words = [w for w in EMOJI.sub("", title).split() if w.strip()]
    if not 4 <= len(words) <= 7:
        out.append(f"{len(words)} words (want 4-7)")
    n = len(EMOJI.findall(title))
    if n != 1:
        out.append(f"{n} emoji (want exactly 1)")
    elif not EMOJI.search(title.rstrip()[-2:]):
        out.append("emoji not at the end")
    bad = [ch for ch in '"\u201c\u201d:#\u2026' if ch in title] + (["..."] if "..." in title else [])
    if bad:
        out.append(f"forbidden characters {bad}")
    if len(title) > 70:
        out.append(f"{len(title)} characters (max 70)")
    return out


def parse_metadata(path):
    lines = open(path, encoding="utf-8").read().splitlines()
    options, description, tags = [], [], []
    section = None
    for i, line in enumerate(lines):
        if re.match(r"TITLE \(pick one", line):
            section = "title"
        elif line.startswith("DESCRIPTION"):
            section = "desc"
        elif line.startswith("TAGS"):
            section = "tags"
        elif line.startswith("UPLOAD SETTINGS") or line.startswith("FACT CHECK"):
            section = None
        elif section == "title":
            m = re.match(r"\d\.\s+(.+)", line)
            if m:
                options.append(m.group(1).strip())
        elif section == "desc" and line.strip():
            description.append(line)
        elif section == "tags" and line.strip():
            raw = line.strip()
            tags = [t.strip() for t in raw.split(",") if t.strip()]
    # first option that meets the title format; otherwise option 1 with a warning (never block the upload)
    title = ""
    for t in options:
        probs = title_problems(t)
        if not probs:
            title = t
            break
        print(f"WARN title format: {t!r}: {'; '.join(probs)}")
    if not title and options:
        title = options[0]
    return title[:100], "\n".join(description), tags


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
            "privacyStatus": "public",    # owner's standing rule (2026-10-27): always public, never private/unlisted
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
    got = (response.get("status") or {}).get("privacyStatus", "?")
    print(f"SUCCESS: https://youtu.be/{video_id} (visibility: {got})")
    if got != "public":
        # YouTube locks uploads from unaudited API projects (created after 2020-07-28) as private.
        print("WARN: YouTube did not make this video public. The Google Cloud API project probably needs the "
              "YouTube API audit; until then upload the MP4 from the Videos folder in YouTube Studio.")
    print(f"Studio: https://studio.youtube.com/video/{video_id}/edit")
    return video_id


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python youtube_upload.py <video.mp4> <metadata.txt>")
        sys.exit(1)
    upload(sys.argv[1], sys.argv[2])
