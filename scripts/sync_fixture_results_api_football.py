#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.csv_store import build_store

API_BASE = "https://v3.football.api-sports.io"
FINISHED_STATUSES = {"FT", "AET", "PEN"}
IN_PROGRESS_STATUSES = {"1H", "HT", "2H", "ET", "BT", "P", "LIVE"}
SCHEDULED_STATUSES = {"TBD", "NS"}
STOPPED_STATUSES = {"PST", "CANC", "ABD", "AWD", "WO", "SUSP", "INT"}


@dataclass
class MatchUpdate:
    match_id: str
    source_match_id: str
    old_status: str
    new_status: str
    old_home_score: str
    new_home_score: str
    old_away_score: str
    new_away_score: str
    old_result: str
    new_result: str
    reason: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Sync fixture results from API-Football into matches.csv or Google Sheets store."
    )
    parser.add_argument("--league", default=os.environ.get("SMILE_BET_API_FOOTBALL_LEAGUE", "1"))
    parser.add_argument("--season", default=os.environ.get("SMILE_BET_API_FOOTBALL_SEASON", "2026"))
    parser.add_argument("--api-key", default=os.environ.get("API_FOOTBALL_KEY", ""))
    parser.add_argument("--match-id", action="append", default=[])
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--allow-overwrite-admin-results", action="store_true")
    return parser.parse_args()


def fetch_fixtures(api_key: str, league: str, season: str) -> list[dict[str, Any]]:
    if not api_key:
        raise SystemExit("Missing API_FOOTBALL_KEY or --api-key")
    query = urllib.parse.urlencode({"league": league, "season": season})
    url = f"{API_BASE}/fixtures?{query}"
    request = urllib.request.Request(url, headers={"x-apisports-key": api_key})
    with urllib.request.urlopen(request, timeout=30) as response:
        payload = json.load(response)
    return list(payload.get("response", []))


def normalize_status(short_status: str) -> str:
    code = (short_status or "").upper()
    if code in FINISHED_STATUSES:
        return "FINISHED"
    if code in IN_PROGRESS_STATUSES:
        return "LIVE"
    if code in SCHEDULED_STATUSES:
        return "SCHEDULED"
    if code in STOPPED_STATUSES:
        return code or "SCHEDULED"
    return code or "SCHEDULED"


def derive_result(home_score: str, away_score: str) -> str:
    if home_score == "" or away_score == "":
        return ""
    home = int(home_score)
    away = int(away_score)
    if home > away:
        return "HOME"
    if home < away:
        return "AWAY"
    return "DRAW"


def fixture_score(fixture: dict[str, Any]) -> tuple[str, str]:
    fulltime = fixture.get("score", {}).get("fulltime", {}) or {}
    goals = fixture.get("goals", {}) or {}
    home = fulltime.get("home")
    away = fulltime.get("away")
    if home is None:
        home = goals.get("home")
    if away is None:
        away = goals.get("away")
    return stringify_score(home), stringify_score(away)


def stringify_score(value: Any) -> str:
    if value is None:
        return ""
    return str(value)


def build_fixture_indexes(fixtures: list[dict[str, Any]]) -> tuple[dict[str, dict[str, Any]], dict[tuple[str, str, str], dict[str, Any]]]:
    by_source_id: dict[str, dict[str, Any]] = {}
    by_identity: dict[tuple[str, str, str], dict[str, Any]] = {}
    for fixture in fixtures:
        fixture_id = str(fixture.get("fixture", {}).get("id") or "")
        if fixture_id:
            by_source_id[fixture_id] = fixture
        home = str(fixture.get("teams", {}).get("home", {}).get("name") or "").strip().casefold()
        away = str(fixture.get("teams", {}).get("away", {}).get("name") or "").strip().casefold()
        kickoff = str(fixture.get("fixture", {}).get("date") or "")
        kickoff_day = kickoff[:10]
        if home and away and kickoff_day:
            by_identity[(home, away, kickoff_day)] = fixture
    return by_source_id, by_identity


def match_fixture(match_row: dict[str, str], by_source_id: dict[str, dict[str, Any]], by_identity: dict[tuple[str, str, str], dict[str, Any]]) -> tuple[dict[str, Any] | None, str]:
    source_match_id = (match_row.get("source_match_id") or "").strip()
    if source_match_id.isdigit() and source_match_id in by_source_id:
        return by_source_id[source_match_id], "source_match_id"
    note_tokens = (match_row.get("notes") or "").split()
    for token in note_tokens:
        if token.startswith("api_fixture_id="):
            fixture_id = token.split("=", 1)[1].strip()
            if fixture_id in by_source_id:
                return by_source_id[fixture_id], "notes.api_fixture_id"
    home = (match_row.get("home_team") or "").strip().casefold()
    away = (match_row.get("away_team") or "").strip().casefold()
    kickoff = kickoff_day(match_row)
    fixture = by_identity.get((home, away, kickoff))
    if fixture:
        return fixture, "team+kickoff_day"
    return None, ""


