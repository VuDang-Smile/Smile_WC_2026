from __future__ import annotations

import csv
from pathlib import Path
from typing import Iterable

DATA_DIR = Path("data/wc2026_betting")


class CsvStore:
    def __init__(self, data_dir: str | Path = DATA_DIR) -> None:
        self.data_dir = Path(data_dir)

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
