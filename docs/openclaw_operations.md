# SmileAI Operations Plan

## Goal

Member only sends natural-language request to SmileAI. SmileAI validates role, reads Google Sheets, writes only allowed rows/fields, and replies with concise result.

## Runtime Rule

- OpenClaw runtime must use Google Sheets as single source of truth.
- Do not read from or write to local CSV during live operation.
- Local CSV allowed only for seed, test, export, backup, or migration scripts outside live command path.
- Public workbook `1wAT0jpXw3_920kHYfemqFMUXWFgzFpv85mc8GNk_lNY` is source of truth for match-facing public views only: match info, active bets, pool totals, final result, winners, payout-by-match.
- Member balances, point ledger, admin actions, and other internal operational data stay in internal sheets, not in public workbook.

## Sheet Permissions

- Admin: editor on workbook.
- Google Workspace manager or Google Chat space manager: treated as Smile Bet manager/admin.
- SmileAI OAuth identity: editor on workbook.
- Members: viewer only.
- Protect formula/rule columns where possible. Editable zones should be limited to admin/SmileAI writes.

## Google Workspace OAuth

- When any user asks to `cap quyen OAuth`, `cấp quyền OAuth`, `grant OAuth`, or authorize SmileAI/OpenClaw, SmileAI/OpenClaw should request the full Google Workspace OAuth bundle below, not a narrowed Sheets-only grant.
- Full OAuth bundle for SmileAI/OpenClaw:
  - `https://www.googleapis.com/auth/calendar`
  - `https://www.googleapis.com/auth/meetings.space.created`
  - `https://www.googleapis.com/auth/meetings.space.readonly`
  - `https://www.googleapis.com/auth/meetings.space.settings`
  - `https://www.googleapis.com/auth/documents`
  - `https://www.googleapis.com/auth/spreadsheets`
  - `https://www.googleapis.com/auth/drive`
- OAuth consent must be completed by the Google account/workspace admin that owns the grant. Do not expose OAuth client secrets, access tokens, refresh tokens, or service account JSON.

## Command Flow

1. Parse intent from user text.
2. Identify Google Chat actor and resolve subject member. If no subject is named, use the sender as subject. Workspace/space manager counts as admin.
3. Load required sheets by stable IDs.
4. Validate role, inputs, kickoff lock, status, and balance.
5. Write append-only rows first: bets, ledger, admin actions.
6. Update cache fields second: member balance, match status, settlement ids.
7. Sync public match workbook after every bet and every settlement.
8. Re-read affected rows and verify invariants.
9. Reply with action result and balance/payout summary.

## Required Invariants

- No positive point change unless admin intent created it or settlement payout produced it. Single-sided WDL pool is exception path: no payout, whole WDL pool moves to jackpot.
- Every balance change has `point_ledger.csv` row.
- Any future manual point change must go through append-only `point_ledger.csv` plus matching `admin_actions.csv`; never edit `members.current_balance` directly.
- `members.current_balance` equals sum of ledger deltas for member.
- No bet can be accepted at or after kickoff/locked time.
- Settlement is idempotent: one settlement per `match_id + market`.
- Exact-score carryover is append-only in `final_jackpot.csv`. Single-sided WDL carryover also appends there.
- Admin-entered results are never overwritten by fixture refresh.
- Every public match tab must show, at minimum: match info, total WDL pool, total score pool, active WDL bets, active score bets, and settlement payout summary once available. Bet tables should keep `selection` separate from `status`, `payout_points`, and `net_points`; do not pack result text into one cell.
- For exact-score settlement, payout and net result must be attached to the exact winning bet row only. Other score rows for the same member must remain visible but show zero payout and negative net stake as applicable.

## Fixture And Team Refresh

Preferred free source: ESPN public scoreboard.

```text
GET https://site.api.espn.com/apis/site/v2/sports/soccer/fifa.world/scoreboard?dates=20260611-20260719
```

Result sync command:

```text
python3 scripts/sync_fixture_results.py
python3 scripts/sync_fixture_results.py --apply
```

Rules for result sync:

```text
- dry-run by default
- may update only match status, source_match_id, home_score, away_score, result, notes sync stamp
- must not overwrite rows with settled_at
- must not overwrite admin-entered scores unless explicit allow-overwrite flag is passed
- should match fixture by numeric source_match_id first, then notes.fixture_id, then home/away/day fallback
```

