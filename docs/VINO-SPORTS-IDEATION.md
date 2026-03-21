# Vino Sports — Ideation

> Domain acquired: **vinosports.com**

---

## Vision

Vino Sports is a brand umbrella for sport-specific betting simulation sites. Each
sport gets its own Django project with its own data models, API integrations, bot
personas, and deploy — unified under a shared brand and (eventually) shared
engineering infrastructure.

### Current & Planned Properties

| Sport | Project | Status |
|-------|---------|--------|
| EPL (English Premier League) | `epl-bets` | Live, phases 1–35+ complete |
| NBA | `nba-bets` | Planned, see `docs/NBA-BETS-PLAN.md` |

---

## Monorepo Strategy

### The Good Version

A monorepo with **separate Django projects** that share a brand, not a codebase:

```
vinosports/
├── epl/                  # standalone Django project (current epl-bets, moved in)
├── nba/                  # standalone Django project
├── shared/               # small Python package, extracted over time
│   ├── core/             # BaseModel, id_hash
│   ├── betting/          # balance ledger, settlement math, parlay evaluation
│   ├── bots/             # BotStrategy base class, comment service interface
│   ├── activity/         # ActivityEvent, WebSocket consumer base
│   └── templates/        # shared components (empty_state, toasts, etc.)
├── docker-compose.yml    # orchestrates both projects (or one at a time)
└── pyproject.toml        # workspace-level tooling (ruff, shared dev deps)
```

### The Bad Version (Avoid)

Cramming multiple sports into one Django project with `if sport == "nba"` branching,
shared migrations, cross-sport database joins, or a premature "generic sport" abstraction
layer. The domain details diverge fast — conferences, divisions, playoffs, bet markets,
season structures, API providers — and a generic abstraction fights you at every turn.

### Why Monorepo Can Work

- Each sport is independently runnable and deployable (`cd nba/ && docker compose up`)
- No cross-sport database joins or shared migrations
- Monorepo tooling is genuinely shared: ruff config, CI pipelines, Docker base images, deploy scripts
- The brand layer (vinosports.com landing page, cross-sport accounts someday) has a natural home
- `shared/` extractions are based on proven duplication, not speculation

### Discipline Required

- **`shared/` starts empty.** Extract only after building the second project and confirming code is truly identical. Two copies of similar code is fine until proven otherwise.
- **Independent deploys.** If one project can't start without the other, something is wrong.
- **Shared package changes need both consumers' tests passing.**
- **No premature abstraction.** Three similar lines in two projects is better than a fragile generic helper.

---

## Recommended Sequence

1. **Build `nba-bets` as a standalone repo** using the plan in `docs/NBA-BETS-PLAN.md`
2. **Get it to a working state** — core pages, betting flow, bots, tests passing
3. **Compare the two codebases side by side** — identify what's actually identical vs. superficially similar
4. **Create the vinosports monorepo** and move both projects in
5. **Extract `shared/` incrementally** based on real duplication evidence

The domain is the brand. The monorepo is the engineering. They don't have to happen
at the same time.

---

## Future Possibilities (Not Committed)

- Cross-sport user accounts (single login, per-sport balances)
- vinosports.com landing page linking to each sport
- Shared leaderboard across sports
- Additional sports (NFL, MLB, Champions League, etc.)
- Shared bot framework with sport-pluggable strategies