def kickoff_day(match_row: dict[str, str]) -> str:
    kickoff_utc = (match_row.get("kickoff_at_utc") or "").strip()
    if len(kickoff_utc) >= 10:
        return kickoff_utc[:10]
    kickoff_local = (match_row.get("kickoff_at_local") or "").strip()
    if len(kickoff_local) >= 10:
        return kickoff_local[:10]
    return ""


def should_skip(row: dict[str, str], allow_overwrite_admin_results: bool) -> str | None:
    if row.get("settled_at"):
        return "already settled"
    if not allow_overwrite_admin_results and row.get("admin_id") and (row.get("home_score") != "" or row.get("away_score") != ""):
        return "admin result present"
    return None


def compare_and_prepare(row: dict[str, str], fixture: dict[str, Any], reason: str) -> MatchUpdate | None:
    status_code = str(fixture.get("fixture", {}).get("status", {}).get("short") or "")
    new_status = normalize_status(status_code)
    new_home_score, new_away_score = fixture_score(fixture)
    new_result = derive_result(new_home_score, new_away_score)
    if (
        row.get("status", "") == new_status
        and row.get("home_score", "") == new_home_score
        and row.get("away_score", "") == new_away_score
        and row.get("result", "") == new_result
    ):
        return None
    return MatchUpdate(
        match_id=row.get("match_id", ""),
        source_match_id=str(fixture.get("fixture", {}).get("id") or row.get("source_match_id", "")),
        old_status=row.get("status", ""),
        new_status=new_status,
        old_home_score=row.get("home_score", ""),
        new_home_score=new_home_score,
        old_away_score=row.get("away_score", ""),
        new_away_score=new_away_score,
        old_result=row.get("result", ""),
        new_result=new_result,
        reason=reason,
    )


def apply_updates(rows: list[dict[str, str]], updates: dict[str, MatchUpdate]) -> list[dict[str, str]]:
    now = datetime.now().astimezone().isoformat(timespec="seconds")
    updated_rows: list[dict[str, str]] = []
    for row in rows:
        match_id = row.get("match_id", "")
        update = updates.get(match_id)
        if not update:
            updated_rows.append(row)
            continue
        next_row = dict(row)
        next_row["source_match_id"] = update.source_match_id
        next_row["status"] = update.new_status
        next_row["home_score"] = update.new_home_score
        next_row["away_score"] = update.new_away_score
        next_row["result"] = update.new_result
        notes = (next_row.get("notes") or "").strip()
        stamp = f"api_fixture_id={update.source_match_id} api_sync_at={now}"
        next_row["notes"] = f"{notes} {stamp}".strip()
        updated_rows.append(next_row)
    return updated_rows


def main() -> int:
    args = parse_args()
    store = build_store()
    rows = store.read_rows("matches.csv")
    target_match_ids = {match_id.upper() for match_id in args.match_id}
    fixtures = fetch_fixtures(args.api_key, args.league, args.season)
    by_source_id, by_identity = build_fixture_indexes(fixtures)

    updates: dict[str, MatchUpdate] = {}
    skipped: list[str] = []
    missing: list[str] = []

    for row in rows:
        match_id = (row.get("match_id") or "").upper()
        if target_match_ids and match_id not in target_match_ids:
            continue
        skip_reason = should_skip(row, args.allow_overwrite_admin_results)
        if skip_reason:
            skipped.append(f"SKIP {match_id} {skip_reason}")
            continue
        fixture, reason = match_fixture(row, by_source_id, by_identity)
        if not fixture:
            missing.append(match_id)
            continue
        update = compare_and_prepare(row, fixture, reason)
        if update:
            updates[match_id] = update

    for line in skipped:
        print(line)
    for match_id in missing:
        print(f"MISS {match_id} no API fixture match")
    for update in updates.values():
        print(
            "DIFF"
            f" {update.match_id} via={update.reason}"
            f" status:{update.old_status}->{update.new_status}"
            f" score:{update.old_home_score}-{update.old_away_score}->{update.new_home_score}-{update.new_away_score}"
            f" result:{update.old_result}->{update.new_result}"
            f" fixture_id={update.source_match_id}"
        )

    if not args.apply:
        print(f"DRY_RUN updates={len(updates)} missing={len(missing)} skipped={len(skipped)}")
        return 0

    if not updates:
        print("APPLY_OK updates=0")
        return 0

    store.replace_rows("matches.csv", apply_updates(rows, updates))
    print(f"APPLY_OK updates={len(updates)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
