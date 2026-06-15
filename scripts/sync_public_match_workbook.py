#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import tempfile
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from google.oauth2 import service_account
from googleapiclient.discovery import build

from scripts.export_match_bet_sheets import export_reports
from scripts.upload_match_bet_sheets_to_google import upload_csv_tabs
from src.google_sheets_store import DEFAULT_SOURCE_SPREADSHEETS

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
]

SOURCE_SPREADSHEETS = DEFAULT_SOURCE_SPREADSHEETS

DEFAULT_PUBLIC_WORKBOOK_ID = "1wAT0jpXw3_920kHYfemqFMUXWFgzFpv85mc8GNk_lNY"

def get_credentials(service_account_path: str):
    return service_account.Credentials.from_service_account_file(service_account_path, scopes=SCOPES)

def fetch_sheet_rows(sheets, spreadsheet_id: str) -> list[list[str]]:
    return sheets.spreadsheets().values().get(spreadsheetId=spreadsheet_id, range="A:Z").execute().get("values", [])

def write_local_csv(path: Path, values: list[list[str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        for row in values:
            writer.writerow(row)

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--service-account", default=".secret/googlechat-service-account.json")
    parser.add_argument("--public-workbook-id", default=DEFAULT_PUBLIC_WORKBOOK_ID)
    parser.add_argument("--keep-existing-cells", action="store_true")
    args = parser.parse_args()

    credentials = get_credentials(args.service_account)
    sheets = build("sheets", "v4", credentials=credentials)

    with tempfile.TemporaryDirectory(prefix="wc2026-public-sync-") as tmp_dir:
        data_dir = Path(tmp_dir) / "data"
        output_dir = data_dir / "match_bet_sheets"
        for file_name, spreadsheet_id in SOURCE_SPREADSHEETS.items():
            values = fetch_sheet_rows(sheets, spreadsheet_id)
            write_local_csv(data_dir / file_name, values)

        export_reports(data_dir, output_dir)
        upload_csv_tabs(
            sheets,
            args.public_workbook_id,
            output_dir,
            clear_existing=not args.keep_existing_cells,
            links_csv=data_dir / "match_sheet_links.csv",
        )
        print(f"Synced public workbook: https://docs.google.com/spreadsheets/d/{args.public_workbook_id}")

if __name__ == "__main__":
    main()
