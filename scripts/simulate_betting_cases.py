#!/usr/bin/env python3
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, ROUND_DOWN
import random
from typing import Callable


WDL_PRICE = Decimal("20")
SCORE_PRICE = Decimal("10")


@dataclass
class Member:
    member_id: str
    balance: Decimal = Decimal("0")
    active: bool = True


@dataclass
class Match:
    match_id: str
    kickoff_minute: int
    home_score: int | None = None
    away_score: int | None = None
    settled_markets: set[str] = field(default_factory=set)

    @property
    def result(self) -> str | None:
        if self.home_score is None or self.away_score is None:
            return None
        if self.home_score > self.away_score:
            return "HOME"
        if self.home_score < self.away_score:
            return "AWAY"
        return "DRAW"


@dataclass
class LedgerEntry:
    member_id: str
    delta: Decimal
    change_type: str


@dataclass
class WdlBet:
    member_id: str
    match_id: str
    pick: str
    tickets: int
    status: str = "ACTIVE"


@dataclass
class ScoreBet:
    member_id: str
    match_id: str
    home: int
    away: int
    tickets: int
    status: str = "ACTIVE"


class Game:
    def __init__(self) -> None:
        self.members: dict[str, Member] = {}
        self.matches: dict[str, Match] = {}
        self.ledger: list[LedgerEntry] = []
        self.wdl_bets: list[WdlBet] = []
        self.score_bets: list[ScoreBet] = []
        self.jackpot = Decimal("0")
        self.unclaimed_pool = Decimal("0")

    def add_member(self, member_id: str, admin: bool = True) -> None:
        if not admin:
            raise PermissionError("admin required")
        if member_id in self.members:
            raise ValueError("duplicate member")
        self.members[member_id] = Member(member_id)
        self._change(member_id, Decimal("200"), "TOPUP")

    def admin_topup(self, member_id: str, points: Decimal, admin: bool = True) -> None:
        if not admin:
            raise PermissionError("admin required")
        if points <= 0:
            raise ValueError("points must be positive")
        self._change(member_id, points, "TOPUP")

    def add_match(self, match_id: str, kickoff_minute: int) -> None:
        self.matches[match_id] = Match(match_id, kickoff_minute)

    def place_wdl(self, member_id: str, match_id: str, pick: str, tickets: int, now: int) -> None:
        match = self.matches[match_id]
        if now >= match.kickoff_minute:
            raise ValueError("match locked")
        if pick not in {"HOME", "AWAY"}:
            raise ValueError("bad pick")
        stake = WDL_PRICE * tickets
        self._require_balance(member_id, stake)
        self.wdl_bets.append(WdlBet(member_id, match_id, pick, tickets))
        self._change(member_id, -stake, "BET_STAKE")

    def place_score(self, member_id: str, match_id: str, home: int, away: int, tickets: int, now: int) -> None:
        match = self.matches[match_id]
        if now >= match.kickoff_minute:
            raise ValueError("match locked")
        if home < 0 or away < 0:
            raise ValueError("negative score")
        stake = SCORE_PRICE * tickets
        self._require_balance(member_id, stake)
        self.score_bets.append(ScoreBet(member_id, match_id, home, away, tickets))
        self._change(member_id, -stake, "BET_STAKE")

    def enter_result(self, match_id: str, home: int, away: int, admin: bool = True) -> None:
        if not admin:
            raise PermissionError("admin required")
        if home < 0 or away < 0:
            raise ValueError("negative score")
        match = self.matches[match_id]
        match.home_score = home
        match.away_score = away

    def settle_wdl(self, match_id: str) -> dict[str, Decimal]:
        match = self.matches[match_id]
        if "WDL" in match.settled_markets:
            raise ValueError("already settled")
        if match.result is None:
            raise ValueError("missing result")

        bets = [b for b in self.wdl_bets if b.match_id == match_id and b.status == "ACTIVE"]
        total_tickets = sum(b.tickets for b in bets)
        if total_tickets == 0:
            match.settled_markets.add("WDL")
            return {}

        payouts: dict[str, Decimal] = {}
        home_tickets = sum(b.tickets for b in bets if b.pick == "HOME")
        away_tickets = sum(b.tickets for b in bets if b.pick == "AWAY")
        if home_tickets == 0 or away_tickets == 0:
            self.jackpot += WDL_PRICE * total_tickets
            match.settled_markets.add("WDL")
            return {}
        if match.result == "DRAW" and not any(b.pick == "DRAW" for b in bets):
            total_pool = WDL_PRICE * total_tickets
            for side in ("HOME", "AWAY"):
                side_bets = [b for b in bets if b.pick == side]
                side_tickets = sum(b.tickets for b in side_bets)
                if side_tickets == 0:
                    continue
                per_ticket = (total_pool / Decimal("2")) / side_tickets
                for bet in side_bets:
                    amount = per_ticket * bet.tickets
                    payouts[bet.member_id] = payouts.get(bet.member_id, Decimal("0")) + amount
        else:
            winners = [b for b in bets if b.pick == match.result]
            winner_tickets = sum(b.tickets for b in winners)
            if winner_tickets == 0:
                self.unclaimed_pool += WDL_PRICE * total_tickets
                match.settled_markets.add("WDL")
                return {}
            losing_tickets = total_tickets - winner_tickets
            profit_per_ticket = (WDL_PRICE * losing_tickets) / winner_tickets
            payout_per_ticket = WDL_PRICE + profit_per_ticket
            for bet in winners:
                amount = payout_per_ticket * bet.tickets
                payouts[bet.member_id] = payouts.get(bet.member_id, Decimal("0")) + amount

        for member_id, amount in payouts.items():
            self._change(member_id, self._money(amount), "PAYOUT")
        match.settled_markets.add("WDL")
        return payouts

    def settle_score(self, match_id: str, final: bool = False) -> dict[str, Decimal]:
        match = self.matches[match_id]
        if "SCORE" in match.settled_markets:
            raise ValueError("already settled")
        if match.home_score is None or match.away_score is None:
            raise ValueError("missing result")

        bets = [b for b in self.score_bets if b.match_id == match_id and b.status == "ACTIVE"]
        total_tickets = sum(b.tickets for b in bets)
        pool = SCORE_PRICE * total_tickets + (self.jackpot if final else Decimal("0"))
        winners = [b for b in bets if b.home == match.home_score and b.away == match.away_score]
        winner_tickets = sum(b.tickets for b in winners)
        if winner_tickets == 0:
            self.jackpot += SCORE_PRICE * total_tickets
            match.settled_markets.add("SCORE")
            return {}

        payout_per_ticket = pool / winner_tickets
        payouts: dict[str, Decimal] = {}
        for bet in winners:
            amount = payout_per_ticket * bet.tickets
            payouts[bet.member_id] = payouts.get(bet.member_id, Decimal("0")) + amount
        for member_id, amount in payouts.items():
            self._change(member_id, self._money(amount), "PAYOUT")
        if final:
            self.jackpot = Decimal("0")
        match.settled_markets.add("SCORE")
        return payouts

    def reconcile(self) -> bool:
        sums: dict[str, Decimal] = {m: Decimal("0") for m in self.members}
        for entry in self.ledger:
            sums[entry.member_id] = sums.get(entry.member_id, Decimal("0")) + entry.delta
        return all(self.members[m].balance == total for m, total in sums.items())

    def system_value(self) -> Decimal:
        balances = sum(member.balance for member in self.members.values())
        active_wdl = sum(
            WDL_PRICE * bet.tickets
            for bet in self.wdl_bets
            if "WDL" not in self.matches[bet.match_id].settled_markets
        )
        active_score = sum(
            SCORE_PRICE * bet.tickets
            for bet in self.score_bets
            if "SCORE" not in self.matches[bet.match_id].settled_markets
        )
        return balances + self.jackpot + self.unclaimed_pool + active_wdl + active_score

    def _change(self, member_id: str, delta: Decimal, change_type: str) -> None:
        member = self.members[member_id]
        member.balance += delta
        self.ledger.append(LedgerEntry(member_id, delta, change_type))

    def _require_balance(self, member_id: str, stake: Decimal) -> None:
        if self.members[member_id].balance < stake:
            raise ValueError("insufficient balance")

    def _money(self, amount: Decimal) -> Decimal:
        return amount.quantize(Decimal("0.01"), rounding=ROUND_DOWN)


