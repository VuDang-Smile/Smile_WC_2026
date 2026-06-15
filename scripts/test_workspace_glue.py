#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import csv
import os
import shutil
import sys
import tempfile
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.betting_service import BettingService, CommandResult
from src.command_router import CommandRouter
from src.csv_store import CsvStore, build_store
from scripts.export_match_bet_sheets import build_match_sheet_rows

FILE_HEADERS = {
    "members.csv": [
        "member_id", "display_name", "email", "google_chat_user_name", "google_chat_display_name",
        "is_admin", "is_workspace_manager", "department", "status", "current_balance",
        "created_at", "updated_at", "notes",
    ],
    "matches.csv": [
        "match_id", "source", "source_match_id", "competition", "stage", "group_name",
        "kickoff_at_utc", "kickoff_at_local", "home_team", "away_team", "status",
        "home_score", "away_score", "result", "locked_at", "settled_at", "admin_id", "notes",
    ],
    "point_ledger.csv": [
        "ledger_id", "created_at", "member_id", "change_type", "points_delta", "balance_after",
        "balance_before", "related_match_id", "related_market", "related_bet_id", "admin_id", "reason",
        "actor_member_id", "counterparty_member_id", "match_home_team", "match_away_team",
        "ticket_count", "unit_points", "pick", "predicted_score", "settlement_id",
    ],
    "win_draw_loss_bets.csv": [
        "bet_id", "created_at", "member_id", "match_id", "pick", "ticket_count", "points_staked",
        "status", "locked_at", "settlement_id", "payout_points", "net_points", "notes",
    ],
    "score_bets.csv": [
        "bet_id", "created_at", "member_id", "match_id", "predicted_home_score", "predicted_away_score",
        "ticket_count", "points_staked", "status", "locked_at", "settlement_id", "payout_points",
        "net_points", "carryover_points", "notes",
    ],
    "admin_actions.csv": [
        "action_id", "created_at", "admin_id", "action_type", "target_type", "target_id", "points_delta", "reason",
    ],
    "match_settlements.csv": [
        "settlement_id", "settled_at", "match_id", "market", "result_key", "total_staked_points",
        "winning_staked_points", "losing_staked_points", "winner_ticket_count", "payout_per_ticket",
        "carryover_points", "admin_id", "status", "notes",
    ],
    "final_jackpot.csv": [
        "entry_id", "created_at", "source_match_id", "points_delta", "balance_after", "reason", "settlement_id", "admin_id",
    ],
    "match_sheet_links.csv": ["match_id", "spreadsheet_id", "sheet_gid", "sheet_url"],
}

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
    for name, headers in FILE_HEADERS.items():
        with (tmp_root / name).open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=headers)
            writer.writeheader()
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

def test_admin_adjust_points_writes_ledger_and_action() -> None:
    store = make_temp_store()
    service = BettingService(store)
    result = service.admin_adjust_points("M0001", 25, admin_id="users/114436789805633538628", reason="Manual correction")
    assert result.intent == "ADMIN_ADJUST_POINTS"
    members = {row["member_id"]: row for row in store.read_rows("members.csv")}
    assert members["M0001"]["current_balance"] == "225"
    ledger = store.read_rows("point_ledger.csv")
    assert len(ledger) == 1
    assert ledger[0]["change_type"] == "ADMIN_TOPUP"
    assert ledger[0]["actor_member_id"] == "users/114436789805633538628"
    actions = store.read_rows("admin_actions.csv")
    assert len(actions) == 1
    assert actions[0]["action_type"] == "ADMIN_TOPUP"

