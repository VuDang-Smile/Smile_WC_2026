#!/usr/bin/env python3
"""Upload per-match bet CSV reports into one Google Sheets workbook."""

from __future__ import annotations

import argparse
import csv
import os
from pathlib import Path

from google.oauth2 import service_account
from googleapiclient.discovery import build


SCOPES = [
    "https://www.googleapis.com/auth/drive.file",
    "https://www.googleapis.com/auth/spreadsheets",
]
DEFAULT_SERVICE_ACCOUNT = ".secret/googlechat-service-account.json"
DEFAULT_CSV_DIR = "data/wc2026_betting/match_bet_sheets"
DEFAULT_SPREADSHEET_NAME = "Smile Bet - WC 2026 - Match Bets"
DEFAULT_LINKS_CSV = "data/wc2026_betting/match_sheet_links.csv"


def get_credentials(service_account_path: str):
    path = service_account_path or os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
    if not path or not Path(path).exists():
        raise FileNotFoundError("Missing service account JSON. Use --service-account or GOOGLE_APPLICATION_CREDENTIALS.")
    return service_account.Credentials.from_service_account_file(path, scopes=SCOPES)


def find_spreadsheet_id(drive, name: str) -> str:
    escaped = name.replace("'", "\\'")
    query = (
        "mimeType='application/vnd.google-apps.spreadsheet' "
        f"and name='{escaped}' and trashed=false"
    )
    response = drive.files().list(
        q=query,
        spaces="drive",
        fields="files(id,name,webViewLink)",
        supportsAllDrives=True,
        includeItemsFromAllDrives=True,
    ).execute()
    files = response.get("files", [])
    if not files:
        raise ValueError(f"Spreadsheet not found: {name}")
    if len(files) > 1:
        names = ", ".join(f"{item['name']}:{item['id']}" for item in files)
        raise ValueError(f"Multiple spreadsheets found. Use --spreadsheet-id. Matches: {names}")
    return files[0]["id"]


def read_csv_values(path: Path) -> list[list[str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return [row for row in csv.reader(handle)]


def sheet_title(csv_path: Path) -> str:
    if csv_path.name == "00_index.csv":
        return "00_index"
    return csv_path.stem[:100]

def write_match_sheet_links(path: Path, spreadsheet_id: str, sheets_metadata: list[dict[str, object]]) -> None:
    rows = []
    for sheet in sheets_metadata:
        properties = sheet.get("properties", {})
        title = str(properties.get("title", ""))
        if not title.startswith("WC2026-") and title != "WC2026-FINAL":
            continue
        gid = str(properties.get("sheetId", ""))
        rows.append(
            {
                "match_id": title,
                "spreadsheet_id": spreadsheet_id,
                "sheet_gid": gid,
                "sheet_url": f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}/edit#gid={gid}",
            }
        )

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["match_id", "spreadsheet_id", "sheet_gid", "sheet_url"])
        writer.writeheader()
        writer.writerows(sorted(rows, key=lambda row: row["match_id"]))

def rgb(red: int, green: int, blue: int) -> dict[str, float]:
    return {
        "red": red / 255,
        "green": green / 255,
        "blue": blue / 255,
    }

def bordered_sides(color: dict[str, float], style: str = "SOLID") -> dict[str, object]:
    border = {"style": style, "colorStyle": {"rgbColor": color}}
    return {
        "borders": {
            "top": border,
            "bottom": border,
            "left": border,
            "right": border,
        }
    }

def row_range(sheet_id: int, start: int, end: int, start_col: int = 0, end_col: int = 11) -> dict[str, object]:
    return {
        "sheetId": sheet_id,
        "startRowIndex": start,
        "endRowIndex": end,
        "startColumnIndex": start_col,
        "endColumnIndex": end_col,
    }

