# Sources for Smile Bet WC 2026 posts

Use this file as source map for writing promo posts.

## Official tournament context

Primary official destination:
- FIFA World Cup 2026 hub: `https://www.fifa.com/en/tournaments/mens/worldcup/canadamexicousa2026`

Use official source for:
- tournament identity and branding
- host framing around Canada, Mexico, USA
- format/news context when manually confirmed
- official tone anchors for launch or milestone posts

Note:
- direct fetch from FIFA may fail in tooling due anti-bot/Cloudflare
- if fetch fails, do not invent quotes
- use repo-approved factual sources below for operational writing

## Fixture seed source already approved in repo

Workspace design doc points to OpenFootball public seed:
- `https://raw.githubusercontent.com/openfootball/worldcup.json/master/2026/worldcup.json`

Use for:
- match pairings
- groups
- round labels
- scheduled dates/times in seed
- venue labels in seed

Examples confirmed in current seed:
- opener: Mexico vs South Africa, 2026-06-11, Group A, Mexico City
- Brazil vs Morocco, 2026-06-13, Group C, New York/New Jersey (East Rutherford)
- USA vs Paraguay, 2026-06-12, Group D, Los Angeles (Inglewood)

## Live refresh source for operations

Design doc primary API source:
- API-Football / API-Sports: `https://v3.football.api-sports.io`
- suggested endpoint: `GET /fixtures?league=1&season=2026`

Use for:
- latest fixture changes
- live status
- post-match result sync
- pre-post fact check when API access exists

## Workspace truth for Smile Bet mechanics

Read these local files for product rules:
- `docs/wc2026_betting_design.md`
- `data/wc2026_betting/matches.csv`
- `data/wc2026_betting/teams.csv`
- `data/wc2026_betting/final_jackpot.csv` when jackpot angle matters

If local fixture files are missing or stale, approved fallback is OpenFootball 2026 seed above.

## Time conversion rule

All user-facing match time must be shown in Vietnam time: `Asia/Ho_Chi_Minh` = `UTC+7`.

When source gives local kickoff like `HH:MM UTC-6`, convert by offset math first, then update date if day rolls over.

Quick reference:
- `UTC-7 -> Vietnam +14 hours`
- `UTC-6 -> Vietnam +13 hours`
- `UTC-5 -> Vietnam +12 hours`
- `UTC-4 -> Vietnam +11 hours`

Never paste raw source timezone into final Google Chat post unless user explicitly asks for source/local venue time too.

Current rules to state exactly:
- each new member starts with 200 point
- win/draw/loss ticket costs 20 point
- exact score ticket costs 10 point
- if no exact-score winner, pool moves to final jackpot

## Recommended post angles

- launch hype: World Cup coming, everyone has starter points, jump in early
- fixture hype: spotlight 3-5 upcoming matches with match ids
- rivalry hype: big-team clashes from `matches.csv`
- jackpot hype: no exact-score winner means jackpot grows
- settle recap: announce winners, then point people toward next slate

## Safety

- prefer local workspace files over memory for mutable schedule facts
- if official page unavailable, cite seed/API-based facts only
- do not claim a fixture is final if only seed says so and API check not done
- do not invent odds, rankings, injuries, or qualification stories without source
