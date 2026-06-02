#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import os
import shutil
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.betting_service import BettingService
from src.command_router import CommandRouter
from src.csv_store import CsvStore

SEED_FILES = [
    "members.csv",
    "matches.csv",
    "point_ledger.csv",
    "win_draw_loss_bets.csv",
    "score_bets.csv",
    "admin_actions.csv",
    "match_settlements.csv",
    "final_jackpot.csv",
    "match_sheet_links.csv",
]

MEMBERS = [
    {
        "member_id": "M0001",
        "display_name": "Nam",
        "email": "nam@company.com",
        "google_chat_user_name": "users/111",
        "is_admin": "false",
        "is_workspace_manager": "false",
    },
    {
        "member_id": "M0002",
        "display_name": "Vũ",
        "email": "vu.dang@smilesoftware.org",
        "google_chat_user_name": "users/114436789805633538628",
        "is_admin": "true",
        "is_workspace_manager": "true",
    },
]


def make_temp_store() -> CsvStore:
    tmp_root = Path(tempfile.mkdtemp(prefix="wc2026-glue-"))
    seed_dir = ROOT / "data" / "wc2026_betting"
    for name in SEED_FILES:
        shutil.copy(seed_dir / name, tmp_root / name)
    store = CsvStore(tmp_root)
    store.replace_rows(
        "members.csv",
        [
            {
                "member_id": "M0001",
                "display_name": "Nam",
                "email": "nam@company.com",
                "google_chat_user_name": "users/111",
                "google_chat_display_name": "Nam",
                "is_admin": "false",
                "is_workspace_manager": "false",
                "department": "Tech",
                "status": "ACTIVE",
                "current_balance": "200",
                "created_at": "2026-05-31T00:00:00Z",
                "updated_at": "2026-05-31T00:00:00Z",
                "notes": "seed",
            },
            {
                "member_id": "M0002",
                "display_name": "Vũ",
                "email": "vu.dang@smilesoftware.org",
                "google_chat_user_name": "users/114436789805633538628",
                "google_chat_display_name": "Đặng Nguyên Vũ",
                "is_admin": "true",
                "is_workspace_manager": "true",
                "department": "Ops",
                "status": "ACTIVE",
                "current_balance": "200",
                "created_at": "2026-05-31T00:00:00Z",
                "updated_at": "2026-05-31T00:00:00Z",
                "notes": "seed",
            },
        ],
    )
    store.replace_rows(
        "matches.csv",
        [
            {
                "match_id": "WC2026-0013",
                "source": "seed",
                "source_match_id": "seed-13",
                "competition": "FIFA World Cup 2026",
                "stage": "Group C",
                "group_name": "Group C",
                "kickoff_at_utc": "2026-06-13 18:00 UTC-4",
                "kickoff_at_local": "",
                "home_team": "Brazil",
                "away_team": "Morocco",
                "status": "SCHEDULED",
                "home_score": "",
                "away_score": "",
                "result": "",
                "locked_at": "",
                "settled_at": "",
                "admin_id": "",
                "notes": "seed",
            }
        ],
    )
    members_json = ROOT / "googlechat_members.json"
    shutil.copy(members_json, tmp_root.parent / "googlechat_members.json")
    return store


def test_show_balance() -> None:
    service = BettingService(make_temp_store())
    result = service.show_balance("M0001")
    assert result.intent == "SHOW_BALANCE"
    assert "200" in result.reply_text


def test_place_wdl_bet_updates_balance_and_ledger() -> None:
    store = make_temp_store()
    service = BettingService(store)
    result = service.place_wdl_bet("M0001", "WC2026-0013", "Brazil", 2)
    assert result.intent == "PLACE_WDL_BET"
    assert "-40 point" in result.reply_text
    members = store.read_rows("members.csv")
    assert members[0]["current_balance"] == "160"
    ledger = store.read_rows("point_ledger.csv")
    assert len(ledger) == 1
    assert ledger[0]["related_market"] == "WDL"
    bets = store.read_rows("win_draw_loss_bets.csv")
    assert len(bets) == 1
    assert bets[0]["pick"] == "HOME"


