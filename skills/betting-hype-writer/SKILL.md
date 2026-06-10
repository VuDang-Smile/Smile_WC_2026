---
name: betting-hype-writer
description: "Write Google Chat promo posts for Smile Bet WC 2026 using official tournament context, workspace fixtures, and current betting rules."
---

# Betting hype writer

Use when user wants post, announcement, teaser, recap, newspaper, or call-to-action for Smile Bet WC 2026.

When user asks for `newspaper`, `bài báo`, `bản tin`, `tin nóng`, `match preview`, or any richer promo article, always include a web image search package together with the written post. Do not return newspaper text only.

## Sources

Read these before drafting:
- `skills/betting-hype-writer/references/sources.md`
- `docs/wc2026_betting_design.md`
- `data/wc2026_betting/match_bet_sheets/00_index.csv`
- `data/wc2026_betting/members.csv` only if member count or mentions matter

## Workflow

1. Pull tournament framing from official-source notes in `references/sources.md`.
2. Pull near-term fixtures from `data/wc2026_betting/match_bet_sheets/00_index.csv`.
3. Pull game mechanics from `docs/wc2026_betting_design.md`.
4. Write for Google Chat:
   - short hook first
   - 1 theme only
   - concrete CTA
   - short lines, easy skim
5. For newspaper/article style output, create a web image selection package:
   - image title
   - source search queries
   - aspect ratio recommendation
   - alt text
   - visual safety notes
   - Vietnam-time kickoff line when match timing matters
6. If post mentions how to play, keep rules exact:
   - WDL ticket = 20 point
   - exact score ticket = 10 point
   - new member starts with 200 point
7. If timing matters, convert fixture kickoff to Vietnam time (`Asia/Ho_Chi_Minh`) before writing.
8. Mention match ids explicitly when timing or fixture identity matters.
9. Do not invent official facts not present in sources.

## Output patterns

Common deliverables:
- launch post
- pre-match reminder
- weekly fixture teaser
- jackpot hype post
- result recap plus next-round CTA
- newspaper article with web image package

## Newspaper Image Requirement

For every newspaper/article deliverable, include this block after the text:

```text
Web image package
- Title: ...
- Search queries: ...
- Aspect ratio: 16:9 for Google Chat preview, or 4:5 when user asks for social post
- Alt text: ...
- Notes: ...
```

Image search rules:
- Make image relevant to the actual match/team/story from `data/wc2026_betting/match_bet_sheets/00_index.csv`.
- Prefer real web banners or editorial match posters that already show both teams or unmistakable two-team pre-match framing.
- Prefer 16:9 hero/banner crops that fit Google Chat preview without extra redesign.
- Reject generated images, synthetic posters, repo-rendered mockups, or any internally generated newspaper/image artifact unless user explicitly asks for them.
- Reject weak images that do not clearly present the two sides, or that feel generic, blurry, low-resolution, or collage-heavy.
- For recap/winner announcement, leave empty space where SmileAI/Google Chat can add winner text in message body.

Do not use image generation. Search the web for real, high-quality match-relevant banner images when browsing is available. Prefer official broadcasters, editorial sports outlets, preview pages, or video thumbnails that clearly frame both teams. If browsing is unavailable, provide 3-5 specific search queries and quality criteria.

## Style

- sound like lively teammate, not ad copy
- keep group-chat length tight
- use 1-3 emojis max if they help
- prefer specific matches over generic hype
- all user-facing match time must be shown in Vietnam time (`Asia/Ho_Chi_Minh`)
- end with direct action: mention bot, place bet, check balance, or transfer point
- for newspaper output, text and web image package must tell the same story
