from __future__ import annotations

import csv
import os
from pathlib import Path
from typing import Iterable, Protocol

DATA_DIR = Path("data/wc2026_betting")


class RowStore(Protocol):
    data_dir: Path

    def exists(self, file_name: str) -> bool:
        ...

    def read_rows(self, file_name: str) -> list[dict[str, str]]:
        ...

    def append_row(self, file_name: str, row: dict[str, object]) -> None:
        ...

    def replace_rows(self, file_name: str, rows: Iterable[dict[str, object]]) -> None:
        ...


class CsvStore:
    def __init__(self, data_dir: str | Path = DATA_DIR) -> None:
        self.data_dir = Path(data_dir)

    def exists(self, file_name: str) -> bool:
        return (self.data_dir / file_name).exists()

    def read_rows(self, file_name: str) -> list[dict[str, str]]:
        path = self.data_dir / file_name
        with path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            return [dict(row) for row in reader]

    def append_row(self, file_name: str, row: dict[str, object]) -> None:
        path = self.data_dir / file_name
        with path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            fieldnames = reader.fieldnames or []
        normalized = {name: self._stringify(row.get(name, "")) for name in fieldnames}
        with path.open("a", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writerow(normalized)

    def replace_rows(self, file_name: str, rows: Iterable[dict[str, object]]) -> None:
        path = self.data_dir / file_name
        with path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            fieldnames = reader.fieldnames or []
        materialized = [
            {name: self._stringify(row.get(name, "")) for name in fieldnames}
            for row in rows
        ]
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(materialized)

    @staticmethod
    def _stringify(value: object) -> str:
        if value is None:
            return ""
        return str(value)


def build_store() -> RowStore:
    mode = os.environ.get("SMILE_BET_STORE", "").strip().lower()
    if mode == "csv":
        data_dir = os.environ.get("SMILE_BET_DATA_DIR", "").strip()
        return CsvStore(data_dir or DATA_DIR)
    if mode in {"source_spreadsheets", "file_sheets", "google_file_sheets"}:
        from src.google_sheets_store import GoogleSheetsFileStore

        return GoogleSheetsFileStore.from_env()
    if mode in {"", "sheets", "google_sheets"}:
        from src.google_sheets_store import GoogleSheetsStore

        return GoogleSheetsStore.from_env()
    raise ValueError(f"Unsupported SMILE_BET_STORE: {mode}")
