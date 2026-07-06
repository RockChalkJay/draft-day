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
player cost right now?**

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
  take to win the player right now, given who's already gone and how much money is
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
- **Tier / TCM / PDM** — cliff detection on projected points (the Tier badge),
  live tier-cliff steepness (surfaced as the 🚨 marker on the Tier badge), and
  positional scarcity vs. open slots (PDM; returned by the API, not shown on
  the board).

`points`/`tier`/`VORP`/**Value** are **static** (computed once per scoring/
roster config); **Worth**, **Bargain**, `inflation`, TCM and PDM are **live**
(recomputed after every pick). Kickers and defenses are tracked for ownership
and price paid only — never assigned a Value/Worth or surfaced as a suggestion.

Value is always computed, never hand-entered: there is no file to create or
sheet to import. See **Data Setup** below for exactly what's fetched and from
where.

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
Board — nothing to configure, nothing to upload. See **Data Setup** below for
exactly what's fetched and from where.

## Data Setup

Every field on the board comes from a free, keyless, no-login data source,
fetched automatically. There is no manual import, no CSV to create, no PDF to
print, no account to log into — none of that exists in this app.

Every request for the player pool resolves data in this order:

1. **Cache** — `data/players_raw.parquet`, if younger than
   `DRAFTDAY_CACHE_TTL_HOURS` (default `24`).
2. **Live fetch** — pulls from every source below, merges them into one table,
   and writes a fresh cache.
3. **Stale cache** — if the live fetch fails (no network, a source down) but
   an old cache exists, real-but-old data is served rather than falling back
   to fake data.
4. **Bundled sample** — `data/sample_players.json`, the last resort, so the
   app always loads something.

The header always shows the player count and which source you're on
(`live`/`cache`/`sample`) — in red on the demo sample, since drafting off fake
data unnoticed is the failure mode that actually matters.

```bash
DRAFTDAY_OFFLINE=1 uvicorn src.api.app:app --port 8000   # skip the network entirely, instant demo load
```

Force a fresh pull mid-session (bypasses the cache, rewrites it):
`GET /api/players?refresh=true`.

### Data sources (all free, no key, no login)

| Source | What it provides | Auth |
|---|---|---|
| FantasyPros | Projections, ECR, expert tier, positional rank, bye | None |
| ESPN | Consensus ADP, auction value, ownership%/start% | None |
| FFC (Fantasy Football Calculator) | ADP (fallback if ESPN's is thin) | None |
| Sleeper | Player IDs, current injury status | None |
| nflverse | Prior-season target share/usage, injury history, Vegas-implied team totals | None |

FantasyPros' pages used here (projections, ECR/rankings) are public and
unauthenticated; only its separate ADP page and salary-cap calculator are
account-gated, which is why neither is used — ESPN's public player endpoint
(no league, no login) supplies live ADP and auction value instead. See *Notes
& known scope* for why FantasyPros stays in the mix for projections/ECR rather
than being the sole source of truth.

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
  Columns, in order:
  - `Rank` — overall rank by live `Worth`.
  - `ECR` — FantasyPros expert consensus overall rank, with a divergence arrow
    (▲ our algo ranks him ≥3 spots higher than FP among undrafted players —
    potential value; ▼ FP ranks him higher — the room may overpay).
  - `Player`, `Team`; `Pos` / `Pos#` — position and positional rank (WR3).
  - `Worth` (live price), `Value` (stable salary-cap baseline), and
    `ESPN Value` (ESPN's live crowd-sourced auction value — what real ESPN
    drafters are actually paying, averaged across many live ESPN leagues)
    side by side — the computed price, the computed value, and the real
    market's own number, for direct comparison. ESPN Value is calibrated to
    ESPN's typical league settings, not necessarily yours, so it can
    legitimately differ
    from Value/Worth; it's shown, never blended in.
  - `ADP` — where the market actually drafts him (ESPN's live consensus ADP →
    FFC, first available), and `±ADP` = ADP − ECR (green ≥ +10: experts rank
    him well ahead of the market — target).
  - `Bargain` (Value − Worth, green = target / red = reach).
  - `Tier` (colored badge, **per-position** — each position's best cluster is
    tier 1; a 🚨 marker means a live tier cliff — points drop >10% within two
    undrafted spots below him at his position, i.e. last chance at this level).
  - `Bye` — flagged with ⚠ when it collides with a starter you already roster
    at the same position; `Inj` (injury-risk tier), `Tgt%` (prior-season
    target share), `TmTot` (Vegas-implied team scoring total).
  - `Sleeper` — 💤 when the experts rank him ≥15 spots ahead of market ADP at
    a late-round price (ADP 60+): a computed sleepers list covering every
    player instead of an editor's dozen. Sort the column to see the biggest
    expert-vs-market gaps first.
  - A search box filters by player or team name.
- **My Max Bid** (header) — bankroll minus $1 for each other open slot: the
  most you can actually put on one player. Recorded picks are validated against
  each team's max bid (and a $1 minimum), matching real auction-room rules.
- **Market** (header) — the effective price level Worth is computed at
  (`inflation × phase`): >1 means Worth has climbed above Value (prices running
  hot), <1 means Worth has fallen below Value (bargains on the board). Hover to
  see the two components — cash-vs-board inflation and draft-phase decay —
  separately.
- **My Roster** (top-right) — your slots, byes, and prices paid. The ↩ button
  undoes a pick (returns the bid, frees the slot, reruns valuation).

### League
Read-only view of every team's bankroll and full roster (slot / player / price).

### Settings
- **Import from Sleeper** — paste a league ID and load its scoring settings and
  roster positions directly from Sleeper's public API (runs in your browser);
  applied immediately. Roster tags with no dedicated slot type here
  (SUPER_FLEX, IDP slots) are mapped to BENCH so the total slot count — which
  drives all pricing math — stays correct; superflex QB pricing and IDP players
  are otherwise out of scope.
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
data/            sample_players.json (committed, offline fallback);
                 players_raw.parquet (live-fetch cache, gitignored)
tests/           ingestion/, rankings/, api/  —  synthetic data, no network
```

## Notes & known scope

- **Value** is computed (VBD → dollars), not sourced from any one site's own
  auction calculator: FantasyPros' salary-cap calculator only renders
  per-player output after a Premium login, in a JS app, so it can't be scraped
  for free; ESPN's auction value is real market data but is calibrated to
  ESPN's own typical league settings, not necessarily yours. Computing Value
  from projections + your league's actual teams/budget/roster sidesteps both,
  and ESPN's auction value is instead surfaced as its own comparison signal —
  see the ADP/±ADP columns.
- **FantasyPros isn't the sole source of truth.** Projections, ECR, and expert
  tier come from FantasyPros' free (unauthenticated) pages, but ADP/auction
  value/ownership come from ESPN's public player endpoint, and ADP falls back
  to FFC if ESPN's is thin. If any one of these sources goes down or changes
  its page, the pipeline degrades (missing columns, not a crash) rather than
  depending on a single provider.
- `inflation` is a single global multiplier (not per-position) and clamped to
  [0.5, 1.8] so one early over/underpay can't swing the whole board. Per-position
  inflation (an RB run pricing up remaining RBs specifically) is a possible
  refinement.
- The draft-phase decay is likewise one global curve (`PHASE_DECAY = 0.2` in
  `src/rankings/inflation.py`); per-position decay (TE prices collapse once
  every team has one, while late RB scarcity can hold prices up) is a possible
  refinement.
- `target_share` / `team_total` / injury history are prior-season nflverse data
  (free, no key). Rookies and players with no NFL history have blank values —
  there's no projection-adjustment for a rookie's expected role.
- K/DST price at `$0` by design; they're tracked for ownership and bid only.
- ESPN's endpoints are undocumented (no official public API contract), so a
  future ESPN-side change could break the fetcher; it fails soft (empty
  frame) rather than crashing the pipeline, falling back to FFC for ADP.
- FantasyPros projections are pulled with `week=draft` (full-season totals);
  without it the page defaults to next week's per-game numbers.