def expect_error(fn: Callable[[], object], error_type: type[Exception]) -> None:
    try:
        fn()
    except error_type:
        return
    raise AssertionError(f"expected {error_type.__name__}")


def new_game(member_count: int = 30) -> Game:
    game = Game()
    for i in range(1, member_count + 1):
        game.add_member(f"M{i:04d}")
    game.add_match("WC2026-0001", 100)
    game.add_match("WC2026-FINAL", 1000)
    return game


def test_registration_and_permissions() -> None:
    game = Game()
    game.add_member("M0001")
    assert game.members["M0001"].balance == Decimal("200")
    expect_error(lambda: game.add_member("M0001"), ValueError)
    expect_error(lambda: game.admin_topup("M0001", Decimal("50"), admin=False), PermissionError)
    assert game.members["M0001"].balance == Decimal("200")


def test_lock_and_balance_validation() -> None:
    game = new_game(1)
    game.place_wdl("M0001", "WC2026-0001", "HOME", 1, now=99)
    assert game.members["M0001"].balance == Decimal("180")
    expect_error(lambda: game.place_wdl("M0001", "WC2026-0001", "HOME", 1, now=100), ValueError)
    expect_error(lambda: game.place_wdl("M0001", "WC2026-0001", "HOME", 999, now=99), ValueError)
    expect_error(lambda: game.place_score("M0001", "WC2026-0001", -1, 0, 1, now=99), ValueError)


