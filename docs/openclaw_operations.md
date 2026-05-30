# SmileAI Operations Plan

## Goal

Member only sends natural-language request to SmileAI. SmileAI validates role, reads Google Sheets, writes only allowed rows/fields, and replies with concise result.

## Sheet Permissions

- Admin: editor on workbook.
- Google Workspace manager or Google Chat space manager: treated as Smile Bet manager/admin.
- SmileAI OAuth identity: editor on workbook.
- Members: viewer only.
- Protect formula/rule columns where possible. Editable zones should be limited to admin/SmileAI writes.

## Command Flow

1. Parse intent from user text.
2. Identify Google Chat actor and resolve subject member. If no subject is named, use the sender as subject. Workspace/space manager counts as admin.
3. Load required sheets by stable IDs.
4. Validate role, inputs, kickoff lock, status, and balance.
5. Write append-only rows first: bets, ledger, admin actions.
6. Update cache fields second: member balance, match status, settlement ids.
7. Re-read affected rows and verify invariants.
8. Reply with action result and balance/payout summary.

## Required Invariants

- No positive point change unless admin intent created it or settlement payout produced it.
- Every balance change has `point_ledger.csv` row.
- `members.current_balance` equals sum of ledger deltas for member.
- No bet can be accepted at or after kickoff/locked time.
- Settlement is idempotent: one settlement per `match_id + market`.
- Exact-score carryover is append-only in `final_jackpot.csv`.
- Admin-entered results are never overwritten by fixture refresh.

## Fixture And Team Refresh

Preferred source: API-Football.

```text
GET https://v3.football.api-sports.io/fixtures?league=1&season=2026
GET https://v3.football.api-sports.io/teams?league=1&season=2026
```

Fallback/manual source: FIFA public match centre and qualified-team list.

Refresh should produce a diff before applying:

```text
new teams, changed names, new fixtures, kickoff changes, cancelled/postponed matches
```

SmileAI should apply only fixture/team metadata. It must not overwrite `home_score`, `away_score`, `result`, `settled_at`, or admin notes.

## User Request Examples

- `M0001 đặt 2 vé đội chủ nhà thắng trận WC2026-0001`
- `M0001 đặt tỷ số 2-1 trận WC2026-0001`
- `@SmileAI đặt Brazil thắng trận WC2026-0001` means the Google Chat sender is the member.
- `@SmileAI đặt tỷ số 2-1 trận WC2026-0001` means the Google Chat sender is the member.
- `xem điểm của tôi`
- `xem tổng cược trận WC2026-0001`
- `admin: nhập kết quả WC2026-0001 2-1`
- `admin: settle trận WC2026-0001`
- `admin: cập nhật lịch World Cup 2026`

## Error Replies

- Insufficient balance: state required points and current balance.
- Locked match: state kickoff/locked time.
- Unknown match/member: ask for valid ID or show closest matches.
- Permission denied: say admin permission required.
- Settlement duplicate: say match already settled and show settlement id.