Fallback/manual source: FIFA public match centre, OpenFootball seed, and API-Football if paid key exists.

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


## Audit after every mutation

- Moi action ghi du lieu phai chay 2 buoc hau kiem: sync workbook public, roi audit.
- Script audit chuan: `python3 scripts/audit_openclaw_state.py --match-id <MATCH_ID> --member-id <MEMBER_ID>`
- Audit phai check toi thieu: row vua ghi ton tai, balance khop ledger, public tab khop pool va bet rows, split columns `status/payout_points/net_points` dung theo tung row, score payout dung tung row, timestamp van hanh dung gio Viet Nam.
- Neu audit fail, phai coi action la loi van hanh va bao chi tiet sheet/rule lech.

## Promo Automation Trigger

OpenClaw should support automatic promo-trigger preparation for hype/report workflows.

### Promo queue workbook

Use dedicated Google Sheets workbook for promo queue and approval flow:
- workbook id: `1qeOZZU6WafIR3WZysMIiC1cbtoudKq2-I-Lg28svAJ8`
- default tab: `promo_jobs`
- recommended env: `SMILE_BET_PROMO_WORKBOOK_ID=1qeOZZU6WafIR3WZysMIiC1cbtoudKq2-I-Lg28svAJ8`

### Nightly roundup schedule

Primary roundup trigger should run at `16:00 Asia/Ho_Chi_Minh` each work day.
It prepares one new thread/post for matches from late night to next morning, with default match window:
- `next day 00:00` to `next day 09:00` Vietnam time
- practical focus remains the overnight block users care about, usually `02:00-09:00`


### Trigger goals

- pre-match teaser for important fixtures
- newspaper/report package for selected headline matches
- post-settlement recap after official settle

### Recommended trigger points

1. Fixture-based pre-match trigger
- run on schedule in Vietnam time
- candidate windows:
  - `T-24h`: long preview or newspaper/report package
  - `T-3h`: short reminder post
  - `T-30m`: final call-to-action post

2. Data-change trigger
- after `settle_match` succeeds and audit passes
- prepare recap payload for that `match_id`

3. Manual admin trigger
- command example: `admin: tạo bài promo trận WC2026-0001`
- command example: `admin: tạo bài report trận WC2026-0001`

### Trigger guardrails

- Only trigger after fixture identity is stable.
- Use Vietnam time only in generated payloads and user-facing text.
- Do not use generated images. Promo payload must ask for real web banner selection only.
- For report/newspaper trigger, preferred banner must clearly frame both teams.
- Never mark promo task complete if image package is missing.

### Minimal automation design

1. Use workbook `SMILE_BET_PROMO_WORKBOOK_ID` and tab `promo_jobs` as queue.
2. Scheduled OpenClaw worker scans `matches` at `16:00 Asia/Ho_Chi_Minh` and enqueues one `night_roundup` job for the next overnight window.
3. Optional secondary worker can still enqueue single-match jobs such as `preview_report` or `recap`.
4. Worker skips jobs already completed for same `promo_type + scheduled_date + scheduled_window`.
5. Job payload includes:
   - `scheduled_date`
   - `promo_type` such as `night_roundup`, `preview_short`, `preview_report`, `recap`
   - `window_start_local`, `window_end_local` in `Asia/Ho_Chi_Minh`
   - `match_ids`
   - optional spotlight fields for featured matches
   - `priority`
6. Promo generation step uses `betting-hype-writer` skill rules.
7. Publish/send only after human approval, unless later policy explicitly allows auto-post.

### Suggested first implementation

- Phase 1: create `promo_jobs` records in workbook queue only, no auto-send.
- Phase 2: admin command lists pending promo jobs and asks OpenClaw to draft content.
- Phase 3: optional Google Chat push after approval flow is defined.

### Suggested `promo_jobs` columns

- `job_id`
- `scheduled_date`
- `promo_type`
- `window_start_local`
- `window_end_local`
- `match_ids`
- `featured_match_ids`
- `status`
- `thread_key`
- `draft_text`
- `image_package`
- `posted_at`
- `note`