def test_wdl_user_examples() -> None:
    game = new_game(15)
    for i in range(1, 11):
        game.place_wdl(f"M{i:04d}", "WC2026-0001", "HOME", 1, now=1)
    for i in range(11, 16):
        game.place_wdl(f"M{i:04d}", "WC2026-0001", "AWAY", 1, now=1)
    game.enter_result("WC2026-0001", 1, 0)
    payouts = game.settle_wdl("WC2026-0001")
    assert payouts["M0001"] == Decimal("30.00")
    assert game.members["M0001"].balance == Decimal("210.00")

    game = new_game(15)
    for i in range(1, 11):
        game.place_wdl(f"M{i:04d}", "WC2026-0001", "HOME", 1, now=1)
    for i in range(11, 16):
        game.place_wdl(f"M{i:04d}", "WC2026-0001", "AWAY", 1, now=1)
    game.enter_result("WC2026-0001", 0, 1)
    payouts = game.settle_wdl("WC2026-0001")
    assert payouts["M0011"] == Decimal("60.00")
    assert game.members["M0011"].balance == Decimal("240.00")

    game = new_game(15)
    for i in range(1, 11):
        game.place_wdl(f"M{i:04d}", "WC2026-0001", "HOME", 1, now=1)
    for i in range(11, 16):
        game.place_wdl(f"M{i:04d}", "WC2026-0001", "AWAY", 1, now=1)
    game.enter_result("WC2026-0001", 1, 1)
    payouts = game.settle_wdl("WC2026-0001")
    assert payouts["M0001"] == Decimal("15.00")
    assert payouts["M0011"] == Decimal("30.00")


def test_draw_bet_rejected_and_no_winner() -> None:
    game = new_game(3)
    try:
        game.place_wdl("M0002", "WC2026-0001", "DRAW", 1, now=1)
        raise AssertionError("DRAW bet should be rejected")
    except ValueError as exc:
        assert str(exc) == "bad pick"

    game = new_game(1)
    game.place_wdl("M0001", "WC2026-0001", "HOME", 1, now=1)
    game.enter_result("WC2026-0001", 0, 1)
    assert game.settle_wdl("WC2026-0001") == {}