def test_match_sheet_rows_keep_settled_bets_inline() -> None:
    store = make_temp_store()
    service = BettingService(store)
    service.place_wdl_bet("M0001", "WC2026-0013", "Brazil", 1)
    rows = store.read_rows("matches.csv")
    rows[0]["home_score"] = "2"
    rows[0]["away_score"] = "1"
    rows[0]["result"] = "HOME"
    rows[0]["status"] = "FINISHED"
    store.replace_rows("matches.csv", rows)
    service.settle_match("WC2026-0013", admin_id="users/114436789805633538628")

    match = store.read_rows("matches.csv")[0]
    member_rows = [
        {
            "member_id": "M0001",
            "display_name": "Nam",
            "email": "nam@company.com",
            "wdl_entries": [
                {
                    "selection": "HOME",
                    "ticket_count": "1",
                    "points_staked": "20",
                    "latest_bet_at": store.read_rows("win_draw_loss_bets.csv")[0]["created_at"],
                    "status": "SETTLED",
                    "payout_points": "40",
                    "net_points": "20",
                }
            ],
            "score_entries": [],
            "latest_bet_at": store.read_rows("win_draw_loss_bets.csv")[0]["created_at"],
        }
    ]
    sheet_rows = build_match_sheet_rows(
        match,
        member_rows,
        settled_wdl_rows=store.read_rows("win_draw_loss_bets.csv"),
        settled_score_rows=store.read_rows("score_bets.csv"),
        settlement_rows=store.read_rows("match_settlements.csv"),
        members={row["member_id"]: row for row in store.read_rows("members.csv")},
    )
    assert any(row["status"] == "SETTLED" and row["payout_points"] == "40" and row["net_points"] == "20" for row in sheet_rows if row["section"] == "KÈO THẮNG/THUA")

def test_public_rows_keep_row_level_score_payouts() -> None:
    member_rows = [
        {
            "member_id": "M0001",
            "display_name": "Nam",
            "email": "nam@company.com",
            "wdl_entries": [],
            "score_entries": [
                {"selection": "3-1", "ticket_count": "1", "points_staked": "10", "latest_bet_at": "t1", "status": "SETTLED", "payout_points": "0", "net_points": "-10"},
                {"selection": "2-0", "ticket_count": "1", "points_staked": "10", "latest_bet_at": "t1", "status": "SETTLED", "payout_points": "60", "net_points": "50"},
                {"selection": "0-1", "ticket_count": "1", "points_staked": "10", "latest_bet_at": "t1", "status": "SETTLED", "payout_points": "0", "net_points": "-10"},
            ],
            "latest_bet_at": "t1",
        }
    ]
    rows = build_match_sheet_rows(
        {
            "match_id": "WC2026-0001",
            "home_team": "Mexico",
            "away_team": "South Africa",
            "stage": "Matchday 1",
            "group_name": "Group A",
            "kickoff_at_local": "2026-06-12 01:00 GMT+7",
            "home_score": "2",
            "away_score": "0",
            "status": "SETTLED",
        },
        member_rows,
    )
    score_rows = [row for row in rows if row["section"] == "KÈO TỶ SỐ" and row["member_id"] == "M0001"]
    assert any(row["selection"] == "3-1" and row["status"] == "SETTLED" and row["payout_points"] == "0" and row["net_points"] == "-10" for row in score_rows)
    assert any(row["selection"] == "2-0" and row["status"] == "SETTLED" and row["payout_points"] == "60" and row["net_points"] == "50" for row in score_rows)
    assert any(row["selection"] == "0-1" and row["status"] == "SETTLED" and row["payout_points"] == "0" and row["net_points"] == "-10" for row in score_rows)


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
        assert "https://docs.google.com/spreadsheets/d/" in reply.message
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

def test_router_handles_sync_results_event() -> None:
    store = make_temp_store()
    service = BettingService(store)
    router = CommandRouter(service)
    with patch.object(service, "sync_results_and_settle_ready_matches") as mock_sync:
        mock_sync.return_value = CommandResult(
            intent="SYNC_RESULTS_AND_SETTLE",
            reply_text="Đã sync API: 1 trận cập nhật. Đã settle: 1 trận.",
            data={"updated_match_count": 1, "settled_match_count": 1, "settled_match_ids": ["WC2026-0013"]},
        )
        event = {
            "user": {"name": "users/114436789805633538628", "displayName": "Đặng Nguyên Vũ", "email": "vu.dang@smilesoftware.org"},
            "membership": {"role": "ROLE_MANAGER"},
            "message": {"text": "@SmileAI cập nhật kết quả", "thread": {"name": "spaces/AAA/threads/BBB"}, "createTime": "2026-05-31T01:00:00Z"},
            "space": {"name": "spaces/AAA"},
        }
        reply = router.handle_event(event, MEMBERS)
    assert reply.ok is True
    assert reply.intent == "SYNC_RESULTS_AND_SETTLE"
    mock_sync.assert_called_once_with(admin_id="users/114436789805633538628")

