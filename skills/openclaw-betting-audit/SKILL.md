---
name: openclaw-betting-audit
description: Audit Smile Bet internal sheets and public workbook after any mutating action such as bet, settle, transfer, or admin point adjustment
---

# OpenClaw Betting Audit

Use after every mutating action.

## Required checks

1. Internal write checks
- target bet/admin/settlement row exists
- member balance changed as expected
- point ledger has matching append-only row
- if WDL pool is single-sided, jackpot append row exists instead of WDL payout rows

2. Public workbook checks
- target match tab updated
- WDL pool correct
- score pool correct
- active or settled bet rows visible
- public bet rows use split columns: `selection`, `status`, `payout_points`, `net_points`
- if settled, payout shown on exact winning score row only

3. Invariant checks
- `members.current_balance` equals ledger-derived balance for touched members
- settled WDL payout total equals WDL settlement payout total
- settled score payout total equals score settlement payout total
- fixture/result sync must not modify rows with `settled_at`
- fixture/result sync must not overwrite admin-entered scores unless explicit override mode was used

## Execution

Run:

```bash
python3 scripts/audit_openclaw_state.py --match-id <MATCH_ID>
```

For broader review:

```bash
python3 scripts/audit_openclaw_state.py
```

For result-sync review before write:

```bash
python3 scripts/sync_fixture_results_api_football.py
```

## Failure rule

If audit fails, do not treat action as complete. Report mismatch precisely: sheet, row type, expected value, actual value. For public row mismatches, mention split-column field names directly instead of packed result text.


## Post-action pipeline

1. Run live action on Google Sheets only.
2. Re-sync public workbook if action touched match/bet/settlement view.
3. Run audit with touched `match_id` and `member_id`.
4. Only then report success.
