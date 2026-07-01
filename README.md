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

It does so with a six-piece valuation pipeline:

1. **Scoring** — projections → fantasy `points`, for your league's scoring.
2. **Tiers** — cliff detection on `points` (real score drops, not arbitrary cuts).
3. **Replacement / VORP** — value over the waiver-wire replacement at each position.
4. **TCM** (Tier-Cliff Multiplier) — *live*; how steep the drop is to the next
   options still on the board.
5. **PDM** (Positional Demand Multiplier) — *live*; league-wide scarcity of
   elite players vs. open slots.
6. **Inflation** — *live*; per-position price inflation as cash and VORP deplete
   unevenly.

`worth` is a **budget-conserving** auction price: $1 is reserved for every
remaining roster slot, and the rest of the cash in the room is partitioned across
the skill positions (by each position's original VORP share × its live demand)
and then across players within a position (by `vorp^0.75 × tcm`). So the total of
all predicted prices equals the money left to spend — `worth` is a partition of
the budget, not an unbounded markup. The `vorp^0.75` compression corrects the way
raw VORP over-prices elite studs relative to how auctions actually clear; the
exponent is tunable per league.

Pieces 1–3 are **static** (computed once per scoring/roster config); pieces 4–6
are **live** (recomputed after every pick). Kickers and defenses are tracked for
ownership and price paid only — they are never assigned a `worth` or surfaced as
a suggestion.

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
  - `Worth`, `Tier`, `VORP`, `TCM`, `PDM`.
  - A search box filters by player or team name.
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
| `POST /api/rankings/live` | after every pick / undo | TCM → PDM → budgets → worth |

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

- `worth` is budget-conserving: predicted prices sum to the cash left in the
  room. TCM/PDM redistribute that fixed pot (toward cliffs and scarce positions)
  rather than inflating the total; a uniform PDM across positions cancels out.
- The `vorp^0.75` compression is a calibration for real-world bidding; adjust it
  (`WORTH_COMPRESSION` in `valuation.py`) if your league prices studs differently.
- K/DST price at `$0` by design (no VORP computed).
- ECR data is ingested; currently only the consensus `rank_ecr` is surfaced (the
  `FP` column). Variance signals (`rank_std`, etc.) are ingested but not yet used.
