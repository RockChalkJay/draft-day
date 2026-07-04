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

### How Value / Worth / Bargain are computed

The board leads with three numbers, and the gap between two of them is the
actual signal:

- **Value** — a stable salary-cap dollar figure: what a player is worth to a
  roster, independent of how the draft is unfolding. Computed the same way
  FantasyPros' own salary-cap calculator works — VBD (value over replacement)
  converted to dollars — run on FantasyPros projections and parameterized by
  your league's teams/budget/roster. It sums to the full league budget across
  the drafted pool (a real auction-value baseline, not an arbitrary curve).
- **Worth** (the headline column) — the *live* price: what it should actually
  take to win him right now, given who's already gone and how much money is
  left in the room:

  ```
  worth = 1 + (value − 1) × inflation × phase
  inflation = (remaining_cash − remaining_slots) / Σ(value − 1 over expected picks)
  phase     = 1 − 0.2 × t²,  t = fraction of league roster slots filled
  ```

  At draft start `inflation == 1` and `phase == 1`, so Worth equals Value. Two
  forces then move it:

  - *Reactive* — as the room spends faster or slower than the board's value
    depletes, `inflation` scales Worth with it: an early run of overpays drains
    cash faster than value leaves the board, so every remaining Worth falls
    (the dollars a rival overspent are dollars no longer chasing everyone
    else); a run of bargains pushes it back up.
  - *Anticipatory* — realized auction prices reliably sag below sheet value as
    the draft progresses (rosters fill, the pool of bidders who still need a
    given player shrinks, and rooms finish with money unspent), so `phase`
    prices that in ahead of time: quadratic decay, near-par through the
    early/mid draft, steepening to −20% as the last slots fill. A disciplined
    room that keeps paying par accumulates surplus cash, pushing `inflation`
    above 1 and offsetting the decay — the factors are designed to compose.
- **Bargain** = `Value − Worth`. Positive (green) means the live price has
  fallen below what he's actually worth — a target. Negative (red) means the
  room is paying more than he's worth — let him go. This is the most
  decision-useful column on the board: rankings alone don't tell you where the
  market is mispricing someone, but this does.

Alongside these, the engine computes projection-based analytical signals shown
as columns but that don't feed the price directly (FantasyPros' projections
already price in a player's role, so folding these on top would double-count):

- **Injury risk** — Low/Med/High from multi-season injury-report history
  (nflverse).
- **Target share** — prior-season share of team targets (nflverse); receiving
  volume signal.
- **Team total** — the player's team's Vegas-implied scoring total (nflverse
  schedule/odds data); a proxy for offensive environment.
- **Tier / TCM / PDM** — cliff detection on projected points, tier-cliff
  steepness, and positional scarcity vs. open slots.

`points`/`tier`/`VORP`/**Value** are **static** (computed once per scoring/
roster config); **Worth**, **Bargain**, `inflation`, TCM and PDM are **live**
(recomputed after every pick). Kickers and defenses are tracked for ownership
and price paid only — never assigned a Value/Worth or surfaced as a suggestion.

An optional `data/auction_values.csv` (columns: `player`, `value`) overrides
the computed Value with your own figures if you have them (e.g. exported from
a tool you have access to) — matched by player name, applied automatically
when present.

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
- **Main table** — the full undrafted board, sortable by any column, default
  sorted by FantasyPros overall rank (ECR):
  - `#` — overall rank by live `Worth`.
  - `ECR` — FantasyPros expert consensus overall rank.
  - `Bye` — flagged with ⚠ when it collides with a starter you already roster at
    the same position.
  - `Worth` (live price) and `Value` (stable salary-cap baseline) side by side,
    plus `Bargain` (Value − Worth, green = target / red = reach).
  - `Inj` (injury-risk tier), `Tgt%` (prior-season target share), `TmTot`
    (Vegas-implied team scoring total), `Tier`.
  - A search box filters by player or team name.
- **Market** (header) — live inflation multiplier: >1 means Worth has climbed
  above Value (prices running hot), <1 means Worth has fallen below Value
  (bargains on the board).
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
| `POST /api/rankings/live` | after every pick / undo | TCM/PDM/Value → inflation → Worth/Bargain |

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

- **Value** is computed (VBD → dollars from FantasyPros projections), not
  scraped from FantasyPros' own salary-cap calculator: that tool's per-player
  output only renders after login, in a JS app, and customizing league settings
  (teams/budget/roster) is gated behind FantasyPros Premium — so it can't be
  scraped for free, and its login is reCAPTCHA-protected. Computing Value from
  the same projections/methodology sidesteps both.
- `inflation` is a single global multiplier (not per-position) and clamped to
  [0.5, 1.8] so one early over/underpay can't swing the whole board. Per-position
  inflation (an RB run pricing up remaining RBs specifically) is a possible
  refinement.
- `target_share` / `team_total` / injury history are prior-season nflverse data
  (free, no key). Rookies and players with no NFL history have blank values —
  there's no projection-adjustment for a rookie's expected role.
- K/DST price at `$0` by design; they're tracked for ownership and bid only.
- FantasyPros projections are pulled with `week=draft` (full-season totals);
  without it the page defaults to next week's per-game numbers.
