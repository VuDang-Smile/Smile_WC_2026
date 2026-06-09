from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, ROUND_DOWN
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from typing import Iterable
from zoneinfo import ZoneInfo

from src.csv_store import CsvStore, RowStore, build_store

WDL_PRICE = Decimal("20")
SCORE_PRICE = Decimal("10")
VN_TZ = ZoneInfo("Asia/Ho_Chi_Minh")
DRAW_ALIASES = {"hoa", "hòa", "draw", "x"}
HOME_ALIASES = {"home", "chu nha", "chủ nhà", "doi chu nha", "đội chủ nhà", "thang", "thắng"}
AWAY_ALIASES = {"away", "doi khach", "đội khách"}


class BettingError(ValueError):
    pass


@dataclass(frozen=True)
class CommandResult:
    intent: str
    reply_text: str
    data: dict[str, object]


class BettingService:
    def __init__(self, store: RowStore | None = None) -> None:
        self.store = store or build_store()
        self.workspace_root = self.store.data_dir.parent.parent

    def show_balance(self, member_id: str) -> CommandResult:
        member = self._get_member(member_id)
        balance = self._member_balance(member)
        return CommandResult(
            intent="SHOW_BALANCE",
            reply_text=f"Số dư hiện tại {member_id}: {self._fmt_points(balance)} point.",
            data={"member_id": member_id, "balance": str(balance)},
        )

    def show_match_sheet_link(self, match_id: str) -> CommandResult:
        match = self._get_match(match_id)
        link_row = self._get_match_sheet_link(match_id)
        url = (link_row.get("sheet_url", "") if link_row else "").strip()
        if not url:
            workbook_id = os.environ.get("SMILE_BET_MATCH_BETS_SPREADSHEET_ID", "").strip()
            if workbook_id:
                url = f"https://docs.google.com/spreadsheets/d/{workbook_id}"
        if not url:
            raise BettingError(
                f"Chưa có link sheet cho trận {match_id}. Cần chạy export/upload sheet trận trước."
            )

        reply = (
            f"Link sheet trận {match_id}: {match.get('home_team', '')} vs {match.get('away_team', '')} - {url}"
        )
        return CommandResult(
            intent="SHOW_MATCH_SHEET_LINK",
            reply_text=reply,
            data={
                "match_id": match_id,
                "home_team": match.get("home_team", ""),
                "away_team": match.get("away_team", ""),
                "sheet_url": url,
                "sheet_gid": link_row.get("sheet_gid", "") if link_row else "",
                "spreadsheet_id": link_row.get("spreadsheet_id", "") if link_row else workbook_id,
            },
        )

    def place_wdl_bet(self, member_id: str, match_id: str, pick: str, ticket_count: int) -> CommandResult:
        if ticket_count <= 0:
            raise BettingError("Số vé phải > 0.")
        member = self._get_member(member_id)
        match = self._get_match(match_id)
        self._ensure_match_open(match)
        normalized_pick = self._normalize_pick(pick, match)
        stake = WDL_PRICE * ticket_count
        balance_before = self._member_balance(member)
        if balance_before < stake:
            raise BettingError(
                f"Không đủ point. Cần {self._fmt_points(stake)}, hiện có {self._fmt_points(balance_before)}."
            )

        created_at = self._now_iso()
        bet_id = self._next_id("win_draw_loss_bets.csv", "bet_id", f"B-WDL-{match_id}-{member_id}")
        ledger_id = self._next_ledger_id()
        balance_after = balance_before - stake

        self.store.append_row(
            "win_draw_loss_bets.csv",
            {
                "bet_id": bet_id,
                "created_at": created_at,
                "member_id": member_id,
                "match_id": match_id,
                "pick": normalized_pick,
                "ticket_count": ticket_count,
                "points_staked": self._fmt_points(stake),
                "status": "ACTIVE",
                "locked_at": match.get("locked_at", ""),
                "settlement_id": "",
                "payout_points": "",
                "net_points": "",
                "notes": "Created by workspace betting_service",
            },
        )
        self._append_ledger_entry(
            ledger_id=ledger_id,
            created_at=created_at,
            member_id=member_id,
            change_type="BET_STAKE",
            points_delta=-stake,
            balance_before=balance_before,
            balance_after=balance_after,
            related_match_id=match_id,
            related_market="WDL",
            related_bet_id=bet_id,
            reason=f"{normalized_pick} x{ticket_count}",
            actor_member_id=member_id,
            match=match,
            ticket_count=ticket_count,
            unit_points=WDL_PRICE,
            pick=normalized_pick,
        )
        self._update_member_balance(member_id, balance_after)
        self._run_post_action_checks(match_id=match_id, touched_member_ids=[member_id])
        return CommandResult(
            intent="PLACE_WDL_BET",
            reply_text=(
                f"Đã ghi cược: {member_id}, {match_id}, {normalized_pick}, {ticket_count} vé, "
                f"-{self._fmt_points(stake)} point. Số dư: {self._fmt_points(balance_after)}."
            ),
            data={
                "member_id": member_id,
                "match_id": match_id,
                "pick": normalized_pick,
                "ticket_count": ticket_count,
                "stake": str(stake),
                "balance_after": str(balance_after),
            },
        )

    def place_score_bet(self, member_id: str, match_id: str, home_score: int, away_score: int, ticket_count: int) -> CommandResult:
        if ticket_count <= 0:
            raise BettingError("Số vé phải > 0.")
        if home_score < 0 or away_score < 0:
            raise BettingError("Tỷ số phải >= 0.")
        member = self._get_member(member_id)
        match = self._get_match(match_id)
        self._ensure_match_open(match)
        stake = SCORE_PRICE * ticket_count
        balance_before = self._member_balance(member)
        if balance_before < stake:
            raise BettingError(
                f"Không đủ point. Cần {self._fmt_points(stake)}, hiện có {self._fmt_points(balance_before)}."
            )

        created_at = self._now_iso()
        bet_id = self._next_id("score_bets.csv", "bet_id", f"B-SCORE-{match_id}-{member_id}")
        ledger_id = self._next_ledger_id()
        balance_after = balance_before - stake

        self.store.append_row(
            "score_bets.csv",
            {
                "bet_id": bet_id,
                "created_at": created_at,
                "member_id": member_id,
                "match_id": match_id,
                "predicted_home_score": home_score,
                "predicted_away_score": away_score,
                "ticket_count": ticket_count,
                "points_staked": self._fmt_points(stake),
                "status": "ACTIVE",
                "locked_at": match.get("locked_at", ""),
                "settlement_id": "",
                "payout_points": "",
                "net_points": "",
                "carryover_points": "",
                "notes": "Created by workspace betting_service",
            },
        )
        self._append_ledger_entry(
            ledger_id=ledger_id,
            created_at=created_at,
            member_id=member_id,
            change_type="BET_STAKE",
            points_delta=-stake,
            balance_before=balance_before,
            balance_after=balance_after,
            related_match_id=match_id,
            related_market="SCORE",
            related_bet_id=bet_id,
            reason=f"{home_score}-{away_score} x{ticket_count}",
            actor_member_id=member_id,
            match=match,
            ticket_count=ticket_count,
            unit_points=SCORE_PRICE,
            predicted_home_score=home_score,
            predicted_away_score=away_score,
        )
        self._update_member_balance(member_id, balance_after)
        self._run_post_action_checks(match_id=match_id, touched_member_ids=[member_id])
        return CommandResult(
            intent="PLACE_SCORE_BET",
            reply_text=(
                f"Đã ghi cược tỷ số: {member_id}, {match_id}, {home_score}-{away_score}, {ticket_count} vé, "
                f"-{self._fmt_points(stake)} point. Số dư: {self._fmt_points(balance_after)}."
            ),
            data={
                "member_id": member_id,
                "match_id": match_id,
                "home_score": home_score,
                "away_score": away_score,
                "ticket_count": ticket_count,
                "stake": str(stake),
                "balance_after": str(balance_after),
            },
        )

    def settle_match(self, match_id: str, admin_id: str = "") -> CommandResult:
        match = self._get_match(match_id)
        home_score, away_score = self._parse_match_score(match)
        settled_rows = self.store.read_rows("match_settlements.csv")
        if any(row.get("match_id") == match_id and row.get("status") == "SETTLED" for row in settled_rows):
            raise BettingError(f"Trận {match_id} đã settle rồi.")
        if any(row.get("match_id") == match_id and row.get("status") == "ANNOUNCED" for row in settled_rows):
            raise BettingError(f"Trận {match_id} đã settle và đã announce rồi.")

        members = {row.get("member_id", ""): row for row in self.store.read_rows("members.csv")}
        created_at = self._now_iso()
        match_result = self._match_result(home_score, away_score)

        wdl = self._settle_wdl_market(match, members, admin_id, created_at, match_result)
        score = self._settle_score_market(match, members, admin_id, created_at, home_score, away_score)
        self._mark_match_settled(match_id, admin_id, created_at)

        announcement = self._build_announcement(match, home_score, away_score, wdl, score, members)
        announce_action_id = self._next_id("admin_actions.csv", "action_id", f"A-ANNOUNCE-{match_id}")
        self.store.append_row(
            "admin_actions.csv",
            {
                "action_id": announce_action_id,
                "created_at": created_at,
                "admin_id": admin_id,
                "action_type": "ANNOUNCE_RESULT",
                "target_type": "match",
                "target_id": match_id,
                "points_delta": "0",
                "reason": announcement,
            },
        )
        self._mark_settlement_announced(match_id, created_at)
        touched_member_ids = sorted(set(wdl["winner_member_ids"] + score["winner_member_ids"]))
        self._run_post_action_checks(match_id=match_id, touched_member_ids=touched_member_ids)

        return CommandResult(
            intent="SETTLE_MATCH",
            reply_text=announcement,
            data={
                "match_id": match_id,
                "home_score": home_score,
                "away_score": away_score,
                "wdl_settlement_id": wdl["settlement_id"],
                "score_settlement_id": score["settlement_id"],
                "announcement": announcement,
                "wdl_winners": wdl["winner_member_ids"],
                "score_winners": score["winner_member_ids"],
            },
        )

    def transfer_points(self, from_member_id: str, to_member_id: str, points: int, actor_member_id: str | None = None) -> CommandResult:
        if points <= 0:
            raise BettingError("Số point chuyển phải > 0.")
        if not actor_member_id or actor_member_id != from_member_id:
            raise BettingError("Chỉ được chuyển point từ tài khoản của chính mình.")
        if from_member_id == to_member_id:
            raise BettingError("Không thể tự chuyển point cho chính mình.")

        from_member = self._get_member(from_member_id)
        to_member = self._get_member(to_member_id)
        from_balance = self._member_balance(from_member)
        transfer_amount = Decimal(points)
        if from_balance < transfer_amount:
            raise BettingError(
                f"Không đủ point để chuyển. Cần {self._fmt_points(transfer_amount)}, hiện có {self._fmt_points(from_balance)}."
            )

        created_at = self._now_iso()
        from_balance_after = from_balance - transfer_amount
        to_balance_before = self._member_balance(to_member)
        to_balance_after = to_balance_before + transfer_amount
        transfer_ref = self._next_id("admin_actions.csv", "action_id", f"XFER-{from_member_id}-{to_member_id}")

        self._append_ledger_entry(
            ledger_id=self._next_ledger_id(),
            created_at=created_at,
            member_id=from_member_id,
            change_type="TRANSFER_OUT",
            points_delta=-transfer_amount,
            balance_before=from_balance,
            balance_after=from_balance_after,
            related_market="TRANSFER",
            related_bet_id=transfer_ref,
            reason=f"Chuyển cho {to_member_id}",
            actor_member_id=from_member_id,
            counterparty_member_id=to_member_id,
        )
        self._append_ledger_entry(
            ledger_id=self._next_ledger_id(),
            created_at=created_at,
            member_id=to_member_id,
            change_type="TRANSFER_IN",
            points_delta=transfer_amount,
            balance_before=to_balance_before,
            balance_after=to_balance_after,
            related_market="TRANSFER",
            related_bet_id=transfer_ref,
            admin_id=from_member_id,
            reason=f"Nhận từ {from_member_id}",
            actor_member_id=from_member_id,
            counterparty_member_id=from_member_id,
        )
        self._update_member_balance(from_member_id, from_balance_after)
        self._update_member_balance(to_member_id, to_balance_after)
        self.store.append_row(
            "admin_actions.csv",
            {
                "action_id": transfer_ref,
                "created_at": created_at,
                "admin_id": from_member_id,
                "action_type": "TRANSFER_POINTS",
                "target_type": "member",
                "target_id": to_member_id,
                "points_delta": self._fmt_points(transfer_amount),
                "reason": f"from={from_member_id}",
            },
        )
        self._run_post_action_checks(touched_member_ids=[from_member_id, to_member_id])
        return CommandResult(
            intent="TRANSFER_POINTS",
            reply_text=(
                f"Đã chuyển {self._fmt_points(transfer_amount)} point từ {from_member_id} cho {to_member_id}. "
                f"Số dư mới: {self._fmt_points(from_balance_after)}."
            ),
            data={
                "from_member_id": from_member_id,
                "to_member_id": to_member_id,
                "points": str(transfer_amount),
                "from_balance_after": str(from_balance_after),
                "to_balance_after": str(to_balance_after),
                "transfer_ref": transfer_ref,
            },
        )

    def admin_adjust_points(
        self,
        member_id: str,
        points_delta: Decimal,
        admin_id: str,
        reason: str,
    ) -> CommandResult:
        points_delta = Decimal(str(points_delta))
        if points_delta == 0:
            raise BettingError("Điều chỉnh point phải khác 0.")
        if not admin_id:
            raise BettingError("Thiếu admin_id cho điều chỉnh point.")
        member = self._get_member(member_id)
        balance_before = self._member_balance(member)
        balance_after = balance_before + points_delta
        if balance_after < 0:
            raise BettingError(
                f"Không đủ point sau điều chỉnh. Hiện có {self._fmt_points(balance_before)}, delta {self._fmt_points(points_delta)}."
            )
        created_at = self._now_iso()
        ref = self._next_id("admin_actions.csv", "action_id", f"A-POINT-{member_id}")
        change_type = "ADMIN_TOPUP" if points_delta > 0 else "ADMIN_DEBIT"
        self._append_ledger_entry(
            ledger_id=self._next_ledger_id(),
            created_at=created_at,
            member_id=member_id,
            change_type=change_type,
            points_delta=points_delta,
            balance_before=balance_before,
            balance_after=balance_after,
            related_market="ADMIN_ADJUST",
            related_bet_id=ref,
            admin_id=admin_id,
            reason=reason,
            actor_member_id=admin_id,
        )
        self._update_member_balance(member_id, balance_after)
        self.store.append_row(
            "admin_actions.csv",
            {
                "action_id": ref,
                "created_at": created_at,
                "admin_id": admin_id,
                "action_type": change_type,
                "target_type": "member",
                "target_id": member_id,
                "points_delta": self._fmt_points(points_delta),
                "reason": reason,
            },
        )
        self._run_post_action_checks(touched_member_ids=[member_id])
        return CommandResult(
            intent="ADMIN_ADJUST_POINTS",
            reply_text=(
                f"Đã điều chỉnh {self._fmt_points(points_delta)} point cho {member_id}. "
                f"Số dư mới: {self._fmt_points(balance_after)}."
            ),
            data={
                "member_id": member_id,
                "points_delta": self._fmt_points(points_delta),
                "balance_before": self._fmt_points(balance_before),
                "balance_after": self._fmt_points(balance_after),
                "admin_id": admin_id,
                "action_id": ref,
            },
        )

    def _settle_wdl_market(
        self,
        match: dict[str, str],
        members: dict[str, dict[str, str]],
        admin_id: str,
        created_at: str,
        result_key: str,
    ) -> dict[str, object]:
        match_id = match["match_id"]
        bets = [row for row in self.store.read_rows("win_draw_loss_bets.csv") if row.get("match_id") == match_id and row.get("status") == "ACTIVE"]
        total_tickets = sum(self._to_int(row.get("ticket_count")) for row in bets)
        total_staked = WDL_PRICE * total_tickets
        settlement_id = f"S-WDL-{match_id}"

        payouts: dict[str, Decimal] = {}
        winner_rows: list[dict[str, str]] = []
        winning_staked = Decimal("0")
        losing_staked = total_staked
        winner_ticket_count = 0
        payout_per_ticket = Decimal("0")
        notes = ""

        wdl_carryover = Decimal("0")
        if bets:
            home_tickets = sum(self._to_int(row.get("ticket_count")) for row in bets if (row.get("pick") or "").upper() == "HOME")
            away_tickets = sum(self._to_int(row.get("ticket_count")) for row in bets if (row.get("pick") or "").upper() == "AWAY")
            if home_tickets == 0 or away_tickets == 0:
                wdl_carryover = total_staked
                notes = "WDL single-sided pool moved to jackpot"
                self._append_jackpot_entry(match_id, wdl_carryover, settlement_id, admin_id, created_at, reason="Carryover from WDL single-sided pool")
            elif result_key == "DRAW" and not any((row.get("pick") or "").upper() == "DRAW" for row in bets):
                half_pool = total_staked / Decimal("2")
                for side in ("HOME", "AWAY"):
                    side_rows = [row for row in bets if (row.get("pick") or "").upper() == side]
                    side_tickets = sum(self._to_int(row.get("ticket_count")) for row in side_rows)
                    if side_tickets == 0:
                        continue
                    per_ticket = half_pool / Decimal(side_tickets)
                    for row in side_rows:
                        tickets = self._to_int(row.get("ticket_count"))
                        amount = self._money(per_ticket * tickets)
                        payouts[row["member_id"]] = payouts.get(row["member_id"], Decimal("0")) + amount
                        winner_rows.append(row)
                    winner_ticket_count += side_tickets
                winning_staked = total_staked
                losing_staked = Decimal("0")
                payout_per_ticket = self._money(half_pool / Decimal(max(1, winner_ticket_count // 2 or 1))) if winner_ticket_count else Decimal("0")
                notes = "DRAW fallback split across HOME and AWAY"
            else:
                winner_rows = [row for row in bets if (row.get("pick") or "").upper() == result_key]
                winner_ticket_count = sum(self._to_int(row.get("ticket_count")) for row in winner_rows)
                winning_staked = WDL_PRICE * winner_ticket_count
                losing_staked = total_staked - winning_staked
                if winner_ticket_count > 0:
                    profit_per_ticket = losing_staked / Decimal(winner_ticket_count)
                    payout_per_ticket = self._money(WDL_PRICE + profit_per_ticket)
                    for row in winner_rows:
                        tickets = self._to_int(row.get("ticket_count"))
                        amount = self._money(payout_per_ticket * tickets)
                        payouts[row["member_id"]] = payouts.get(row["member_id"], Decimal("0")) + amount
                else:
                    notes = "No WDL winner"

        self._apply_payouts(payouts, members, created_at, match_id, "WDL", settlement_id, admin_id)
        self._replace_wdl_bets(match_id, settlement_id, payouts)
        self.store.append_row(
            "match_settlements.csv",
            {
                "settlement_id": settlement_id,
                "settled_at": created_at,
                "match_id": match_id,
                "market": "WDL",
                "result_key": result_key,
                "total_staked_points": self._fmt_points(total_staked),
                "winning_staked_points": self._fmt_points(winning_staked),
                "losing_staked_points": self._fmt_points(losing_staked),
                "winner_ticket_count": str(winner_ticket_count),
                "payout_per_ticket": self._fmt_points(payout_per_ticket),
                "carryover_points": self._fmt_points(wdl_carryover),
                "admin_id": admin_id,
                "status": "SETTLED",
                "notes": notes,
            },
        )
        self.store.append_row(
            "admin_actions.csv",
            {
                "action_id": self._next_id("admin_actions.csv", "action_id", f"A-SETTLE-WDL-{match_id}"),
                "created_at": created_at,
                "admin_id": admin_id,
                "action_type": "SETTLE_WDL",
                "target_type": "match",
                "target_id": match_id,
                "points_delta": self._fmt_points(sum(payouts.values(), Decimal("0"))),
                "reason": settlement_id,
            },
        )
        return {
            "settlement_id": settlement_id,
            "winner_member_ids": sorted(payouts.keys()),
            "payouts": payouts,
            "winner_ticket_count": winner_ticket_count,
            "carryover": wdl_carryover,
        }

    def _settle_score_market(
        self,
        match: dict[str, str],
        members: dict[str, dict[str, str]],
        admin_id: str,
        created_at: str,
        home_score: int,
        away_score: int,
    ) -> dict[str, object]:
        match_id = match["match_id"]
        bets = [row for row in self.store.read_rows("score_bets.csv") if row.get("match_id") == match_id and row.get("status") == "ACTIVE"]
        total_tickets = sum(self._to_int(row.get("ticket_count")) for row in bets)
        score_pool = SCORE_PRICE * total_tickets
        final_bonus = self._current_jackpot() if match_id == "WC2026-FINAL" else Decimal("0")
        pool = score_pool + final_bonus
        winners = [
            row for row in bets
            if self._to_int(row.get("predicted_home_score")) == home_score and self._to_int(row.get("predicted_away_score")) == away_score
        ]
        winner_ticket_count = sum(self._to_int(row.get("ticket_count")) for row in winners)
        settlement_id = f"S-SCORE-{match_id}"
        payouts: dict[str, Decimal] = {}
        payout_per_ticket = Decimal("0")
        carryover = Decimal("0")
        notes = ""

        if winner_ticket_count > 0:
            payout_per_ticket = self._money(pool / Decimal(winner_ticket_count))
            for row in winners:
                tickets = self._to_int(row.get("ticket_count"))
                amount = self._money(payout_per_ticket * tickets)
                payouts[row["member_id"]] = payouts.get(row["member_id"], Decimal("0")) + amount
        else:
            carryover = score_pool
            notes = "Score pool moved to jackpot"
            if carryover > 0:
                self._append_jackpot_entry(match_id, carryover, settlement_id, admin_id, created_at)

        if final_bonus > 0 and payouts:
            self._append_jackpot_entry(match_id, -final_bonus, settlement_id, admin_id, created_at, reason="Final payout consumed jackpot")

        self._apply_payouts(payouts, members, created_at, match_id, "SCORE", settlement_id, admin_id)
        self._replace_score_bets(match_id, settlement_id, payouts, carryover)
        self.store.append_row(
            "match_settlements.csv",
            {
                "settlement_id": settlement_id,
                "settled_at": created_at,
                "match_id": match_id,
                "market": "SCORE",
                "result_key": f"{home_score}-{away_score}",
                "total_staked_points": self._fmt_points(pool),
                "winning_staked_points": self._fmt_points(SCORE_PRICE * winner_ticket_count),
                "losing_staked_points": self._fmt_points(pool - (SCORE_PRICE * winner_ticket_count)),
                "winner_ticket_count": str(winner_ticket_count),
                "payout_per_ticket": self._fmt_points(payout_per_ticket),
                "carryover_points": self._fmt_points(carryover),
                "admin_id": admin_id,
                "status": "SETTLED",
                "notes": notes,
            },
        )
        self.store.append_row(
            "admin_actions.csv",
            {
                "action_id": self._next_id("admin_actions.csv", "action_id", f"A-SETTLE-SCORE-{match_id}"),
                "created_at": created_at,
                "admin_id": admin_id,
                "action_type": "SETTLE_SCORE",
                "target_type": "match",
                "target_id": match_id,
                "points_delta": self._fmt_points(sum(payouts.values(), Decimal("0"))),
                "reason": settlement_id,
            },
        )
        return {
            "settlement_id": settlement_id,
            "winner_member_ids": sorted(payouts.keys()),
            "payouts": payouts,
            "winner_ticket_count": winner_ticket_count,
            "carryover": carryover,
        }

    def _build_announcement(
        self,
        match: dict[str, str],
        home_score: int,
        away_score: int,
        wdl: dict[str, object],
        score: dict[str, object],
        members: dict[str, dict[str, str]],
    ) -> str:
        match_id = match["match_id"]
        result_line = f"Kết quả {match_id}: {match.get('home_team', '')} {home_score}-{away_score} {match.get('away_team', '')}. Đã settle."
        wdl_mentions = self._member_mentions(wdl["winner_member_ids"], members)
        score_mentions = self._member_mentions(score["winner_member_ids"], members)
        parts = [result_line]
        if wdl_mentions:
            parts.append(f"Thắng kèo WDL: {', '.join(wdl_mentions)}.")
        elif wdl.get("carryover", Decimal("0")) and Decimal(wdl["carryover"]) > 0:
            parts.append("Kèo WDL nghiêng 1 phía. Pool chuyển jackpot.")
        else:
            parts.append("Kèo WDL: chưa có người thắng.")
        if score_mentions:
            parts.append(f"Thắng kèo tỷ số: {', '.join(score_mentions)}. Point đã cộng vào tài khoản.")
        elif score.get("carryover", Decimal("0")) and Decimal(score["carryover"]) > 0:
            parts.append("Kèo tỷ số chưa có người thắng. Pool chuyển jackpot.")
        else:
            parts.append("Kèo tỷ số: chưa có người thắng.")
        return " ".join(parts)

    def _member_mentions(self, member_ids: Iterable[str], members: dict[str, dict[str, str]]) -> list[str]:
        mention_map = self._load_google_chat_mentions()
        mentions: list[str] = []
        for member_id in member_ids:
            member = members.get(member_id, {})
            user_name = member.get("google_chat_user_name", "")
            mention = mention_map.get(user_name)
            if not mention and user_name.startswith("users/"):
                mention = f"<{user_name}>"
            if not mention:
                display_name = member.get("display_name") or member_id
                mention = display_name
            mentions.append(mention)
        return mentions

    def _load_google_chat_mentions(self) -> dict[str, str]:
        path = self.workspace_root / "googlechat_members.json"
        if not path.exists():
            return {}
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        mentions: dict[str, str] = {}
        for row in data.get("members", []):
            user_name = row.get("userName", "")
            mention = row.get("mention", "")
            if user_name and mention:
                mentions[user_name] = mention
        return mentions

    def _apply_payouts(
        self,
        payouts: dict[str, Decimal],
        members: dict[str, dict[str, str]],
        created_at: str,
        match_id: str,
        market: str,
        settlement_id: str,
        admin_id: str,
    ) -> None:
        for member_id, delta in payouts.items():
            member = members.get(member_id) or self._get_member(member_id)
            balance_after = self._member_balance(member) + delta
            self._append_ledger_entry(
                ledger_id=self._next_ledger_id(),
                created_at=created_at,
                member_id=member_id,
                change_type="PAYOUT",
                points_delta=delta,
                balance_before=self._member_balance(member),
                balance_after=balance_after,
                related_match_id=match_id,
                related_market=market,
                related_bet_id=settlement_id,
                admin_id=admin_id,
                reason=settlement_id,
                actor_member_id=admin_id,
                match=self._get_match(match_id),
                settlement_id=settlement_id,
            )
            self._update_member_balance(member_id, balance_after)
            members[member_id] = self._get_member(member_id)

    def _append_ledger_entry(
        self,
        *,
        ledger_id: str,
        created_at: str,
        member_id: str,
        change_type: str,
        points_delta: Decimal,
        balance_before: Decimal,
        balance_after: Decimal,
        related_match_id: str = "",
        related_market: str = "",
        related_bet_id: str = "",
        admin_id: str = "",
        reason: str = "",
        actor_member_id: str = "",
        counterparty_member_id: str = "",
        match: dict[str, str] | None = None,
        ticket_count: int | None = None,
        unit_points: Decimal | None = None,
        pick: str = "",
        predicted_home_score: int | None = None,
        predicted_away_score: int | None = None,
        settlement_id: str = "",
    ) -> None:
        self.store.append_row(
            "point_ledger.csv",
            {
                "ledger_id": ledger_id,
                "created_at": created_at,
                "member_id": member_id,
                "change_type": change_type,
                "points_delta": self._fmt_points(points_delta),
                "balance_before": self._fmt_points(balance_before),
                "balance_after": self._fmt_points(balance_after),
                "related_match_id": related_match_id,
                "related_market": related_market,
                "related_bet_id": related_bet_id,
                "admin_id": admin_id,
                "reason": reason,
                "actor_member_id": actor_member_id,
                "counterparty_member_id": counterparty_member_id,
                "match_home_team": (match or {}).get("home_team", ""),
                "match_away_team": (match or {}).get("away_team", ""),
                "ticket_count": str(ticket_count or ""),
                "unit_points": self._fmt_points(unit_points) if unit_points is not None else "",
                "pick": pick,
                "predicted_score": (
                    f"{predicted_home_score}-{predicted_away_score}"
                    if predicted_home_score is not None and predicted_away_score is not None else ""
                ),
                "settlement_id": settlement_id,
            },
        )

    def _replace_wdl_bets(self, match_id: str, settlement_id: str, payouts: dict[str, Decimal]) -> None:
        rows = self.store.read_rows("win_draw_loss_bets.csv")
        for row in rows:
            if row.get("match_id") != match_id or row.get("status") != "ACTIVE":
                continue
            member_id = row.get("member_id", "")
            row["settlement_id"] = settlement_id
            row["status"] = "SETTLED"
            row["payout_points"] = self._fmt_points(payouts.get(member_id, Decimal("0")))
            row["net_points"] = self._fmt_points(payouts.get(member_id, Decimal("0")) - Decimal(row.get("points_staked") or "0"))
        self.store.replace_rows("win_draw_loss_bets.csv", rows)

    def _replace_score_bets(self, match_id: str, settlement_id: str, payouts: dict[str, Decimal], carryover: Decimal) -> None:
        rows = self.store.read_rows("score_bets.csv")
        for row in rows:
            if row.get("match_id") != match_id or row.get("status") != "ACTIVE":
                continue
            member_id = row.get("member_id", "")
            row["settlement_id"] = settlement_id
            row["status"] = "SETTLED"
            row["payout_points"] = self._fmt_points(payouts.get(member_id, Decimal("0")))
            row["net_points"] = self._fmt_points(payouts.get(member_id, Decimal("0")) - Decimal(row.get("points_staked") or "0"))
            row["carryover_points"] = self._fmt_points(carryover)
        self.store.replace_rows("score_bets.csv", rows)

    def _append_jackpot_entry(
        self,
        match_id: str,
        delta: Decimal,
        settlement_id: str,
        admin_id: str,
        created_at: str,
        reason: str | None = None,
    ) -> None:
        balance_after = self._current_jackpot() + delta
        self.store.append_row(
            "final_jackpot.csv",
            {
                "entry_id": self._next_id("final_jackpot.csv", "entry_id", "JP"),
                "created_at": created_at,
                "source_match_id": match_id,
                "points_delta": self._fmt_points(delta),
                "balance_after": self._fmt_points(balance_after),
                "reason": reason or "Carryover from score market",
                "settlement_id": settlement_id,
                "admin_id": admin_id,
            },
        )

    def _current_jackpot(self) -> Decimal:
        rows = self.store.read_rows("final_jackpot.csv")
        if not rows:
            return Decimal("0")
        last = rows[-1].get("balance_after", "")
        if last:
            return Decimal(last)
        return sum((Decimal(row.get("points_delta") or "0") for row in rows), Decimal("0"))

    def _mark_match_settled(self, match_id: str, admin_id: str, created_at: str) -> None:
        rows = self.store.read_rows("matches.csv")
        updated = False
        for row in rows:
            if row.get("match_id") == match_id:
                row["settled_at"] = created_at
                row["admin_id"] = admin_id
                row["status"] = "SETTLED"
                updated = True
        if not updated:
            raise BettingError(f"Không tìm thấy trận {match_id} để cập nhật settle.")
        self.store.replace_rows("matches.csv", rows)

    def _mark_settlement_announced(self, match_id: str, created_at: str) -> None:
        rows = self.store.read_rows("match_settlements.csv")
        for row in rows:
            if row.get("match_id") == match_id and row.get("status") == "SETTLED":
                row["status"] = "ANNOUNCED"
                note = row.get("notes", "")
                extra = f"announced_at={created_at}"
                row["notes"] = f"{note}; {extra}".strip("; ") if note else extra
        self.store.replace_rows("match_settlements.csv", rows)

    def _get_member(self, member_id: str) -> dict[str, str]:
        for row in self.store.read_rows("members.csv"):
            if row.get("member_id") == member_id:
                return row
        raise BettingError(f"Không tìm thấy member {member_id}.")

    def _get_match(self, match_id: str) -> dict[str, str]:
        for row in self.store.read_rows("matches.csv"):
            if row.get("match_id") == match_id:
                return row
        raise BettingError(f"Không tìm thấy trận {match_id}.")

    def _get_match_sheet_link(self, match_id: str) -> dict[str, str] | None:
        file_name = "match_sheet_links.csv"
        if not self.store.exists(file_name):
            return None
        for row in self.store.read_rows(file_name):
            if row.get("match_id") == match_id:
                return row
        return None

    def _ensure_match_open(self, match: dict[str, str]) -> None:
        if (match.get("status") or "").upper() not in {"", "SCHEDULED"}:
            raise BettingError(f"Không ghi cược. Trận {match.get('match_id', '')} không ở trạng thái mở.")
        if match.get("locked_at"):
            raise BettingError(f"Không ghi cược. Trận {match.get('match_id', '')} đã khóa lúc {match['locked_at']}.")

    def _parse_match_score(self, match: dict[str, str]) -> tuple[int, int]:
        if match.get("home_score", "") == "" or match.get("away_score", "") == "":
            raise BettingError(f"Trận {match.get('match_id', '')} chưa có kết quả để settle.")
        return self._to_int(match.get("home_score")), self._to_int(match.get("away_score"))

    def _member_balance(self, member: dict[str, str]) -> Decimal:
        value = member.get("current_balance", "") or "0"
        return Decimal(value)

    def _update_member_balance(self, member_id: str, balance: Decimal) -> None:
        rows = self.store.read_rows("members.csv")
        updated = False
        for row in rows:
            if row.get("member_id") == member_id:
                row["current_balance"] = self._fmt_points(balance)
                row["updated_at"] = self._now_iso()
                updated = True
        if not updated:
            raise BettingError(f"Không tìm thấy member {member_id} để cập nhật số dư.")
        self.store.replace_rows("members.csv", rows)

    def _normalize_pick(self, pick: str, match: dict[str, str]) -> str:
        lowered = self._normalize_text(pick)
        if lowered in DRAW_ALIASES:
            raise BettingError("Không được đặt Hòa. Chỉ đặt đội thắng: đội chủ nhà hoặc đội khách.")
        if lowered in HOME_ALIASES or lowered == self._normalize_text(match.get("home_team", "")):
            return "HOME"
        if lowered in AWAY_ALIASES or lowered == self._normalize_text(match.get("away_team", "")):
            return "AWAY"
        raise BettingError(f"Pick không hợp lệ: {pick}.")

    def _next_id(self, file_name: str, field_name: str, prefix: str) -> str:
        rows = self.store.read_rows(file_name)
        count = sum(1 for row in rows if (row.get(field_name) or "").startswith(prefix)) + 1
        return f"{prefix}-{count:03d}"

    def _next_ledger_id(self) -> str:
        rows = self.store.read_rows("point_ledger.csv")
        return f"L-{datetime.now(VN_TZ).strftime('%Y%m%d%H%M%S')}-{len(rows)+1:04d}"

    def _run_post_action_checks(
        self,
        match_id: str | None = None,
        touched_member_ids: list[str] | None = None,
    ) -> None:
        self._sync_public_workbook_if_enabled()
        self._audit_if_enabled(match_id=match_id, touched_member_ids=touched_member_ids or [])

    def _audit_if_enabled(
        self,
        match_id: str | None = None,
        touched_member_ids: list[str] | None = None,
    ) -> None:
        if os.environ.get("SMILE_BET_AUDIT_AFTER_ACTION", "true").strip().lower() in {"0", "false", "no"}:
            return
        service_account = (
            os.environ.get("SMILE_BET_GOOGLE_SERVICE_ACCOUNT", "").strip()
            or os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", "").strip()
        )
        if not service_account:
            return
        script_path = self.workspace_root / "scripts" / "audit_openclaw_state.py"
        if not script_path.exists():
            return
        command = [sys.executable, str(script_path), "--service-account", service_account]
        if match_id:
            command.extend(["--match-id", match_id])
        for member_id in touched_member_ids or []:
            command.extend(["--member-id", member_id])
        subprocess.run(
            command,
            check=True,
            cwd=self.workspace_root,
            env=os.environ.copy(),
        )

    def _sync_public_workbook_if_enabled(self) -> None:
        if not self._uses_google_sheets_runtime():
            return
        if os.environ.get("SMILE_BET_SYNC_PUBLIC_WORKBOOK", "true").strip().lower() in {"0", "false", "no"}:
            return
        service_account = (
            os.environ.get("SMILE_BET_GOOGLE_SERVICE_ACCOUNT", "").strip()
            or os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", "").strip()
        )
        if not service_account:
            return
        public_workbook_id = os.environ.get(
            "SMILE_BET_PUBLIC_WORKBOOK_ID",
            "1wAT0jpXw3_920kHYfemqFMUXWFgzFpv85mc8GNk_lNY",
        ).strip()
        if not public_workbook_id:
            return
        script_path = self.workspace_root / "scripts" / "sync_public_match_workbook.py"
        if not script_path.exists():
            return
        subprocess.run(
            [
                sys.executable,
                str(script_path),
                "--service-account",
                service_account,
                "--public-workbook-id",
                public_workbook_id,
            ],
            check=True,
            cwd=self.workspace_root,
            env=os.environ.copy(),
        )

    def _uses_google_sheets_runtime(self) -> bool:
        return self.store.__class__.__name__ == "GoogleSheetsStore"

    @staticmethod
    def _fmt_points(value: Decimal) -> str:
        quantized = value.quantize(Decimal("0.01"))
        if quantized == quantized.to_integral():
            return str(int(quantized))
        return format(quantized.normalize(), "f")

    @staticmethod
    def _normalize_text(value: str) -> str:
        value = value.casefold().strip()
        value = re.sub(r"\s+", " ", value)
        return value

    @staticmethod
    def _now_iso() -> str:
        return datetime.now(VN_TZ).replace(microsecond=0).isoformat()

    @staticmethod
    def _to_int(value: object) -> int:
        if value in (None, ""):
            return 0
        return int(str(value))

    @staticmethod
    def _match_result(home_score: int, away_score: int) -> str:
        if home_score > away_score:
            return "HOME"
        if home_score < away_score:
            return "AWAY"
        return "DRAW"

    @staticmethod
    def _money(value: Decimal) -> Decimal:
        return value.quantize(Decimal("0.01"), rounding=ROUND_DOWN)