def test_place_score_bet_updates_balance_and_ledger() -> None:
    store = make_temp_store()
    service = BettingService(store)
    result = service.place_score_bet("M0001", "WC2026-0013", 2, 1, 1)
    assert result.intent == "PLACE_SCORE_BET"
    assert "-10 point" in result.reply_text
    members = store.read_rows("members.csv")
    assert members[0]["current_balance"] == "190"
    ledger = store.read_rows("point_ledger.csv")
    assert len(ledger) == 1
    assert ledger[0]["related_market"] == "SCORE"


def test_settle_match_announces_winners_and_marks_rows() -> None:
    store = make_temp_store()
    service = BettingService(store)
    service.place_wdl_bet("M0001", "WC2026-0013", "Brazil", 1)
    service.place_wdl_bet("M0002", "WC2026-0013", "Morocco", 1)
    service.place_score_bet("M0001", "WC2026-0013", 2, 1, 1)
    service.place_score_bet("M0002", "WC2026-0013", 1, 0, 1)

    rows = store.read_rows("matches.csv")
    rows[0]["home_score"] = "2"
    rows[0]["away_score"] = "1"
    rows[0]["result"] = "HOME"
    rows[0]["status"] = "FINISHED"
    store.replace_rows("matches.csv", rows)

    result = service.settle_match("WC2026-0013", admin_id="users/114436789805633538628")
    assert result.intent == "SETTLE_MATCH"
    assert "Kết quả WC2026-0013: Brazil 2-1 Morocco." in result.reply_text
    assert "<users/111>" in result.reply_text
    assert "Point đã cộng vào tài khoản." in result.reply_text

    members = {row["member_id"]: row for row in store.read_rows("members.csv")}
    assert members["M0001"]["current_balance"] == "230"
    assert members["M0002"]["current_balance"] == "170"

    settlements = store.read_rows("match_settlements.csv")
    assert len(settlements) == 2
    assert {row["status"] for row in settlements} == {"ANNOUNCED"}

    actions = store.read_rows("admin_actions.csv")
    assert any(row["action_type"] == "ANNOUNCE_RESULT" for row in actions)


def test_transfer_points_updates_both_balances() -> None:
    store = make_temp_store()
    service = BettingService(store)
    result = service.transfer_points("M0001", "M0002", 50, actor_member_id="M0001")
    assert result.intent == "TRANSFER_POINTS"
    assert "Đã chuyển 50 point từ M0001 cho M0002." in result.reply_text
    members = {row["member_id"]: row for row in store.read_rows("members.csv")}
    assert members["M0001"]["current_balance"] == "150"
    assert members["M0002"]["current_balance"] == "250"
    ledger = store.read_rows("point_ledger.csv")
    assert len(ledger) == 2
    assert {row["change_type"] for row in ledger} == {"TRANSFER_OUT", "TRANSFER_IN"}


def test_router_handles_balance_event() -> None:
    store = make_temp_store()
    router = CommandRouter(BettingService(store))
    event = {
        "user": {"name": "users/111", "displayName": "Nam", "email": "nam@company.com"},
        "message": {"text": "@SmileAI xem điểm của mình", "thread": {"name": "spaces/AAA/threads/BBB"}, "createTime": "2026-05-31T01:00:00Z"},
        "space": {"name": "spaces/AAA"},
    }
    reply = router.handle_event(event, MEMBERS)
    assert reply.ok is True
    assert reply.intent == "SHOW_BALANCE"


def test_router_handles_score_event() -> None:
    store = make_temp_store()
    router = CommandRouter(BettingService(store))
    event = {
        "user": {"name": "users/111", "displayName": "Nam", "email": "nam@company.com"},
        "message": {"text": "@SmileAI đặt tỷ số 2-1 trận WC2026-0013", "thread": {"name": "spaces/AAA/threads/BBB"}, "createTime": "2026-05-31T01:00:00Z"},
        "space": {"name": "spaces/AAA"},
    }
    reply = router.handle_event(event, MEMBERS)
    assert reply.ok is True
    assert reply.intent == "PLACE_SCORE_BET"

