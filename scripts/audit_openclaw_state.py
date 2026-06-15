#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import sys
import tempfile
from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from google.oauth2 import service_account
from googleapiclient.discovery import build

from scripts.export_match_bet_sheets import build_match_sheet_rows
from scripts.sync_public_match_workbook import DEFAULT_PUBLIC_WORKBOOK_ID, SOURCE_SPREADSHEETS

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
VN_SUFFIX = "+07:00"

@dataclass
class AuditIssue:
    scope: str
    message: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--service-account", default=".secret/googlechat-service-account.json")
    parser.add_argument("--public-workbook-id", default=DEFAULT_PUBLIC_WORKBOOK_ID)
    parser.add_argument("--match-id", action="append", default=[])
    parser.add_argument("--member-id", action="append", default=[])
    return parser.parse_args()


def get_credentials(service_account_path: str):
    return service_account.Credentials.from_service_account_file(service_account_path, scopes=SCOPES)


def fetch_values(sheets, spreadsheet_id: str, range_name: str = "A:Z") -> list[list[str]]:
    return sheets.spreadsheets().values().get(spreadsheetId=spreadsheet_id, range=range_name).execute().get("values", [])


def values_to_rows(values: list[list[str]]) -> list[dict[str, str]]:
    if not values:
        return []
    headers = [str(value) for value in values[0]]
    rows: list[dict[str, str]] = []
    for raw_row in values[1:]:
        padded = list(raw_row) + [""] * max(0, len(headers) - len(raw_row))
        rows.append({headers[index]: str(padded[index]) for index in range(len(headers))})
    return rows


def read_public_tab_rows(sheets, spreadsheet_id: str, tab_name: str) -> list[dict[str, str]]:
    return values_to_rows(fetch_values(sheets, spreadsheet_id, f"'{tab_name}'!A:K"))

def read_public_tabs_rows(sheets, spreadsheet_id: str, tab_names: list[str]) -> dict[str, list[dict[str, str]]]:
    if not tab_names:
        return {}
    ranges = [f"'{tab_name}'!A:K" for tab_name in tab_names]
    result = sheets.spreadsheets().values().batchGet(
        spreadsheetId=spreadsheet_id,
        ranges=ranges,
    ).execute()
    value_ranges = result.get("valueRanges", [])
    rows_by_tab: dict[str, list[dict[str, str]]] = {}
    for tab_name, value_range in zip(tab_names, value_ranges):
        rows_by_tab[tab_name] = values_to_rows(value_range.get("values", []))
    return rows_by_tab


def to_int(value: str | None) -> int:
    if not value:
        return 0
    return int(Decimal(str(value)))


def to_decimal(value: str | None) -> Decimal:
    if value in (None, ""):
        return Decimal("0")
    return Decimal(str(value))


def latest(values: list[str]) -> str:
    return max((value for value in values if value), default="")


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



def build_expected_public_rows(match: dict[str, str], members: dict[str, dict[str, str]], wdl_rows: list[dict[str, str]], score_rows: list[dict[str, str]]) -> list[dict[str, object]]:
    rows_by_member: dict[str, dict[str, object]] = {}
    for bet in wdl_rows:
        member_id = bet.get("member_id", "")
        if not member_id:
            continue
        row = rows_by_member.setdefault(member_id, base_member_row(member_id, members))
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
        row["latest_bet_at"] = latest([str(row["latest_bet_at"]), bet.get("created_at", "")])
    for bet in score_rows:
        member_id = bet.get("member_id", "")
        if not member_id:
            continue
        row = rows_by_member.setdefault(member_id, base_member_row(member_id, members))
        row["score_entries"].append(
            {
                "selection": f"{bet.get('predicted_home_score', '')}-{bet.get('predicted_away_score', '')}",
                "ticket_count": bet.get("ticket_count", ""),
                "points_staked": bet.get("points_staked", ""),
                "latest_bet_at": bet.get("created_at", ""),
                "status": bet.get("status", ""),
                "payout_points": bet.get("payout_points", "") or "0",
                "net_points": bet.get("net_points", "") or "0",
            }
        )
        row["latest_bet_at"] = latest([str(row["latest_bet_at"]), bet.get("created_at", "")])
    member_rows = sorted(rows_by_member.values(), key=lambda row: (str(row["display_name"]), str(row["member_id"])))
    return build_match_sheet_rows(match, member_rows)


def audit_members_vs_ledger(member_rows: list[dict[str, str]], ledger_rows: list[dict[str, str]], target_member_ids: set[str]) -> list[AuditIssue]:
    issues: list[AuditIssue] = []
    ledger_totals: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
    ledger_seen: set[str] = set()
    for row in ledger_rows:
        member_id = row.get("member_id", "")
        if member_id:
            ledger_seen.add(member_id)
            ledger_totals[member_id] += to_decimal(row.get("points_delta", "0"))
    for member in member_rows:
        member_id = member.get("member_id", "")
        if target_member_ids and member_id not in target_member_ids:
            continue
        expected = ledger_totals.get(member_id, Decimal("0"))
        actual = to_decimal(member.get("current_balance", "0"))
        if member_id in ledger_seen and actual != expected:
            issues.append(AuditIssue("members", f"balance mismatch for {member_id}: members={actual} ledger={expected}"))
        updated_at = member.get("updated_at", "")
        if updated_at and not updated_at.endswith(VN_SUFFIX):
            issues.append(AuditIssue("members", f"updated_at not Vietnam time for {member_id}: {updated_at}"))
    return issues


