#!/usr/bin/env python3
"""Export per-match betting reports as CSV files.

Creates one CSV per match plus an index CSV with bettor counts, ticket counts,
and points staked. The generated files can be uploaded to Google Sheets as
one workbook with one tab per match.
"""

from __future__ import annotations

import argparse
import csv
from collections import defaultdict
from pathlib import Path


DEFAULT_DATA_DIR = Path("data/wc2026_betting")
DEFAULT_OUTPUT_DIR = Path("data/wc2026_betting/match_bet_sheets")


MATCH_FIELDNAMES = ["section", "member_id", "display_name", "email", "selection", "ticket_count", "points_staked", "status", "payout_points", "net_points", "latest_bet_at"]

INDEX_FIELDNAMES = [
    "match_id",
    "stage",
    "group_name",
    "kickoff_at_local",
    "home_team",
    "away_team",
    "unique_bettor_count",
    "wdl_bettor_count",
    "wdl_ticket_count",
    "wdl_points_staked",
    "score_bettor_count",
    "score_ticket_count",
    "score_points_staked",
    "total_points_staked",
    "match_sheet_file",
]


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def write_rows(path: Path, fieldnames: list[str], rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def to_int(value: str | None) -> int:
    if not value:
        return 0
    return int(value)


def add_number(current: str, value: str) -> str:
    if not current:
        return value or "0"
    if not value:
        return current
    return str(to_int(current) + to_int(value))


def latest(first: str, second: str) -> str:
    if not first:
        return second
    if not second:
        return first
    return max(first, second)


def export_reports(data_dir: Path, output_dir: Path) -> None:
    matches = read_rows(data_dir / "matches.csv")
    members = {row["member_id"]: row for row in read_rows(data_dir / "members.csv") if row.get("member_id")}
    all_wdl_bets = read_rows(data_dir / "win_draw_loss_bets.csv")
    all_score_bets = read_rows(data_dir / "score_bets.csv")
    wdl_bets = [row for row in all_wdl_bets if row.get("status") in {"ACTIVE", "SETTLED"}]
    score_bets = [row for row in all_score_bets if row.get("status") in {"ACTIVE", "SETTLED"}]
    settlements = read_rows(data_dir / "match_settlements.csv")

    rows_by_match: dict[str, dict[str, dict[str, object]]] = defaultdict(dict)

    for bet in wdl_bets:
        match_id = bet.get("match_id", "")
        member_id = bet.get("member_id", "")
        if not match_id or not member_id:
            continue
        row = rows_by_match[match_id].setdefault(member_id, base_member_row(member_id, members))
        row["wdl_entries"].append(
            {
                "selection": bet.get("pick", ""),
                "ticket_count": bet.get("ticket_count", ""),
                "points_staked": bet.get("points_staked", ""),
                "latest_bet_at": bet.get("created_at", ""),
                "status": bet.get("status", ""),
                "payout_points": bet.get("payout_points", "") or "0",
                "net_points": bet.get("net_points", "") or "0",
            }
        )
        row["latest_bet_at"] = latest(row["latest_bet_at"], bet.get("created_at", ""))

    for bet in score_bets:
        match_id = bet.get("match_id", "")
        member_id = bet.get("member_id", "")
        if not match_id or not member_id:
            continue
        prediction = f"{bet.get('predicted_home_score', '')}-{bet.get('predicted_away_score', '')}"
        row = rows_by_match[match_id].setdefault(member_id, base_member_row(member_id, members))
        row["score_entries"].append(
            {
                "selection": prediction,
                "ticket_count": bet.get("ticket_count", ""),
                "points_staked": bet.get("points_staked", ""),
                "latest_bet_at": bet.get("created_at", ""),
                "status": bet.get("status", ""),
                "payout_points": bet.get("payout_points", "") or "0",
                "net_points": bet.get("net_points", "") or "0",
            }
        )
        row["latest_bet_at"] = latest(row["latest_bet_at"], bet.get("created_at", ""))

    index_rows: list[dict[str, object]] = []
    for match in matches:
        match_id = match.get("match_id", "")
        file_name = f"{match_id}.csv"
        member_rows = sorted(rows_by_match.get(match_id, {}).values(), key=lambda row: (row["display_name"], row["member_id"]))
        match_rows = build_match_sheet_rows(
            match,
            member_rows,
            settled_wdl_rows=[row for row in all_wdl_bets if row.get("match_id") == match_id and row.get("status") == "SETTLED"],
            settled_score_rows=[row for row in all_score_bets if row.get("match_id") == match_id and row.get("status") == "SETTLED"],
            settlement_rows=[row for row in settlements if row.get("match_id") == match_id],
            members=members,
        )
        write_rows(output_dir / file_name, MATCH_FIELDNAMES, match_rows)

        wdl_bettors = {row["member_id"] for row in member_rows if row["wdl_entries"]}
        score_bettors = {row["member_id"] for row in member_rows if row["score_entries"]}
        wdl_tickets = sum(sum(to_int(entry["ticket_count"]) for entry in row["wdl_entries"]) for row in member_rows)
        score_tickets = sum(sum(to_int(entry["ticket_count"]) for entry in row["score_entries"]) for row in member_rows)
        wdl_points = sum(sum(to_int(entry["points_staked"]) for entry in row["wdl_entries"]) for row in member_rows)
        score_points = sum(sum(to_int(entry["points_staked"]) for entry in row["score_entries"]) for row in member_rows)

        index_rows.append({
            "match_id": match_id,
            "stage": match.get("stage", ""),
            "group_name": match.get("group_name", ""),
            "kickoff_at_local": match.get("kickoff_at_local", "") or match.get("kickoff_at_utc", ""),
            "home_team": match.get("home_team", ""),
            "away_team": match.get("away_team", ""),
            "unique_bettor_count": len(wdl_bettors | score_bettors),
            "wdl_bettor_count": len(wdl_bettors),
            "wdl_ticket_count": wdl_tickets,
            "wdl_points_staked": wdl_points,
            "score_bettor_count": len(score_bettors),
            "score_ticket_count": score_tickets,
            "score_points_staked": score_points,
            "total_points_staked": wdl_points + score_points,
            "match_sheet_file": file_name,
        })

    write_rows(output_dir / "00_index.csv", INDEX_FIELDNAMES, index_rows)


def base_member_row(member_id: str, members: dict[str, dict[str, str]]) -> dict[str, object]:
    member = members.get(member_id, {})
    return {
        "member_id": member_id,
        "display_name": member.get("display_name", ""),
        "email": member.get("email", ""),
        "wdl_entries": [],
        "score_entries": [],
        "latest_bet_at": "",
    }

def build_match_sheet_rows(
    match: dict[str, str],
    member_rows: list[dict[str, str]],
    settled_wdl_rows: list[dict[str, str]] | None = None,
    settled_score_rows: list[dict[str, str]] | None = None,
    settlement_rows: list[dict[str, str]] | None = None,
    members: dict[str, dict[str, str]] | None = None,
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []

    title = f"{match.get('match_id', '')} - {match.get('home_team', '')} vs {match.get('away_team', '')}"
    kickoff = match.get("kickoff_at_local", "") or match.get("kickoff_at_utc", "")
    subtitle = " | ".join(part for part in [match.get("stage", ""), match.get("group_name", ""), kickoff] if part)
    rows.append(report_row("THÔNG TIN TRẬN", title, subtitle))
    if match.get("home_score", "") != "" and match.get("away_score", "") != "":
        rows.append(report_row("THÔNG TIN TRẬN", f"Kết quả: {match.get('home_team', '')} {match.get('home_score', '')}-{match.get('away_score', '')} {match.get('away_team', '')}", match.get("status", "")))
    wdl_pool = sum(sum(to_int(entry["points_staked"]) for entry in row["wdl_entries"]) for row in member_rows)
    score_pool = sum(sum(to_int(entry["points_staked"]) for entry in row["score_entries"]) for row in member_rows)
    rows.append(report_row("THÔNG TIN TRẬN", f"Tổng pool WDL: {wdl_pool} point", f"Tổng pool tỷ số: {score_pool} point"))
    rows.append(blank_row())

    rows.extend(build_market_section(
        title="KÈO THẮNG/THUA",
        selection_label="Lựa chọn",
        member_rows=[row for row in member_rows if row["wdl_entries"]],
        entries_key="wdl_entries",
    ))
    rows.append(blank_row())
    rows.extend(build_market_section(
        title="KÈO TỶ SỐ",
        selection_label="Dự đoán",
        member_rows=[row for row in member_rows if row["score_entries"]],
        entries_key="score_entries",
    ))
    return rows

def build_market_section(
    title: str,
    selection_label: str,
    member_rows: list[dict[str, str]],
    entries_key: str,
) -> list[dict[str, object]]:
    rows = [report_row(title, "", "")]
    rows.append(
        {
            "section": title,
            "member_id": "member_id",
            "display_name": "display_name",
            "email": "email",
            "selection": selection_label,
            "ticket_count": "Số vé",
            "points_staked": "Point",
            "status": "Trạng thái",
            "payout_points": "Payout",
            "net_points": "Net",
            "latest_bet_at": "Cược gần nhất",
        }
    )
    if not member_rows:
        rows.append(report_row(title, "Chưa có cược", ""))
        return rows

    for row in member_rows:
        for entry in row[entries_key]:
            rows.append(
                {
                    "section": title,
                    "member_id": row["member_id"],
                    "display_name": row["display_name"],
                    "email": row["email"],
                    "selection": entry["selection"],
                    "ticket_count": entry["ticket_count"],
                    "points_staked": entry["points_staked"],
                    "status": entry.get("status", ""),
                    "payout_points": entry.get("payout_points", ""),
                    "net_points": entry.get("net_points", ""),
                    "latest_bet_at": entry["latest_bet_at"],
                }
            )
    return rows

def report_row(section: str, member_id: str, display_name: str) -> dict[str, object]:
    return {
        "section": section,
        "member_id": member_id,
        "display_name": display_name,
        "email": "",
        "selection": "",
        "ticket_count": "",
        "points_staked": "",
        "status": "",
        "payout_points": "",
        "net_points": "",
        "latest_bet_at": "",
    }

def blank_row() -> dict[str, object]:
    return {
        "section": "",
        "member_id": "",
        "display_name": "",
        "email": "",
        "selection": "",
        "ticket_count": "",
        "points_staked": "",
        "status": "",
        "payout_points": "",
        "net_points": "",
        "latest_bet_at": "",
    }


def join_values(current: str, value: str) -> str:
    if not value:
        return current
    if not current:
        return value
    values = current.split("; ")
    if value in values:
        return current
    return f"{current}; {value}"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()
    export_reports(args.data_dir, args.output_dir)
    print(f"Exported match bet sheets to {args.output_dir}")


if __name__ == "__main__":
    main()