def test_build_store_csv_mode() -> None:
    previous_mode = os.environ.get("SMILE_BET_STORE")
    previous_dir = os.environ.get("SMILE_BET_DATA_DIR")
    tmp_root = Path(tempfile.mkdtemp(prefix="wc2026-store-"))
    os.environ["SMILE_BET_STORE"] = "csv"
    os.environ["SMILE_BET_DATA_DIR"] = str(tmp_root)
    try:
        store = build_store()
        assert isinstance(store, CsvStore)
        assert store.data_dir == tmp_root
    finally:
        if previous_mode is None:
            os.environ.pop("SMILE_BET_STORE", None)
        else:
            os.environ["SMILE_BET_STORE"] = previous_mode
        if previous_dir is None:
            os.environ.pop("SMILE_BET_DATA_DIR", None)
        else:
            os.environ["SMILE_BET_DATA_DIR"] = previous_dir



def test_mutating_actions_run_post_action_checks() -> None:
    store = make_temp_store()
    service = BettingService(store)
    with patch.object(service, "_run_post_action_checks") as mock_checks:
        service.place_wdl_bet("M0001", "WC2026-0013", "Brazil", 1)
        mock_checks.assert_called_once_with(match_id="WC2026-0013", touched_member_ids=["M0001"])


def test_audit_hook_builds_expected_command() -> None:
    store = make_temp_store()
    service = BettingService(store)
    service.workspace_root = ROOT
    previous = os.environ.get("SMILE_BET_AUDIT_AFTER_ACTION")
    os.environ["SMILE_BET_AUDIT_AFTER_ACTION"] = "true"
    with patch("src.betting_service.subprocess.run") as mock_run:
        with patch.dict(os.environ, {"SMILE_BET_GOOGLE_SERVICE_ACCOUNT": ".secret/googlechat-service-account.json"}, clear=False):
            service._audit_if_enabled(match_id="WC2026-0013", touched_member_ids=["M0001", "M0002"])
    assert mock_run.call_args is not None
    cmd = mock_run.call_args.kwargs["args"] if "args" in mock_run.call_args.kwargs else mock_run.call_args.args[0]
    assert str(service.workspace_root / "scripts" / "audit_openclaw_state.py") in cmd
    assert "--match-id" in cmd
    assert "WC2026-0013" in cmd
    assert cmd.count("--member-id") == 2
    if previous is None:
        os.environ.pop("SMILE_BET_AUDIT_AFTER_ACTION", None)
    else:
        os.environ["SMILE_BET_AUDIT_AFTER_ACTION"] = previous

def main() -> int:
    tests = [
        test_show_balance,
        test_place_wdl_bet_updates_balance_and_ledger,
        test_place_score_bet_updates_balance_and_ledger,
        test_settle_match_announces_winners_and_marks_rows,
        test_transfer_points_updates_both_balances,
        test_admin_adjust_points_writes_ledger_and_action,
        test_match_sheet_rows_keep_settled_bets_inline,
        test_public_rows_keep_row_level_score_payouts,
        test_router_handles_balance_event,
        test_router_handles_score_event,
        test_router_handles_match_link_event,
        test_router_handles_transfer_event,
        test_router_handles_transfer_event_with_google_chat_mention,
        test_router_handles_settle_event,
        test_router_handles_sync_results_event,
        test_mutating_actions_run_post_action_checks,
        test_audit_hook_builds_expected_command,
        test_build_store_csv_mode,
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