def audit_match(match: dict[str, str], members: dict[str, dict[str, str]], wdl_rows: list[dict[str, str]], score_rows: list[dict[str, str]], public_rows: list[dict[str, str]]) -> list[AuditIssue]:
    issues: list[AuditIssue] = []
    match_id = match.get("match_id", "")
    if match.get("settled_at") and match.get("status") != "FINISHED":
        issues.append(AuditIssue(match_id, f"settled match status must stay FINISHED, got {match.get('status', '')}"))
    if match.get("settled_at") and (match.get("home_score", "") == "" or match.get("away_score", "") == ""):
        issues.append(AuditIssue(match_id, "settled match missing final score"))
    expected_rows = build_expected_public_rows(match, members, wdl_rows, score_rows)
    expected_keys = {
        (str(row.get("section", "")), str(row.get("member_id", "")), str(row.get("selection", "")), str(row.get("ticket_count", "")), str(row.get("points_staked", "")), str(row.get("status", "")), str(row.get("payout_points", "")), str(row.get("net_points", "")), str(row.get("latest_bet_at", "")))
        for row in expected_rows
    }
    actual_keys = {
        (str(row.get("section", "")), str(row.get("member_id", "")), str(row.get("selection", "")), str(row.get("ticket_count", "")), str(row.get("points_staked", "")), str(row.get("status", "")), str(row.get("payout_points", "")), str(row.get("net_points", "")), str(row.get("latest_bet_at", "")))
        for row in public_rows
    }
    missing = sorted(expected_keys - actual_keys)
    if missing:
        issues.append(AuditIssue(match_id, f"public rows missing: {missing[:5]}"))

    wdl_pool = sum(to_int(row.get("points_staked")) for row in wdl_rows if row.get("status") in {"ACTIVE", "SETTLED"})
    score_pool = sum(to_int(row.get("points_staked")) for row in score_rows if row.get("status") in {"ACTIVE", "SETTLED"})
    info_rows = [row for row in public_rows if row.get("section") == "THÔNG TIN TRẬN"]
    if not any(f"Tổng pool WDL: {wdl_pool} point" == row.get("member_id", "") for row in info_rows):
        issues.append(AuditIssue(match_id, f"public WDL pool mismatch: expected {wdl_pool}"))
    if not any(f"Tổng pool tỷ số: {score_pool} point" == row.get("display_name", "") for row in info_rows):
        issues.append(AuditIssue(match_id, f"public score pool mismatch: expected {score_pool}"))

    settled_score_rows = [row for row in score_rows if row.get("status") == "SETTLED"]
    for row in settled_score_rows:
        selection = f"{row.get('predicted_home_score', '')}-{row.get('predicted_away_score', '')}"
        payout = row.get('payout_points', '') or '0'
        net = row.get('net_points', '') or '0'
        if not any(
            public.get("member_id") == row.get("member_id")
            and public.get("selection") == selection
            and public.get("status") == "SETTLED"
            and public.get("payout_points") == payout
            and public.get("net_points") == net
            for public in public_rows
        ):
            issues.append(AuditIssue(match_id, f"missing settled score row for {row.get('member_id')} {selection} payout={payout} net={net}"))

    return issues


def main() -> int:
    args = parse_args()
    credentials = get_credentials(args.service_account)
    sheets = build("sheets", "v4", credentials=credentials)

    internal_rows = {
        file_name: values_to_rows(fetch_values(sheets, spreadsheet_id))
        for file_name, spreadsheet_id in SOURCE_SPREADSHEETS.items()
    }
    members = {row.get("member_id", ""): row for row in internal_rows["members.csv"] if row.get("member_id")}
    matches = {row.get("match_id", ""): row for row in internal_rows["matches.csv"] if row.get("match_id")}

    target_match_ids = set(args.match_id) if args.match_id else set(matches)
    target_member_ids = set(args.member_id)

    issues: list[AuditIssue] = []
    issues.extend(audit_members_vs_ledger(internal_rows["members.csv"], internal_rows["point_ledger.csv"], target_member_ids))

    try:
        public_rows_by_match = read_public_tabs_rows(sheets, args.public_workbook_id, sorted(target_match_ids))
    except Exception as exc:  # noqa: BLE001
        public_rows_by_match = {}
        for match_id in sorted(target_match_ids):
            issues.append(AuditIssue(match_id, f"cannot read public tab batch: {exc}"))

    for match_id in sorted(target_match_ids):
        match = matches.get(match_id)
        if not match:
            issues.append(AuditIssue("matches", f"unknown match_id: {match_id}"))
            continue
        wdl_rows = [row for row in internal_rows["win_draw_loss_bets.csv"] if row.get("match_id") == match_id and row.get("status") in {"ACTIVE", "SETTLED"}]
        score_rows = [row for row in internal_rows["score_bets.csv"] if row.get("match_id") == match_id and row.get("status") in {"ACTIVE", "SETTLED"}]
        public_rows = public_rows_by_match.get(match_id)
        if public_rows is None:
            issues.append(AuditIssue(match_id, "public tab missing from batch response"))
            continue
        issues.extend(audit_match(match, members, wdl_rows, score_rows, public_rows))

    if issues:
        for issue in issues:
            print(f"AUDIT_FAIL [{issue.scope}] {issue.message}")
        return 1

    match_text = ",".join(sorted(target_match_ids)) if target_match_ids else "all-matches"
    member_text = ",".join(sorted(target_member_ids)) if target_member_ids else "all-members"
    print(f"AUDIT_OK matches={match_text} members={member_text}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
