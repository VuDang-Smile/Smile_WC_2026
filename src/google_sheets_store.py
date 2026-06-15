from __future__ import annotations

import os
from pathlib import Path
from typing import Iterable

from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

DEFAULT_SOURCE_SPREADSHEETS = {
    "members.csv": "1ugJmw4wODbK7kYkXQ9vEYUDMMBXkZdq1pxd3m4KccHY",
    "matches.csv": "15-D3OOjpqCbpeX6-riCMzi6jB0wC2tpGhWzNBDM0nUU",
    "point_ledger.csv": "1fGHn4hXgYXnZ-H02sL98zEm0-RbsYSkeA3uDinlm3QA",
    "win_draw_loss_bets.csv": "1HjM6tof5kLB4_5wzPfqPscfFdUnUT_ecbVSev4r7V_Q",
    "score_bets.csv": "1IArjIazapqmwwhndlJuhZs_7wbqqlg5d3F8DZU0ZCcs",
    "admin_actions.csv": "1d-Q9vTGs4FD_m1UScm_aWyxk0PE17E3WRx7BzWoI_Rw",
    "match_settlements.csv": "10cH3VfZhZeFowNNT-yoENHLAJcUN2j5UC8gnNCS_JpA",
    "final_jackpot.csv": "1raO48c2Y6bzOlKP0s_qCTc1HELK4jjbdZp_PdmgdqPA",
}


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
    def from_env(cls) -> "GoogleSheetsStore | GoogleSheetsFileStore":
        credentials_path = _credentials_path_from_env()
        spreadsheet_id = os.environ.get("SMILE_BET_SPREADSHEET_ID", "").strip()
        if not spreadsheet_id and credentials_path:
            return GoogleSheetsFileStore.from_env(credentials_path=credentials_path)

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


class GoogleSheetsFileStore:
    def __init__(
        self,
        spreadsheet_map: dict[str, str],
        credentials_path: str,
        data_dir: str | Path = Path("google-sheets-files://wc2026_betting"),
    ) -> None:
        if not spreadsheet_map:
            raise ValueError("Missing source spreadsheet map")
        if not credentials_path:
            raise ValueError("Missing credentials path")
        self.spreadsheet_map = spreadsheet_map
        self.data_dir = Path(data_dir)
        credentials = Credentials.from_service_account_file(
            credentials_path,
            scopes=["https://www.googleapis.com/auth/spreadsheets"],
        )
        self.sheets = build("sheets", "v4", credentials=credentials)

    @classmethod
    def from_env(cls, credentials_path: str | None = None) -> "GoogleSheetsFileStore":
        spreadsheet_map = _source_spreadsheet_map_from_env()
        return cls(
            spreadsheet_map=spreadsheet_map,
            credentials_path=credentials_path or _credentials_path_from_env(),
        )

    def exists(self, file_name: str) -> bool:
        return file_name in self.spreadsheet_map

    def read_rows(self, file_name: str) -> list[dict[str, str]]:
        spreadsheet_id = self._spreadsheet_id(file_name)
        result = self.sheets.spreadsheets().values().get(
            spreadsheetId=spreadsheet_id,
            range="A:Z",
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
        spreadsheet_id = self._spreadsheet_id(file_name)
        fieldnames = self._fieldnames(file_name)
        values = [[self._stringify(row.get(name, "")) for name in fieldnames]]
        self.sheets.spreadsheets().values().append(
            spreadsheetId=spreadsheet_id,
            range="A1",
            valueInputOption="USER_ENTERED",
            insertDataOption="INSERT_ROWS",
            body={"values": values},
        ).execute()

    def replace_rows(self, file_name: str, rows: Iterable[dict[str, object]]) -> None:
        spreadsheet_id = self._spreadsheet_id(file_name)
        fieldnames = self._fieldnames(file_name)
        values = [fieldnames]
        for row in rows:
            values.append([self._stringify(row.get(name, "")) for name in fieldnames])
        self.sheets.spreadsheets().values().clear(
            spreadsheetId=spreadsheet_id,
            range="A:Z",
            body={},
        ).execute()
        self.sheets.spreadsheets().values().update(
            spreadsheetId=spreadsheet_id,
            range="A1",
            valueInputOption="USER_ENTERED",
            body={"values": values},
        ).execute()

    def _fieldnames(self, file_name: str) -> list[str]:
        spreadsheet_id = self._spreadsheet_id(file_name)
        result = self.sheets.spreadsheets().values().get(
            spreadsheetId=spreadsheet_id,
            range="1:1",
        ).execute()
        values = result.get("values", [])
        if not values:
            raise ValueError(f"Sheet has no header row: {file_name}")
        return [str(value) for value in values[0]]

    def _spreadsheet_id(self, file_name: str) -> str:
        spreadsheet_id = self.spreadsheet_map.get(file_name, "").strip()
        if not spreadsheet_id:
            raise ValueError(f"No source spreadsheet mapped for {file_name}")
        return spreadsheet_id

    @staticmethod
    def _stringify(value: object) -> str:
        if value is None:
            return ""
        return str(value)


def _credentials_path_from_env() -> str:
    env_path = (
        os.environ.get("SMILE_BET_GOOGLE_SERVICE_ACCOUNT", "").strip()
        or os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", "").strip()
    )
    if env_path:
        return env_path
    default_path = Path(".secret/googlechat-service-account.json")
    if default_path.exists():
        return str(default_path)
    return ""


def _source_spreadsheet_map_from_env() -> dict[str, str]:
    raw_map = os.environ.get("SMILE_BET_SOURCE_SPREADSHEETS", "").strip()
    spreadsheet_map: dict[str, str] = {}
    for pair in raw_map.split(","):
        if not pair.strip() or "=" not in pair:
            continue
        file_name, spreadsheet_id = pair.split("=", 1)
        spreadsheet_map[file_name.strip()] = spreadsheet_id.strip()
    return spreadsheet_map or DEFAULT_SOURCE_SPREADSHEETS.copy()