def test_score_examples_and_jackpot() -> None:
    game = new_game(25)
    for i in range(1, 6):
        game.place_score(f"M{i:04d}", "WC2026-0001", 2, 1, 1, now=1)
    for i in range(6, 26):
        game.place_score(f"M{i:04d}", "WC2026-0001", 1, 0, 1, now=1)
    game.enter_result("WC2026-0001", 2, 1)
    payouts = game.settle_score("WC2026-0001")
    assert payouts["M0001"] == Decimal("50.00")

    game = new_game(2)
    game.place_score("M0001", "WC2026-0001", 1, 0, 1, now=1)
    game.place_score("M0002", "WC2026-0001", 0, 1, 1, now=1)
    game.enter_result("WC2026-0001", 2, 2)
    assert game.settle_score("WC2026-0001") == {}
    assert game.jackpot == Decimal("20")
    game.place_score("M0001", "WC2026-FINAL", 3, 2, 1, now=1)
    game.enter_result("WC2026-FINAL", 3, 2)
    payouts = game.settle_score("WC2026-FINAL", final=True)
    assert payouts["M0001"] == Decimal("30.00")
    assert game.jackpot == Decimal("0")



def test_wdl_single_sided_pool_moves_to_jackpot() -> None:
    game = new_game(2)
    game.place_wdl("M0001", "WC2026-0001", "HOME", 2, now=10)
    game.enter_result("WC2026-0001", 1, 0)
    payouts = game.settle_wdl("WC2026-0001")
    assert payouts == {}
    assert game.jackpot == Decimal("40")
    assert game.members["M0001"].balance == Decimal("160")
    assert game.reconcile() is True

def test_idempotency_and_reconcile() -> None:
    game = new_game(2)
    game.place_wdl("M0001", "WC2026-0001", "HOME", 1, now=1)
    game.place_score("M0002", "WC2026-0001", 1, 0, 1, now=1)
    game.enter_result("WC2026-0001", 1, 0)
    game.settle_wdl("WC2026-0001")
    game.settle_score("WC2026-0001")
    expect_error(lambda: game.settle_wdl("WC2026-0001"), ValueError)
    expect_error(lambda: game.settle_score("WC2026-0001"), ValueError)
    assert game.reconcile()


def test_many_randomized_matches() -> None:
    rng = random.Random(20260530)
    game = new_game(80)
    for match_no in range(2, 102):
        match_id = f"WC2026-{match_no:04d}"
        game.add_match(match_id, 1000 + match_no)
        for member_no in range(1, 81):
            member_id = f"M{member_no:04d}"
            if rng.random() < 0.55:
                pick = rng.choice(["HOME", "AWAY"])
                tickets = rng.randint(1, 3)
                try:
                    game.place_wdl(member_id, match_id, pick, tickets, now=match_no)
                except ValueError:
                    pass
            if rng.random() < 0.45:
                home = rng.randint(0, 5)
                away = rng.randint(0, 5)
                tickets = rng.randint(1, 2)
                try:
                    game.place_score(member_id, match_id, home, away, tickets, now=match_no)
                except ValueError:
                    pass
        game.enter_result(match_id, rng.randint(0, 5), rng.randint(0, 5))
        before_total = game.system_value()
        game.settle_wdl(match_id)
        game.settle_score(match_id, final=(match_no == 101))
        after_total = game.system_value()
        assert after_total <= before_total
        assert before_total - after_total < Decimal("1.00")
        assert game.reconcile()


TESTS = [
    test_registration_and_permissions,
    test_lock_and_balance_validation,
    test_wdl_user_examples,
    test_draw_bet_rejected_and_no_winner,
    test_score_examples_and_jackpot,
    test_wdl_single_sided_pool_moves_to_jackpot,
    test_idempotency_and_reconcile,
    test_many_randomized_matches,
]


def main() -> int:
    failures = 0
    for test in TESTS:
        try:
            test()
        except Exception as exc:
            failures += 1
            print(f"FAIL {test.__name__}: {exc}")
        else:
            print(f"PASS {test.__name__}")
    print(f"summary: {len(TESTS) - failures} passed, {failures} failed")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())

