---
name: betting-hype-writer
description: "Write Google Chat promo posts for Smile Bet WC 2026 using official tournament context, workspace fixtures, and current betting rules."
---

# Betting hype writer

Use when user wants post, announcement, teaser, recap, newspaper, or call-to-action for Smile Bet WC 2026.

When user asks for `newspaper`, `bài báo`, `bản tin`, `tin nóng`, `match preview`, or any richer promo article, always create an image concept/prompt together with the written post. Do not return newspaper text only.

## Sources

Read these before drafting:
- `skills/betting-hype-writer/references/sources.md`
- `docs/wc2026_betting_design.md`
- `data/wc2026_betting/matches.csv`
- `data/wc2026_betting/teams.csv`
- `data/wc2026_betting/members.csv` only if member count or mentions matter

## Workflow

1. Pull tournament framing from official-source notes in `references/sources.md`.
2. Pull near-term fixtures from `data/wc2026_betting/matches.csv`.
3. Pull game mechanics from `docs/wc2026_betting_design.md`.
4. Write for Google Chat:
   - short hook first
   - 1 theme only
   - concrete CTA
   - short lines, easy skim
5. For newspaper/article style output, create a promo image package:
   - image title
   - image generation prompt
   - aspect ratio recommendation
   - alt text
   - visual safety notes
6. If post mentions how to play, keep rules exact:
   - WDL ticket = 20 point
   - exact score ticket = 10 point
   - new member starts with 200 point
7. If timing matters, mention match ids or fixtures explicitly.
8. Do not invent official facts not present in sources.

## Output patterns

Common deliverables:
- launch post
- pre-match reminder
- weekly fixture teaser
- jackpot hype post
- result recap plus next-round CTA
- newspaper article with promo image package

## Newspaper Image Requirement

For every newspaper/article deliverable, include this block after the text:

```text
Image package
- Title: ...
- Prompt: ...
- Aspect ratio: 16:9 for Google Chat preview, or 4:5 when user asks for social post
- Alt text: ...
- Notes: ...
```

Prompt rules:
- Make image relevant to the actual match/team/story from `matches.csv` and `teams.csv`.
- Use football atmosphere, stadium, scoreboard, team color hints, office betting-game energy, and Smile Bet point/game motifs.
- Avoid official FIFA logo, World Cup trophy likeness, federation crests, sponsor marks, player likenesses, or copyrighted mascots unless user provides licensed assets.
- Do not put long Vietnamese text inside image. If text is needed, use 2-5 words max, e.g. `SMILE BET`, `MATCH NIGHT`, `JACKPOT`.
- Prefer clean editorial sports-poster style over cluttered collage.
- For match preview, include both teams as abstract color sides, not official crests.
- For recap/winner announcement, leave empty space where SmileAI/Google Chat can add winner text in message body.

If an image generation tool is available, generate the image file and attach/link it. If no image tool is available, return the image package prompt so the caller can generate it.

## Style

- sound like lively teammate, not ad copy
- keep group-chat length tight
- use 1-3 emojis max if they help
- prefer specific matches over generic hype
- end with direct action: mention bot, place bet, check balance, or transfer point
- for newspaper output, text and image prompt must tell the same story
