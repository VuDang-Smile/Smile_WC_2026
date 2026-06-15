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

ESPN_SCOREBOARD_URL = "https://site.api.espn.com/apis/site/v2/sports/soccer/fifa.world/scoreboard"
API_FOOTBALL_BASE = "https://v3.football.api-sports.io"


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
    parser = argparse.ArgumentParser(description="Sync fixture results from free public sources into matches store.")
    parser.add_argument("--source", choices=["espn", "api-football", "auto"], default=os.environ.get("SMILE_BET_RESULT_SOURCE", "espn"))
    parser.add_argument("--season", default=os.environ.get("SMILE_BET_RESULT_SEASON", "2026"))
    parser.add_argument("--espn-dates", default=os.environ.get("SMILE_BET_ESPN_DATES", "20260611-20260719"))
    parser.add_argument("--league", default=os.environ.get("SMILE_BET_API_FOOTBALL_LEAGUE", "1"))
    parser.add_argument("--api-key", default=os.environ.get("API_FOOTBALL_KEY", ""))
    parser.add_argument("--match-id", action="append", default=[])
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--allow-overwrite-admin-results", action="store_true")
    return parser.parse_args()


def fetch_fixtures_auto(source: str, season: str, espn_dates: str, league: str, api_key: str) -> tuple[str, list[dict[str, Any]]]:
    if source == "espn":
        return "espn", fetch_espn_fixtures(espn_dates)
    if source == "api-football":
        return "api-football", fetch_api_football_fixtures(api_key, league, season)
    try:
        return "espn", fetch_espn_fixtures(espn_dates)
    except Exception:
        return "api-football", fetch_api_football_fixtures(api_key, league, season)


def fetch_espn_fixtures(dates: str) -> list[dict[str, Any]]:
    query = urllib.parse.urlencode({"dates": dates})
    with urllib.request.urlopen(f"{ESPN_SCOREBOARD_URL}?{query}", timeout=30) as response:
        payload = json.load(response)
    return list(payload.get("events", []))


def fetch_api_football_fixtures(api_key: str, league: str, season: str) -> list[dict[str, Any]]:
    if not api_key:
        raise SystemExit("Missing API_FOOTBALL_KEY or --api-key")
    query = urllib.parse.urlencode({"league": league, "season": season})
    request = urllib.request.Request(f"{API_FOOTBALL_BASE}/fixtures?{query}", headers={"x-apisports-key": api_key})
    with urllib.request.urlopen(request, timeout=30) as response:
        payload = json.load(response)
    errors = payload.get("errors") or {}
    if errors:
        raise RuntimeError(f"api-football errors: {errors}")
    return list(payload.get("response", []))


def normalize_status(raw_status: str) -> str:
    code = (raw_status or "").upper()
    if code in {"FT", "AET", "PEN", "STATUS_FULL_TIME"}:
        return "FINISHED"
    if code in {"1H", "HT", "2H", "ET", "BT", "P", "LIVE", "STATUS_IN_PROGRESS", "STATUS_HALFTIME"}:
        return "LIVE"
    if code in {"TBD", "NS", "SCHEDULED", "STATUS_SCHEDULED"}:
        return "SCHEDULED"
    if code in {"PST", "CANC", "ABD", "AWD", "WO", "SUSP", "INT", "STATUS_POSTPONED", "STATUS_CANCELED"}:
        return code
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


def build_fixture_indexes(source_name: str, fixtures: list[dict[str, Any]]) -> tuple[dict[str, dict[str, Any]], dict[tuple[str, str, str], dict[str, Any]]]:
    by_source_id: dict[str, dict[str, Any]] = {}
    by_identity: dict[tuple[str, str, str], dict[str, Any]] = {}
    for fixture in fixtures:
        fixture_id = fixture_id_for(source_name, fixture)
        if fixture_id:
            by_source_id[fixture_id] = fixture
        home, away = team_names_for(source_name, fixture)
        kickoff = kickoff_day_for(source_name, fixture)
        if home and away and kickoff:
            by_identity[(home.casefold(), away.casefold(), kickoff)] = fixture
    return by_source_id, by_identity


def fixture_id_for(source_name: str, fixture: dict[str, Any]) -> str:
    if source_name == "espn":
        return str(fixture.get("id") or "")
    return str(fixture.get("fixture", {}).get("id") or "")


def team_names_for(source_name: str, fixture: dict[str, Any]) -> tuple[str, str]:
    if source_name == "espn":
        competition = (fixture.get("competitions") or [{}])[0]
        competitors = competition.get("competitors") or []
        home = next((row.get("team", {}).get("displayName", "") for row in competitors if row.get("homeAway") == "home"), "")
        away = next((row.get("team", {}).get("displayName", "") for row in competitors if row.get("homeAway") == "away"), "")
        return str(home), str(away)
    home = fixture.get("teams", {}).get("home", {}).get("name", "")
    away = fixture.get("teams", {}).get("away", {}).get("name", "")
    return str(home), str(away)