def test_router_handles_match_link_event() -> None:
    store = make_temp_store()
    router = CommandRouter(BettingService(store))
    previous = os.environ.get("SMILE_BET_MATCH_BETS_SPREADSHEET_ID")
    os.environ["SMILE_BET_MATCH_BETS_SPREADSHEET_ID"] = "seed-spreadsheet-id"
    event = {
        "user": {"name": "users/111", "displayName": "Nam", "email": "nam@company.com"},
        "message": {"text": "@SmileAI link trận WC2026-0013", "thread": {"name": "spaces/AAA/threads/BBB"}, "createTime": "2026-05-31T01:00:00Z"},
        "space": {"name": "spaces/AAA"},
    }
    try:
        reply = router.handle_event(event, MEMBERS)
        assert reply.ok is True
        assert reply.intent == "SHOW_MATCH_SHEET_LINK"
        assert "https://docs.google.com/spreadsheets/d/seed-spreadsheet-id" in reply.message
        assert "WC2026-0013" in reply.message
    finally:
        if previous is None:
            os.environ.pop("SMILE_BET_MATCH_BETS_SPREADSHEET_ID", None)
        else:
            os.environ["SMILE_BET_MATCH_BETS_SPREADSHEET_ID"] = previous


def test_router_handles_transfer_event() -> None:
    store = make_temp_store()
    router = CommandRouter(BettingService(store))
    event = {
        "user": {"name": "users/111", "displayName": "Nam", "email": "nam@company.com"},
        "message": {"text": "@SmileAI chuyển 50 point cho Vũ", "thread": {"name": "spaces/AAA/threads/BBB"}, "createTime": "2026-05-31T01:00:00Z"},
        "space": {"name": "spaces/AAA"},
    }
    reply = router.handle_event(event, MEMBERS)
    assert reply.ok is True
    assert reply.intent == "TRANSFER_POINTS"
    assert "Đã chuyển 50 point" in reply.message


def test_router_handles_transfer_event_with_google_chat_mention() -> None:
    store = make_temp_store()
    router = CommandRouter(BettingService(store))
    event = {
        "user": {"name": "users/111", "displayName": "Nam", "email": "nam@company.com"},
        "message": {"text": "@SmileAI chuyển 50 point cho <users/114436789805633538628>", "thread": {"name": "spaces/AAA/threads/BBB"}, "createTime": "2026-05-31T01:00:00Z"},
        "space": {"name": "spaces/AAA"},
    }
    reply = router.handle_event(event, MEMBERS)
    assert reply.ok is True
    assert reply.intent == "TRANSFER_POINTS"
    assert "Đã chuyển 50 point" in reply.message


def test_router_handles_settle_event() -> None:
    store = make_temp_store()
    service = BettingService(store)
    service.place_wdl_bet("M0001", "WC2026-0013", "Brazil", 1)
    rows = store.read_rows("matches.csv")
    rows[0]["home_score"] = "1"
    rows[0]["away_score"] = "0"
    rows[0]["result"] = "HOME"
    rows[0]["status"] = "FINISHED"
    store.replace_rows("matches.csv", rows)

    router = CommandRouter(service)
    event = {
        "user": {"name": "users/114436789805633538628", "displayName": "Đặng Nguyên Vũ", "email": "vu.dang@smilesoftware.org"},
        "membership": {"role": "ROLE_MANAGER"},
        "message": {"text": "@SmileAI settle trận WC2026-0013", "thread": {"name": "spaces/AAA/threads/BBB"}, "createTime": "2026-05-31T01:00:00Z"},
        "space": {"name": "spaces/AAA"},
    }
    reply = router.handle_event(event, MEMBERS)
    assert reply.ok is True
    assert reply.intent == "SETTLE_MATCH"
    assert "Kết quả WC2026-0013" in reply.message


def main() -> int:
    tests = [
        test_show_balance,
        test_place_wdl_bet_updates_balance_and_ledger,
        test_place_score_bet_updates_balance_and_ledger,
        test_settle_match_announces_winners_and_marks_rows,
        test_transfer_points_updates_both_balances,
        test_router_handles_balance_event,
        test_router_handles_score_event,
        test_router_handles_match_link_event,
        test_router_handles_transfer_event,
        test_router_handles_transfer_event_with_google_chat_mention,
        test_router_handles_settle_event,
    ]
    failures = 0
    for test in tests:
        try:
            test()
        except Exception as exc:
            failures += 1
            print(f"FAIL {test.__name__}: {exc}")
        else:
            print(f"PASS {test.__name__}")
    print(f"summary: {len(tests) - failures} passed, {failures} failed")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
