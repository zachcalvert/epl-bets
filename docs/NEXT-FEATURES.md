# Next Features

Three greenfield features under consideration. Match Discussion Threads is the first priority as a high-leverage move that adds social depth with minimal new infrastructure.

---

## 1. Match Discussion Threads (first up)

Threaded comment section on the match detail page, below the odds board. Not live chat — standard post-and-reply discussion tied to each match.

**What makes it interesting:**
- Comments linked to a user's actual bet position ("this user bet HOME_WIN") adds credibility signals absent from generic sports forums
- Could gate commenting behind having placed a bet, keeping discussion focused
- Simple model: `Comment` on a `Match`, optional `parent` for single-level replies
- HTMX form submission + partial reload — no WebSocket needed

## 2. Avatars & Profile Graphics

Visual identity for user profiles. Two directions to consider:

- **User-uploaded images** — more personal, requires moderation
- **Generated/selectable system** — zero moderation, fits the play-money platform vibe (identicons, EPL-themed icon sets, unlockable frames tied to badges/achievements)

Layers well on top of discussion threads — comments look better with faces next to them.

## 3. Dynamic Homepage

Content-driven landing page that surfaces narratives from existing data, giving users a reason to visit even when not placing bets.

**Content types (all computable from existing data):**
- Streaks against the spread ("Arsenal has beaten the spread 5 straight")
- Hot bettors ("alice_123 is on a 7-bet win streak")
- Value alerts (significant odds movement between open and current)
- Post-matchday recap cards (upsets, biggest winners)

**RAG integration (stretch goal):**
Could pipe context (recent results, odds movements, betting patterns) into [bbr-chat-service](https://github.com/zachcalvert/bbr-chat-service) to generate editorial-style match previews, recaps, or an interactive Q&A feature. Two possible modes:
- **Content generator** — Celery task calls the service after each matchday, caches output (simpler)
- **Interactive** — users ask questions about form, history, odds (bigger UX commitment, very unique)