def kickoff_day_for(source_name: str, fixture: dict[str, Any]) -> str:
    if source_name == "espn":
        return str(fixture.get("date") or "")[:10]
    return str(fixture.get("fixture", {}).get("date") or "")[:10]


def match_fixture(match_row: dict[str, str], by_source_id: dict[str, dict[str, Any]], by_identity: dict[tuple[str, str, str], dict[str, Any]]) -> tuple[dict[str, Any] | None, str]:
    source_match_id = (match_row.get("source_match_id") or "").strip()
    if source_match_id.isdigit() and source_match_id in by_source_id:
        return by_source_id[source_match_id], "source_match_id"
    note_tokens = (match_row.get("notes") or "").split()
    for token in note_tokens:
        if token.startswith("fixture_id="):
            fixture_id = token.split("=", 1)[1].strip()
            if fixture_id in by_source_id:
                return by_source_id[fixture_id], "notes.fixture_id"
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


def fixture_values(source_name: str, fixture: dict[str, Any]) -> tuple[str, str, str, str]:
    if source_name == "espn":
        competition = (fixture.get("competitions") or [{}])[0]
        status = normalize_status(str(competition.get("status", {}).get("type", {}).get("shortDetail") or competition.get("status", {}).get("type", {}).get("name") or ""))
        competitors = competition.get("competitors") or []
        home = next((str(row.get("score") or "") for row in competitors if row.get("homeAway") == "home"), "")
        away = next((str(row.get("score") or "") for row in competitors if row.get("homeAway") == "away"), "")
        return status, home, away, derive_result(home, away)
    status_code = str(fixture.get("fixture", {}).get("status", {}).get("short") or "")
    fulltime = fixture.get("score", {}).get("fulltime", {}) or {}
    goals = fixture.get("goals", {}) or {}
    home = fulltime.get("home") if fulltime.get("home") is not None else goals.get("home")
    away = fulltime.get("away") if fulltime.get("away") is not None else goals.get("away")
    home_score = "" if home is None else str(home)
    away_score = "" if away is None else str(away)
    return normalize_status(status_code), home_score, away_score, derive_result(home_score, away_score)


def compare_and_prepare(source_name: str, row: dict[str, str], fixture: dict[str, Any], reason: str) -> MatchUpdate | None:
    new_status, new_home_score, new_away_score, new_result = fixture_values(source_name, fixture)
    if (
        row.get("status", "") == new_status
        and row.get("home_score", "") == new_home_score
        and row.get("away_score", "") == new_away_score
        and row.get("result", "") == new_result
    ):
        return None
    return MatchUpdate(
        match_id=row.get("match_id", ""),
        source_match_id=fixture_id_for(source_name, fixture) or row.get("source_match_id", ""),
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


def apply_updates(rows: list[dict[str, str]], updates: dict[str, MatchUpdate], source_name: str) -> list[dict[str, str]]:
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
        stamp = f"result_source={source_name} fixture_id={update.source_match_id} result_sync_at={now}"
        next_row["notes"] = f"{notes} {stamp}".strip()
        updated_rows.append(next_row)
    return updated_rows


def main() -> int:
    args = parse_args()
    store = build_store()
    rows = store.read_rows("matches.csv")
    target_match_ids = {match_id.upper() for match_id in args.match_id}
    source_name, fixtures = fetch_fixtures_auto(args.source, args.season, args.espn_dates, args.league, args.api_key)
    by_source_id, by_identity = build_fixture_indexes(source_name, fixtures)

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
        update = compare_and_prepare(source_name, row, fixture, reason)
        if update:
            updates[match_id] = update

    for line in skipped:
        print(line)
    for match_id in missing:
        print(f"MISS {match_id} no fixture match")
    for update in updates.values():
        print(
            "DIFF"
            f" {update.match_id} source={source_name} via={update.reason}"
            f" status:{update.old_status}->{update.new_status}"
            f" score:{update.old_home_score}-{update.old_away_score}->{update.new_home_score}-{update.new_away_score}"
            f" result:{update.old_result}->{update.new_result}"
            f" fixture_id={update.source_match_id}"
        )

    if not args.apply:
        print(f"DRY_RUN source={source_name} updates={len(updates)} missing={len(missing)} skipped={len(skipped)}")
        return 0

    if not updates:
        print(f"APPLY_OK source={source_name} updates=0")
        return 0

    store.replace_rows("matches.csv", apply_updates(rows, updates, source_name))
    print(f"APPLY_OK source={source_name} updates={len(updates)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