def build_match_sheet_format_requests(sheet_id: int, values: list[list[str]]) -> list[dict[str, object]]:
    if not values:
        return []

    requests: list[dict[str, object]] = [
        {
            "updateSheetProperties": {
                "properties": {
                    "sheetId": sheet_id,
                    "gridProperties": {"frozenRowCount": 1},
                },
                "fields": "gridProperties.frozenRowCount",
            }
        },
        {
            "repeatCell": {
                "range": row_range(sheet_id, 0, 1),
                "cell": {
                    "userEnteredFormat": {
                        "backgroundColorStyle": {"rgbColor": rgb(32, 33, 36)},
                        "textFormat": {"bold": True, "foregroundColorStyle": {"rgbColor": rgb(255, 255, 255)}},
                        "horizontalAlignment": "CENTER",
                    }
                },
                "fields": "userEnteredFormat(backgroundColorStyle,textFormat,horizontalAlignment)",
            }
        },
        {
            "updateDimensionProperties": {
                "range": {"sheetId": sheet_id, "dimension": "COLUMNS", "startIndex": 0, "endIndex": 11},
                "properties": {"pixelSize": 140},
                "fields": "pixelSize",
            }
        },
        {
            "updateDimensionProperties": {
                "range": {"sheetId": sheet_id, "dimension": "COLUMNS", "startIndex": 2, "endIndex": 3},
                "properties": {"pixelSize": 220},
                "fields": "pixelSize",
            }
        },
        {
            "updateDimensionProperties": {
                "range": {"sheetId": sheet_id, "dimension": "COLUMNS", "startIndex": 3, "endIndex": 5},
                "properties": {"pixelSize": 240},
                "fields": "pixelSize",
            }
        },
        {
            "updateDimensionProperties": {
                "range": {"sheetId": sheet_id, "dimension": "COLUMNS", "startIndex": 7, "endIndex": 10},
                "properties": {"pixelSize": 110},
                "fields": "pixelSize",
            }
        },
        {
            "updateDimensionProperties": {
                "range": {"sheetId": sheet_id, "dimension": "COLUMNS", "startIndex": 10, "endIndex": 11},
                "properties": {"pixelSize": 180},
                "fields": "pixelSize",
            }
        },
    ]

    section_fill = rgb(232, 240, 254)
    header_fill = rgb(243, 244, 246)
    border_color = rgb(189, 193, 198)
    title_fill = rgb(219, 68, 55)

    for row_index, row in enumerate(values[1:], start=1):
        section = row[0] if len(row) > 0 else ""
        member_id = row[1] if len(row) > 1 else ""
        if section == "THÔNG TIN TRẬN":
            requests.append(
                {
                    "repeatCell": {
                        "range": row_range(sheet_id, row_index, row_index + 1),
                        "cell": {
                            "userEnteredFormat": {
                                "backgroundColorStyle": {"rgbColor": title_fill},
                                "textFormat": {"bold": True, "foregroundColorStyle": {"rgbColor": rgb(255, 255, 255)}},
                                "wrapStrategy": "WRAP",
                            }
                        },
                        "fields": "userEnteredFormat(backgroundColorStyle,textFormat,wrapStrategy)",
                    }
                }
            )
            continue

        if section in {"KÈO THẮNG/THUA", "KÈO TỶ SỐ"} and member_id == "":
            requests.append(
                {
                    "repeatCell": {
                        "range": row_range(sheet_id, row_index, row_index + 1),
                        "cell": {
                            "userEnteredFormat": {
                                "backgroundColorStyle": {"rgbColor": section_fill},
                                "textFormat": {"bold": True},
                            }
                        },
                        "fields": "userEnteredFormat(backgroundColorStyle,textFormat)",
                    }
                }
            )
            continue

        if member_id == "member_id":
            requests.append(
                {
                    "repeatCell": {
                        "range": row_range(sheet_id, row_index, row_index + 1),
                        "cell": {
                            "userEnteredFormat": {
                                "backgroundColorStyle": {"rgbColor": header_fill},
                                "textFormat": {"bold": True},
                                **bordered_sides(border_color),
                            }
                        },
                        "fields": "userEnteredFormat(backgroundColorStyle,textFormat,borders)",
                    }
                }
            )
            continue

        if section in {"KÈO THẮNG/THUA", "KÈO TỶ SỐ"} and any(cell for cell in row[1:]):
            requests.append(
                {
                    "repeatCell": {
                        "range": row_range(sheet_id, row_index, row_index + 1),
                        "cell": {
                            "userEnteredFormat": {
                                "wrapStrategy": "WRAP",
                                "verticalAlignment": "MIDDLE",
                                **bordered_sides(border_color),
                            }
                        },
                        "fields": "userEnteredFormat(wrapStrategy,verticalAlignment,borders)",
                    }
                }
            )

    return requests

