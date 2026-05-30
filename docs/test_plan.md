# WC 2026 Betting Test Plan

## Scope

Test betting rules, permission boundaries, balance ledger integrity, settlement idempotency, exact-score jackpot, fixture/team refresh, and Google Sheets operational safety.

## Functional Areas

- Member registration and admin topup.
- Win/draw/loss bet creation and settlement.
- Exact-score bet creation and settlement.
- Match lock and result entry.
- Final jackpot carryover.
- Ledger and balance reconciliation.
- SmileAI natural-language intents.
- API refresh merge behavior.

## Edge Cases

- Bet exactly at kickoff must be rejected.
- Match with no bets should settle without crash.
- Market with no winners should not divide by zero.
- Repeated settlement must not pay twice.
- Payout with fractional division must use deterministic rounding policy.
- Cancelled match should refund unsettled stakes.
- Negative scores, unknown IDs, inactive members, and insufficient balance must fail without writes.

## Simulation Evidence

Run:

```bash
python3 scripts/simulate_betting_cases.py
```

Expected: all cases print `PASS` and final summary has zero failures.
