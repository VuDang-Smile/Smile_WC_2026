# WC 2026 Betting Sheet Design

## API Source

Use API-Football (`https://v3.football.api-sports.io`) for official paid/API refresh when available. Suggested endpoint:

```text
GET /fixtures?league=1&season=2026
```

Keep API data as seed only. Admin remains source of truth for results and settlements.

Current checked-in seed uses public OpenFootball data:

```text
https://raw.githubusercontent.com/openfootball/worldcup.json/master/2026/worldcup.json
```

Refresh command:

```bash
python3 scripts/import_openfootball_wc2026.py
```

## Files

Time rule: user-facing time and stored operation timestamps should use Vietnam time (`Asia/Ho_Chi_Minh`, GMT+7). Fixture rows may retain source time in `kickoff_at_utc`, but runtime display should prefer `kickoff_at_local`.

- `members.csv`: member profile and balance cache.
- `point_ledger.csv`: append-only point ledger. Every topup, bet stake, refund, payout, correction must create row.
- `matches.csv`: 104-match fixture list, lock time, scores, result.
- `win_draw_loss_bets.csv`: 20 point tickets for home/draw/away.
- `score_bets.csv`: 10 point exact-score tickets.
- `match_settlements.csv`: computed settlement records.
- `final_jackpot.csv`: carryover pool for exact-score market.
- `admin_actions.csv`: privileged action audit.
- `teams.csv`: 48 team info rows imported from OpenFootball public WC 2026 data.
- `smileai_commands.csv`: supported natural-language intents and validations.
- `test_cases.csv`: functional and edge cases for verification.

## Roles

- Admin can increase points, edit match results, settle matches, fix records with ledger correction.
- SmileAI can append bets and ledger rows, then update balance cache.
- Members can view sheets only.

## Point Rules

### Initial Topup

Member joins with 200 points. Only admin may create positive point topup.

Ledger row:

```text
change_type=TOPUP
points_delta=200
reason=Initial WC 2026 pool
```

### Win / Draw / Loss Market

- Ticket price: 20 points.
- Choices: `HOME`, `AWAY`. Members cannot place `DRAW` tickets.
- Bets lock at kickoff time.
- Stake immediately subtracts points from member balance.
- Settlement pays winning side from losing side pool.

Payout formulas:

```text
total_staked = sum(all tickets * 20)
winning_staked = sum(winning tickets * 20)
losing_staked = total_staked - winning_staked
payout_per_ticket = losing_staked / winner_ticket_count
payout_points_per_ticket = 20 + payout_per_ticket
net_points_per_ticket = payout_per_ticket
```

Draw handling: if result is draw, split all staked points equally across `HOME` and `AWAY` pools by side ticket count. To match your example:

```text
home_pool_return = total_staked / 2
away_pool_return = total_staked / 2
home_payout_per_ticket = home_pool_return / home_ticket_count
away_payout_per_ticket = away_pool_return / away_ticket_count
```

`DRAW` rows may still settle for legacy data, but new bets must be `HOME` or `AWAY`.

If no ticket matches the result, do not divide by zero. Record the pool as unclaimed in settlement notes for admin decision, or create an explicit refund/carryover rule before launch.

### Exact Score Market

- Ticket price: 10 points.
- Many members can pick same score.
- Bets lock at kickoff time.
- Stake immediately subtracts points from member balance.
- Correct score tickets split full exact-score pool for that match.
- If no correct ticket exists, full pool moves to final jackpot.
- Final match exact-score pool includes jackpot balance.

Formula:

```text
pool = sum(score ticket stakes for match) + final_jackpot_balance_if_final
payout_per_ticket = pool / winning_ticket_count
```

## IDs

Use stable IDs so SmileAI can edit safely:

```text
member_id: M0001
match_id: WC2026-0001
bet_id: B-WDL-WC2026-0001-M0001-001 or B-SCORE-WC2026-0001-M0001-001
ledger_id: L-YYYYMMDDHHMMSS-0001
settlement_id: S-WDL-WC2026-0001 or S-SCORE-WC2026-0001
```

## World Cup 2026 Teams

World Cup 2026 has 48 teams. `teams.csv` is populated from OpenFootball public data and includes group assignment, confederation, FIFA-style code, source provider, and qualification status. Refresh from API-Football/FIFA if official data differs. Keep `team_id` stable where possible, and store provider IDs in `api_team_id` for future fixture joins.

## Google Drive Target

Folder ID:

```text
1wUwJNck0WAuR110Jk3tTzjSSHVzGfAO9
```

Create one Google Sheet workbook named `Smile Bet - WC 2026` with each CSV as a tab, or upload CSV files directly. Workbook is better for formulas and sharing.