def build_index_sheet_format_requests(sheet_id: int, values: list[list[str]]) -> list[dict[str, object]]:
    if not values:
        return []

    header_fill = rgb(32, 33, 36)
    row_fill = rgb(255, 255, 255)
    alt_fill = rgb(248, 249, 250)
    border_color = rgb(218, 220, 224)
    row_count = len(values)

    requests: list[dict[str, object]] = [
        {
            "updateSheetProperties": {
                "properties": {
                    "sheetId": sheet_id,
                    "gridProperties": {"frozenRowCount": 1},
                },
                "fields": "gridProperties.frozenRowCount",
            }
        },
        {
            "repeatCell": {
                "range": row_range(sheet_id, 0, 1, 0, len(values[0])),
                "cell": {
                    "userEnteredFormat": {
                        "backgroundColorStyle": {"rgbColor": header_fill},
                        "textFormat": {"bold": True, "foregroundColorStyle": {"rgbColor": rgb(255, 255, 255)}},
                        "horizontalAlignment": "CENTER",
                        "wrapStrategy": "WRAP",
                        **bordered_sides(border_color),
                    }
                },
                "fields": "userEnteredFormat(backgroundColorStyle,textFormat,horizontalAlignment,wrapStrategy,borders)",
            }
        },
        {
            "repeatCell": {
                "range": row_range(sheet_id, 1, row_count, 0, len(values[0])),
                "cell": {
                    "userEnteredFormat": {
                        "backgroundColorStyle": {"rgbColor": row_fill},
                        "wrapStrategy": "WRAP",
                        "verticalAlignment": "MIDDLE",
                        **bordered_sides(border_color),
                    }
                },
                "fields": "userEnteredFormat(backgroundColorStyle,wrapStrategy,verticalAlignment,borders)",
            }
        },
    ]

    for row_index in range(1, row_count, 2):
        requests.append(
            {
                "repeatCell": {
                    "range": row_range(sheet_id, row_index, row_index + 1, 0, len(values[0])),
                    "cell": {
                        "userEnteredFormat": {
                            "backgroundColorStyle": {"rgbColor": alt_fill},
                            "wrapStrategy": "WRAP",
                            "verticalAlignment": "MIDDLE",
                            **bordered_sides(border_color),
                        }
                    },
                    "fields": "userEnteredFormat(backgroundColorStyle,wrapStrategy,verticalAlignment,borders)",
                }
            }
        )

    column_sizes = [120, 120, 120, 160, 150, 150, 120, 120, 120, 140, 120, 120, 140, 140, 180]
    for index, pixel_size in enumerate(column_sizes):
        requests.append(
            {
                "updateDimensionProperties": {
                    "range": {"sheetId": sheet_id, "dimension": "COLUMNS", "startIndex": index, "endIndex": index + 1},
                    "properties": {"pixelSize": pixel_size},
                    "fields": "pixelSize",
                }
            }
        )
    return requests


def upload_csv_tabs(sheets, spreadsheet_id: str, csv_dir: Path, clear_existing: bool, links_csv: Path) -> None:
    metadata = sheets.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
    existing = {sheet["properties"]["title"]: sheet["properties"]["sheetId"] for sheet in metadata.get("sheets", [])}

    csv_paths = [csv_dir / "00_index.csv"] + sorted(path for path in csv_dir.glob("WC2026-*.csv"))
    requests = []
    for path in csv_paths:
        title = sheet_title(path)
        if title not in existing:
            requests.append({"addSheet": {"properties": {"title": title}}})
        elif clear_existing:
            requests.append({"updateCells": {"range": {"sheetId": existing[title]}, "fields": "userEnteredValue"}})

    if requests:
        sheets.spreadsheets().batchUpdate(spreadsheetId=spreadsheet_id, body={"requests": requests}).execute()

    value_ranges = [
        {
            "range": f"'{sheet_title(path)}'!A1",
            "values": read_csv_values(path),
        }
        for path in csv_paths
    ]
    sheets.spreadsheets().values().batchUpdate(
        spreadsheetId=spreadsheet_id,
        body={"valueInputOption": "RAW", "data": value_ranges},
    ).execute()
    metadata = sheets.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
    existing = {sheet["properties"]["title"]: sheet["properties"]["sheetId"] for sheet in metadata.get("sheets", [])}
    format_requests: list[dict[str, object]] = []
    for path in csv_paths:
        title = sheet_title(path)
        sheet_id = existing.get(title)
        if sheet_id is None:
            continue
        values = read_csv_values(path)
        if title == "00_index":
            format_requests.extend(build_index_sheet_format_requests(sheet_id, values))
        else:
            format_requests.extend(build_match_sheet_format_requests(sheet_id, values))
    if format_requests:
        sheets.spreadsheets().batchUpdate(spreadsheetId=spreadsheet_id, body={"requests": format_requests}).execute()
    write_match_sheet_links(links_csv, spreadsheet_id, metadata.get("sheets", []))
    for path in csv_paths:
        print(f"Uploaded {path.name} -> {sheet_title(path)}")
    print(f"Wrote match sheet links -> {links_csv}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv-dir", type=Path, default=DEFAULT_CSV_DIR)
    parser.add_argument("--spreadsheet-name", default=DEFAULT_SPREADSHEET_NAME)
    parser.add_argument("--spreadsheet-id", default="")
    parser.add_argument("--service-account", default=DEFAULT_SERVICE_ACCOUNT)
    parser.add_argument("--keep-existing-cells", action="store_true")
    parser.add_argument("--links-csv", type=Path, default=DEFAULT_LINKS_CSV)
    args = parser.parse_args()

    credentials = get_credentials(args.service_account)
    drive = build("drive", "v3", credentials=credentials)
    sheets = build("sheets", "v4", credentials=credentials)
    spreadsheet_id = args.spreadsheet_id or find_spreadsheet_id(drive, args.spreadsheet_name)
    upload_csv_tabs(sheets, spreadsheet_id, args.csv_dir, clear_existing=not args.keep_existing_cells, links_csv=args.links_csv)
    print(f"Done: https://docs.google.com/spreadsheets/d/{spreadsheet_id}")


if __name__ == "__main__":
    main()
