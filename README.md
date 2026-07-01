# Draft Day

A fantasy-football **auction-draft assistant**. It turns merged player
projections into *live, draft-aware* auction values — recomputed after every
pick — so you can see what each remaining player is actually worth as the board
thins and money leaves the room, instead of staring at static pre-draft
rankings.

## Motivation

Pre-draft cheat sheets go stale the moment the draft starts. Once a few elite
backs are gone, a tier cliff that looked far away is suddenly right in front of
you; once a bankroll-heavy team empties out, inflation shifts. Draft Day models
that live state and answers one clean question per player: **what should this
cost right now?**

### How `worth` is computed

`worth` is a **value ceiling** — the most you should pay for a player — scaled
live by market heat:

```
worth = 1 + (AAV − 1) × heat
heat  = (total_spent − num_drafted) / Σ(AAV − 1 over drafted players)
```

`AAV` here is a steep value curve (top ≈ $66, tapering to $1 by ~rank 45): the
top tier carries real money and everyone else is a $1 flier, matching how bids
concentrate on studs. It is deliberately **not** budget-conserving — worth
answers "what's this player worth to me," not "what will the market clear at."

`heat` is the live market signal, starting at 1.0. It compares dollars actually
spent to the value bought: if the room is paying over sticker (a hot draft) heat
rises and the remaining ceilings scale up with it; bargains cool it down. Because
it's driven by spending vs. value — not slot counts — it makes no assumption that
every roster spot gets filled.

Alongside `worth`, the engine computes projection-based analytical signals for
display (they don't feed the price):

1. **Scoring** — projections → fantasy `points`, for your league's scoring.
2. **Tiers** — cliff detection on `points` (real score drops, not arbitrary cuts).
3. **VORP** — value over the waiver-wire replacement at each position.
4. **TCM / PDM** — tier-cliff steepness and positional demand, shown as columns.

`points`/`tiers`/`VORP` are **static** (computed once per config); `worth`,
`heat`, TCM and PDM are **live** (recomputed after every pick). Kickers and
defenses are tracked for ownership and price paid only — never assigned a `worth`
or surfaced as a suggestion.

## Installation

Requires Python 3.10+.

```bash
python -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

Run the test suite (no network required):

```bash
python -m pytest tests/ -q
```

## Running the app

```bash
source venv/bin/activate
uvicorn src.api.app:app --port 8000
# open http://127.0.0.1:8000
```

On first load the app fetches the player pool, computes rankings, and shows the
Board. Player data is resolved in this order: the parquet cache
(`data/players_raw.parquet`), then a live fetch from the ingestion sources, then
the bundled offline sample (`data/sample_players.json`).

**Offline / demo mode** skips the network entirely and serves the bundled
sample, so the app loads instantly:

```bash
DRAFTDAY_OFFLINE=1 uvicorn src.api.app:app --port 8000
```

Force a fresh live pull (and refresh the cache) with `GET /api/players?refresh=true`.

## Usage

The app has three full-screen views (top nav) plus a one-time **Start Draft** modal.

### Board (default)
- **Start Draft** — set team names (the first team is yours), starting bankroll,
  and number of tiers. League size is the number of teams you enter.
- **Suggestion strips** (QB/RB/WR/TE only — K/DST excluded):
  - *Top 5 Overall* — highest `worth` on the board.
  - *Top 3 Per Position*.
  - *Best Value For Your Needs* — the best available player at each position you
    still need to fill a starter slot.
  - Every suggestion chip is clickable and nominates that player.
- **Nominate / Record-pick bar** — pick a player, enter the winning bid and team,
  and **Record Pick**. The roster slot is auto-assigned (position → FLEX →
  BENCH); if the winning team has no eligible open slot the pick is blocked. Live
  valuation reruns automatically.
- **Main table** — the full undrafted board, sortable by any column:
  - `#` — overall rank by computed `worth`.
  - `FP` — FantasyPros expert consensus rank (ECR). **Green ▲** = our algorithm
    rates the player higher than FP (potential value); **red ▼** = FP rates them
    higher.
  - `Bye` — flagged with ⚠ when it collides with a starter you already roster at
    the same position.
  - `Worth` (live auction value) and `AAV` (market baseline) side by side, plus
    `Tier`, `VORP`, `TCM`, `PDM`.
  - A search box filters by player or team name.
- **Market** (header) — live market-heat multiplier: >1 means the room is bidding
  over value ceilings (hot), <1 means value is going through.
- **My Roster** (top-right) — your slots, byes, and prices paid. The ↩ button
  undoes a pick (returns the bid, frees the slot, reruns valuation).

### League
Read-only view of every team's bankroll and full roster (slot / player / price).

### Settings
- **Import from Sleeper** — paste a league ID and load its scoring settings and
  roster positions directly from Sleeper's public API (runs in your browser).
  Then click *Save Settings & Recompute* to apply.
- **Scoring config** and **Roster config** — editable via form fields or raw
  JSON. Saving recomputes the static rankings.

## Configuration

Two backend config objects drive the math:

**`ScoringConfig`** (`src/rankings/scoring.py`) — presets `standard`, `half_ppr`,
`ppr`, with optional per-key overrides. Categories: `passing`, `rushing`,
`receiving` (`rec` is the per-reception weight), `kicking`, `defense`, `misc`.

**`ReplacementConfig`** (`src/rankings/replacement.py`) — starters per position
plus `flex_spots` (an integer count of FLEX slots, mapping directly to Sleeper's
`roster_positions`). Flex demand is split between RB and WR when computing
replacement level.

`num_teams`, `num_tiers`, and starting bankroll are one-time league setup,
collected in the Start Draft modal rather than Settings.

## Architecture

Stateless REST. The **browser owns all draft state** (the `LeagueState`) and
re-sends it on each call, so the server is a pure function of its inputs — no
sessions, no database.

| Endpoint | When | Does |
|---|---|---|
| `GET /api/players` | app load | raw merged player table (cache → live → sample) |
| `POST /api/rankings/static` | draft start / config change | points → tiers → VORP |
| `POST /api/rankings/live` | after every pick / undo | TCM/PDM signals → market heat → worth |

The browser caches the `/static` response and includes it in every `/live`
request along with the current `LeagueState`.

## Project layout

```
src/
  ingestion/     external data sources + merge + pipeline orchestrator
  rankings/      the six-piece valuation engine (+ league_state, valuation)
  api/           FastAPI app, request/response models, serialization
web/             single-page frontend (served by the API at /)
data/            sample_players.json (committed); players_raw.parquet (cache, gitignored)
tests/           ingestion/, rankings/, api/  —  synthetic data, no network
```

## Notes & known scope

- `worth` is a **value ceiling** ("most you should pay"), not a market-clearing
  price: it's steep (top tier carries the money, the rest are $1) and does not
  sum to the budget. The steepness curve lives in `pipeline.py` (`AAV_TOP`,
  `AAV_SPAN`, `AAV_STEEP`) if you want to tune it.
- The value curve is synthesized from FantasyPros ECR **consensus rank** when no
  direct AAV-$ feed is present; a real auction-value source can populate the
  `aav` column upstream to override it.
- Market heat is a single global multiplier and clamped to [0.5, 2.0] so one
  early over/underpay can't swing the board. Per-position heat is a possible
  refinement.
- K/DST price at `$0` by design; they're tracked for ownership and bid only.
- ECR data is ingested; currently only the consensus `rank_ecr` is surfaced (the
  `FP` column). Variance signals (`rank_std`, etc.) are ingested but not yet used.
