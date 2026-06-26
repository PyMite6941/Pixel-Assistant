"""
Google Calendar integration for Pixel Assistant.

First-time setup:
  1. Go to https://console.cloud.google.com/
  2. Create a project → enable "Google Calendar API"
  3. Credentials → OAuth 2.0 Client ID → Desktop app → Download JSON
  4. Save the downloaded file as  <project_root>/credentials.json
  5. Run Pixel and use any /calendar command — browser auth opens once.
     Token is saved to src/functionalities/google_token.json for future use.

Requires:
  pip install google-api-python-client google-auth-oauthlib google-auth-httplib2
"""
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

try:
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build
    from googleapiclient.errors import HttpError
except ImportError:
    subprocess.check_call([
        sys.executable, "-m", "pip", "install",
        "google-api-python-client", "google-auth-oauthlib",
        "google-auth-httplib2", "-q",
    ])
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build
    from googleapiclient.errors import HttpError


SCOPES = ["https://www.googleapis.com/auth/calendar"]

_FUNC_DIR     = Path(__file__).parent.parent / "functionalities"
TOKEN_FILE    = _FUNC_DIR / "google_token.json"
CREDS_FILE    = Path(__file__).parent.parent.parent / "credentials.json"


# ── Auth ───────────────────────────────────────────────────────────────────────

def _get_service():
    """Authenticate and return a Calendar API service object."""
    if not CREDS_FILE.exists():
        raise FileNotFoundError(
            f"Google credentials not found at:\n  {CREDS_FILE}\n\n"
            "Setup steps:\n"
            "  1. Visit https://console.cloud.google.com/\n"
            "  2. Create a project → APIs & Services → Enable Google Calendar API\n"
            "  3. Credentials → + Create Credentials → OAuth 2.0 Client ID\n"
            "     (Application type: Desktop app)\n"
            "  4. Download the JSON and save it as 'credentials.json' in the\n"
            "     Pixel Assistant project root.\n"
            "  5. Run any /calendar command again — a browser tab will open once."
        )

    creds = None
    if TOKEN_FILE.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            import webbrowser
            flow = InstalledAppFlow.from_client_secrets_file(str(CREDS_FILE), SCOPES)
            print("\nGoogle Calendar Authorization")
            print("=" * 50)
            print("A browser tab will open. Sign in and grant access.")
            print("=" * 50)
            creds = flow.run_local_server(port=0, open_browser=True)
        _FUNC_DIR.mkdir(exist_ok=True)
        TOKEN_FILE.write_text(creds.to_json(), encoding="utf-8")

    return build("calendar", "v3", credentials=creds)


# ── Events ─────────────────────────────────────────────────────────────────────

def list_events(days: int = 7, max_results: int = 20) -> list[dict]:
    """Return up to max_results events over the next `days` days."""
    service = _get_service()
    now     = datetime.now(timezone.utc)
    end     = now + timedelta(days=days)

    result = service.events().list(
        calendarId="primary",
        timeMin=now.isoformat(),
        timeMax=end.isoformat(),
        maxResults=max_results,
        singleEvents=True,
        orderBy="startTime",
    ).execute()

    return result.get("items", [])


def list_today() -> list[dict]:
    """Return all events today (local midnight to midnight)."""
    service = _get_service()
    local_now = datetime.now().astimezone()
    day_start = local_now.replace(hour=0, minute=0, second=0, microsecond=0)
    day_end   = day_start + timedelta(days=1)

    result = service.events().list(
        calendarId="primary",
        timeMin=day_start.isoformat(),
        timeMax=day_end.isoformat(),
        singleEvents=True,
        orderBy="startTime",
    ).execute()
    return result.get("items", [])


def create_event(
    summary: str,
    start: datetime,
    end: datetime,
    description: str = "",
    location: str = "",
) -> dict:
    """Create a calendar event and return the created event dict."""
    service = _get_service()
    body = {
        "summary": summary,
        "start":   {"dateTime": start.isoformat(), "timeZone": _local_tz()},
        "end":     {"dateTime": end.isoformat(),   "timeZone": _local_tz()},
    }
    if description:
        body["description"] = description
    if location:
        body["location"] = location

    return service.events().insert(calendarId="primary", body=body).execute()


def delete_event(event_id: str) -> None:
    """Delete a calendar event by its ID."""
    service = _get_service()
    service.events().delete(calendarId="primary", eventId=event_id).execute()


def _local_tz() -> str:
    """Return local IANA timezone name, e.g. 'Asia/Bangkok'."""
    try:
        import tzlocal
        return str(tzlocal.get_localzone())
    except Exception:
        return "UTC"


# ── Formatting helpers ─────────────────────────────────────────────────────────

def _fmt_event(ev: dict) -> str:
    start = ev.get("start", {})
    dt_str = start.get("dateTime") or start.get("date", "")
    try:
        if "T" in dt_str:
            dt = datetime.fromisoformat(dt_str)
            time_part = dt.strftime("%a %b %d  %I:%M %p")
        else:
            dt = datetime.fromisoformat(dt_str)
            time_part = dt.strftime("%a %b %d  (all day)")
    except Exception:
        time_part = dt_str

    summary  = ev.get("summary", "(no title)")
    location = ev.get("location", "")
    ev_id    = ev.get("id", "")[:12]
    line     = f"  {time_part}  —  {summary}"
    if location:
        line += f"  [{location}]"
    line += f"  (id: {ev_id})"
    return line


def format_events(events: list[dict], header: str = "") -> str:
    if not events:
        return f"{header}No events found."
    lines = ([header] if header else []) + [_fmt_event(e) for e in events]
    return "\n".join(lines)
