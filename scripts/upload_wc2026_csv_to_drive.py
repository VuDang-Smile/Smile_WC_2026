#!/usr/bin/env python3
"""Upload WC 2026 betting CSV files to Google Drive.

Requires:
  pip install google-api-python-client google-auth google-auth-oauthlib

Credential options:
  1. --service-account or GOOGLE_APPLICATION_CREDENTIALS service account JSON
  2. OAuth client JSON path via --client-secret, creates token at --token
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google.oauth2 import service_account
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload


SCOPES = ["https://www.googleapis.com/auth/drive.file"]
DEFAULT_FOLDER_ID = "1wUwJNck0WAuR110Jk3tTzjSSHVzGfAO9"
DEFAULT_SERVICE_ACCOUNT = ".secret/googlechat-service-account.json"


def get_credentials(args: argparse.Namespace):
    service_account_path = args.service_account or os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
    if service_account_path and Path(service_account_path).exists():
        return service_account.Credentials.from_service_account_file(
            service_account_path,
            scopes=SCOPES,
        )

    token_path = Path(args.token)
    creds = None
    if token_path.exists():
        creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
    if not creds or not creds.valid:
        flow = InstalledAppFlow.from_client_secrets_file(args.client_secret, SCOPES)
        creds = flow.run_local_server(port=0)
        token_path.parent.mkdir(parents=True, exist_ok=True)
        token_path.write_text(creds.to_json(), encoding="utf-8")
    return creds


def _find_existing_file(service, folder_id: str, name: str) -> dict[str, str] | None:
    escaped_name = name.replace("'", "\\'")
    response = service.files().list(
        q=f"name = '{escaped_name}' and '{folder_id}' in parents and trashed = false",
        fields="files(id,name,webViewLink)",
        supportsAllDrives=True,
        includeItemsFromAllDrives=True,
    ).execute()
    files = response.get("files", [])
    return files[0] if files else None

def upload_csv_files(args: argparse.Namespace) -> None:
    service = build("drive", "v3", credentials=get_credentials(args))
    data_dir = Path(args.data_dir)
    for csv_path in sorted(data_dir.glob("*.csv")):
        metadata = {
            "name": csv_path.name,
            "mimeType": "application/vnd.google-apps.spreadsheet",
        }
        media = MediaFileUpload(str(csv_path), mimetype="text/csv", resumable=False)
        existing = _find_existing_file(service, args.folder_id, csv_path.name)
        if existing:
            updated = service.files().update(
                fileId=existing["id"],
                body=metadata,
                media_body=media,
                fields="id,name,webViewLink",
                supportsAllDrives=True,
            ).execute()
            print(f"UPDATED {updated['name']}: {updated['webViewLink']}")
            continue

        created = service.files().create(
            body={**metadata, "parents": [args.folder_id]},
            media_body=media,
            fields="id,name,webViewLink",
            supportsAllDrives=True,
        ).execute()
        print(f"CREATED {created['name']}: {created['webViewLink']}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", default="data/wc2026_betting")
    parser.add_argument("--folder-id", default=DEFAULT_FOLDER_ID)
    parser.add_argument("--service-account", default=DEFAULT_SERVICE_ACCOUNT)
    parser.add_argument("--client-secret", default=".secret/google_oauth_client.json")
    parser.add_argument("--token", default=".secret/google_oauth_token.json")
    args = parser.parse_args()
    upload_csv_files(args)


if __name__ == "__main__":
    main()
