#!/usr/bin/env python3
from __future__ import annotations

import csv
import json
import re
import urllib.request
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo


SOURCE_URL = "https://raw.githubusercontent.com/openfootball/worldcup.json/master/2026/worldcup.json"
DATA_DIR = Path("data/wc2026_betting")
SOURCE_TZ = ZoneInfo("America/Mexico_City")
VN_TZ = ZoneInfo("Asia/Ho_Chi_Minh")

CONFEDERATION = {
    "Algeria": "CAF",
    "Argentina": "CONMEBOL",
    "Australia": "AFC",
    "Austria": "UEFA",
    "Belgium": "UEFA",
    "Bosnia & Herzegovina": "UEFA",
    "Brazil": "CONMEBOL",
    "Canada": "CONCACAF",
    "Cape Verde": "CAF",
    "Colombia": "CONMEBOL",
    "Croatia": "UEFA",
    "Curaçao": "CONCACAF",
    "Czech Republic": "UEFA",
    "DR Congo": "CAF",
    "Ecuador": "CONMEBOL",
    "Egypt": "CAF",
    "England": "UEFA",
    "France": "UEFA",
    "Germany": "UEFA",
    "Ghana": "CAF",
    "Haiti": "CONCACAF",
    "Iran": "AFC",
    "Iraq": "AFC",
    "Ivory Coast": "CAF",
    "Japan": "AFC",
    "Jordan": "AFC",
    "Mexico": "CONCACAF",
    "Morocco": "CAF",
    "Netherlands": "UEFA",
    "New Zealand": "OFC",
    "Norway": "UEFA",
    "Panama": "CONCACAF",
    "Paraguay": "CONMEBOL",
    "Portugal": "UEFA",
    "Qatar": "AFC",
    "Saudi Arabia": "AFC",
    "Scotland": "UEFA",
    "Senegal": "CAF",
    "South Africa": "CAF",
    "South Korea": "AFC",
    "Spain": "UEFA",
    "Sweden": "UEFA",
    "Switzerland": "UEFA",
    "Tunisia": "CAF",
    "Turkey": "UEFA",
    "USA": "CONCACAF",
    "Uruguay": "CONMEBOL",
    "Uzbekistan": "AFC",
}

FIFA_CODE = {
    "Bosnia & Herzegovina": "BIH",
    "Curaçao": "CUW",
    "Czech Republic": "CZE",
    "DR Congo": "COD",
    "Ivory Coast": "CIV",
    "South Africa": "RSA",
    "South Korea": "KOR",
    "USA": "USA",
}


def code_for(team: str) -> str:
    if team in FIFA_CODE:
        return FIFA_CODE[team]
    words = re.sub(r"[^A-Za-z ]", "", team).split()
    if len(words) == 1:
        return words[0][:3].upper()
    return "".join(w[0] for w in words[:3]).upper()[:3]


def team_id(team: str) -> str:
    slug = re.sub(r"[^A-Z0-9]+", "-", team.upper()).strip("-")
    return f"T-{slug}"


def load_source() -> dict:
    with urllib.request.urlopen(SOURCE_URL, timeout=20) as response:
        return json.load(response)

def parse_kickoff(date_value: str, time_value: str) -> datetime:
    raw = f"{date_value} {time_value}".strip()
    if not raw:
        raise ValueError("missing kickoff time")
    match = re.match(r"^(\d{4}-\d{2}-\d{2})\s+(\d{1,2}):(\d{2})(?:\s+UTC([+-])(\d{1,2}))?$", raw)
    if not match:
        raise ValueError(f"unsupported kickoff time: {raw}")
    date_part, hour, minute, sign, offset = match.groups()
    naive = datetime.strptime(f"{date_part} {hour}:{minute}", "%Y-%m-%d %H:%M")
    if sign and offset:
        direction = 1 if sign == "+" else -1
        tzinfo = timezone(timedelta(hours=direction * int(offset)))
        return naive.replace(tzinfo=tzinfo)
    return naive.replace(tzinfo=SOURCE_TZ)

def to_vietnam_time(date_value: str, time_value: str) -> str:
    try:
        source_dt = parse_kickoff(date_value, time_value)
    except ValueError:
        return ""
    return source_dt.astimezone(VN_TZ).strftime("%Y-%m-%d %H:%M GMT+7")

def match_sort_key(indexed_match: tuple[int, dict]) -> tuple[datetime, int]:
    source_index, match = indexed_match
    return (
        parse_kickoff(match.get("date", ""), match.get("time", "")).astimezone(timezone.utc),
        source_index,
    )


def write_teams(data: dict) -> None:
    groups: dict[str, set[str]] = defaultdict(set)
    for match in data["matches"]:
        group = match.get("group", "")
        if not group.startswith("Group "):
            continue
        for key in ("team1", "team2"):
            groups[match[key]].add(group)

    rows = []
    for team in sorted(groups):
        method = "Host" if team in {"USA", "Canada", "Mexico"} else "Qualified"
        rows.append({
            "team_id": team_id(team),
            "fifa_code": code_for(team),
            "team_name": team,
            "confederation": CONFEDERATION.get(team, "TBD"),
            "qualification_status": "QUALIFIED",
            "qualification_method": method,
            "qualification_date": "",
            "group_name": ";".join(sorted(groups[team])),
            "seed_pot": "",
            "api_provider": "openfootball/worldcup.json",
            "api_team_id": "",
            "flag_url": "",
            "notes": f"Imported from {SOURCE_URL}",
        })

    if len(rows) != 48:
        raise RuntimeError(f"expected 48 group-stage teams, got {len(rows)}")

    path = DATA_DIR / "teams.csv"
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def write_matches(data: dict) -> None:
    rows = []
    indexed_matches = list(enumerate(data["matches"], start=1))
    for index, (source_index, match) in enumerate(sorted(indexed_matches, key=match_sort_key), start=1):
        source_match_id = f"openfootball-2026-{source_index:03d}"
        match_id = f"WC2026-{index:04d}"
        team1 = match.get("team1", "")
        team2 = match.get("team2", "")
        rows.append({
            "match_id": match_id,
            "source": "openfootball/worldcup.json",
            "source_match_id": source_match_id,
            "competition": "FIFA World Cup 2026",
            "stage": match.get("round", ""),
            "group_name": match.get("group", ""),
            "kickoff_at_utc": f"{match.get('date', '')} {match.get('time', '')}".strip(),
            "kickoff_at_local": to_vietnam_time(match.get('date', ''), match.get('time', '')),
            "home_team": team1,
            "away_team": team2,
            "status": "SCHEDULED",
            "home_score": "",
            "away_score": "",
            "result": "",
            "locked_at": "",
            "settled_at": "",
            "admin_id": "",
            "notes": f"ground={match.get('ground', '')}",
        })

    if len(rows) != 104:
        raise RuntimeError(f"expected 104 matches, got {len(rows)}")

    path = DATA_DIR / "matches.csv"
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    data = load_source()
    write_teams(data)
    write_matches(data)
    print("imported 48 teams")
    print("imported 104 matches")


if __name__ == "__main__":
    main()
