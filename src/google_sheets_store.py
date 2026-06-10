from __future__ import annotations

import os
from pathlib import Path
from typing import Iterable

from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build


class GoogleSheetsStore:
    def __init__(self, spreadsheet_id: str, sheet_map: dict[str, str], credentials_path: str, data_dir: str | Path = Path("google-sheets://wc2026_betting")) -> None:
        if not spreadsheet_id:
            raise ValueError("Missing spreadsheet_id")
        if not sheet_map:
            raise ValueError("Missing sheet map")
        if not credentials_path:
            raise ValueError("Missing credentials path")
        self.spreadsheet_id = spreadsheet_id
        self.sheet_map = sheet_map
        self.data_dir = Path(data_dir)
        credentials = Credentials.from_service_account_file(
            credentials_path,
            scopes=["https://www.googleapis.com/auth/spreadsheets"],
        )
        self.sheets = build("sheets", "v4", credentials=credentials)

    @classmethod
    def from_env(cls) -> "GoogleSheetsStore":
        spreadsheet_id = os.environ.get("SMILE_BET_SPREADSHEET_ID", "").strip()
        credentials_path = (
            os.environ.get("SMILE_BET_GOOGLE_SERVICE_ACCOUNT", "").strip()
            or os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", "").strip()
        )
        raw_map = os.environ.get("SMILE_BET_SHEET_MAP", "").strip()
        sheet_map: dict[str, str] = {}
        for pair in raw_map.split(","):
            if not pair.strip() or "=" not in pair:
                continue
            file_name, sheet_name = pair.split("=", 1)
            sheet_map[file_name.strip()] = sheet_name.strip()
        if not sheet_map:
            sheet_map = cls.default_sheet_map()
        if not spreadsheet_id:
            raise ValueError("Missing SMILE_BET_SPREADSHEET_ID for Google Sheets runtime")
        if not credentials_path:
            raise ValueError("Missing SMILE_BET_GOOGLE_SERVICE_ACCOUNT or GOOGLE_APPLICATION_CREDENTIALS for Google Sheets runtime")
        return cls(spreadsheet_id=spreadsheet_id, sheet_map=sheet_map, credentials_path=credentials_path)

    @staticmethod
    def default_sheet_map() -> dict[str, str]:
        return {
            "members.csv": "members",
            "matches.csv": "matches",
            "point_ledger.csv": "point_ledger",
            "win_draw_loss_bets.csv": "win_draw_loss_bets",
            "score_bets.csv": "score_bets",
            "admin_actions.csv": "admin_actions",
            "match_settlements.csv": "match_settlements",
            "final_jackpot.csv": "final_jackpot",
            "match_sheet_links.csv": "match_sheet_links",
        }

    def exists(self, file_name: str) -> bool:
        return file_name in self.sheet_map

    def read_rows(self, file_name: str) -> list[dict[str, str]]:
        sheet_name = self._sheet_name(file_name)
        result = self.sheets.spreadsheets().values().get(
            spreadsheetId=self.spreadsheet_id,
            range=f"'{sheet_name}'",
        ).execute()
        values = result.get("values", [])
        if not values:
            return []
        headers = [str(value) for value in values[0]]
        rows: list[dict[str, str]] = []
        for raw_row in values[1:]:
            padded = list(raw_row) + [""] * max(0, len(headers) - len(raw_row))
            rows.append({headers[index]: str(padded[index]) for index in range(len(headers))})
        return rows

    def append_row(self, file_name: str, row: dict[str, object]) -> None:
        sheet_name = self._sheet_name(file_name)
        fieldnames = self._fieldnames(file_name)
        values = [[self._stringify(row.get(name, "")) for name in fieldnames]]
        self.sheets.spreadsheets().values().append(
            spreadsheetId=self.spreadsheet_id,
            range=f"'{sheet_name}'!A1",
            valueInputOption="USER_ENTERED",
            insertDataOption="INSERT_ROWS",
            body={"values": values},
        ).execute()

    def replace_rows(self, file_name: str, rows: Iterable[dict[str, object]]) -> None:
        sheet_name = self._sheet_name(file_name)
        fieldnames = self._fieldnames(file_name)
        values = [fieldnames]
        for row in rows:
            values.append([self._stringify(row.get(name, "")) for name in fieldnames])
        self.sheets.spreadsheets().values().clear(
            spreadsheetId=self.spreadsheet_id,
            range=f"'{sheet_name}'",
            body={},
        ).execute()
        self.sheets.spreadsheets().values().update(
            spreadsheetId=self.spreadsheet_id,
            range=f"'{sheet_name}'!A1",
            valueInputOption="USER_ENTERED",
            body={"values": values},
        ).execute()

    def _fieldnames(self, file_name: str) -> list[str]:
        sheet_name = self._sheet_name(file_name)
        result = self.sheets.spreadsheets().values().get(
            spreadsheetId=self.spreadsheet_id,
            range=f"'{sheet_name}'!1:1",
        ).execute()
        values = result.get("values", [])
        if not values:
            raise ValueError(f"Sheet has no header row: {sheet_name}")
        return [str(value) for value in values[0]]

    def _sheet_name(self, file_name: str) -> str:
        sheet_name = self.sheet_map.get(file_name, "").strip()
        if not sheet_name:
            raise ValueError(f"No sheet mapped for {file_name}")
        return sheet_name

    @staticmethod
    def _stringify(value: object) -> str:
        if value is None:
            return ""
        return str(value)
