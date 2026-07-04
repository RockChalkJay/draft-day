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

An optional `data/auction_values.csv` overrides the computed Value with your
own figures if you have them — matched by player name, applied automatically
when present (skill positions only; K/DST stay $0 by design). Because a sheet
is calibrated to *its* assumed league, the overridden values are then
**renormalized to your league's budget** (a single monotone rescale of the
value premiums, preserving the sheet's relative prices) — without this, the
market math opens broken: inflation starts away from 1.0 and every Bargain
opens red before a single bid. So the displayed Value may differ from the
sheet's printed number when your league's teams/budget/roster differ from the
sheet's assumptions — that difference is the point. A second optional import,
`data/rankings_tiers.csv`, locks ECR/tiers/bye/ADP to a printed FantasyPros
sheet the same way. See **Data Setup** below for how to create both.

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
Board — no manual setup required. See **Data Setup** below for how that data is
resolved automatically, and for the optional manual imports that lock the
board to a specific FantasyPros sheet before a real draft.

## Data Setup

Draft Day needs one thing to run: a table of players with projections, ranks,
ADP, and byes. Two ways to get it, and they layer on top of each other —
automatic needs zero setup, manual imports let you pin the board to an exact
sheet so nothing shifts under you mid-draft.

### Automatic (default — nothing to do)

Every request for the player pool resolves data in this order:

1. **Cache** — `data/players_raw.parquet`, if younger than
   `DRAFTDAY_CACHE_TTL_HOURS` (default `24`).
2. **Live fetch** — pulls FantasyPros projections/ECR/ADP, FFC ADP, Sleeper
   player IDs, and nflverse usage/injury/Vegas data, merges them into one
   table, and writes a fresh cache.
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

### Manual: season-specific sheet imports (optional, recommended before a real draft)

Two gitignored CSVs override parts of the automatically-fetched data —
personal, dated data the repo doesn't track, so they need to be (re)created
each season. Both match by normalized player name (DSTs by team abbreviation)
and apply automatically whenever the file is present; no restart needed if
you write them while the app is already up — just refresh the page or the
`/api/players` call.

**1. Auction values → `data/auction_values.csv`** (columns: `player`, `value`)
overrides the computed `Value` column. Two ways to populate it:
- By hand — any CSV with `player,value` columns (also accepts
  `name`/`player_name` and `salary`/`auction`/`aav`).
- From FantasyPros' free "Cheat Sheet: Positional Rankings" PDF (Auction
  Values → Download PDF):

  ```bash
  python -m src.ingestion.fantasypros_auction_pdf path/to/cheat_sheet.pdf
  ```

  Values are automatically rescaled to your league's actual budget (see *How
  Value/Worth/Bargain are computed* above for why) — the printed sheet number
  and the board's Value can legitimately differ.

**2. Rankings & tiers → `data/rankings_tiers.csv`** overrides ECR, bye weeks,
expert tiers, and ADP/±ADP. Print a FantasyPros cheat-sheet rankings page to
PDF (fantasypros.com/nfl/rankings/ppr-cheatsheets.php → Print → Save as PDF),
then:

```bash
python -m src.ingestion.fantasypros_rankings_pdf path/to/rankings.pdf
```

Both importers validate before writing (e.g. the rankings importer refuses to
write a file with gaps in the overall rank rather than save a silently-partial
sheet) and print how many players they covered.

To point either override at a nonstandard file location, set
`DRAFTDAY_AUCTION_VALUES_PATH` / `DRAFTDAY_RANKINGS_PATH` before starting the
app.

### Optional: FantasyPros login for the full ADP table

FantasyPros' consensus ADP page is registration-fenced: anonymous visitors see
only a ~5-row teaser, but any **free** FantasyPros account unlocks the full
table. The login form itself is captcha-protected, so instead of a
username/password config the app reuses your browser's logged-in session:

1. Sign in (or create a free account) at fantasypros.com in your browser.
2. Open DevTools (⌘⌥I) → **Network** tab, then reload any fantasypros.com page.
3. Click the first request → **Request Headers** → copy the entire value of
   the `Cookie` header.
4. Export it before starting the app:

   ```bash
   export DRAFTDAY_FP_COOKIE='paste the whole cookie value here'
   uvicorn src.api.app:app --port 8000
   ```

   (Then force a refresh with `GET /api/players?refresh=true` if you already
   had a cached pull.)

The cookie expires like any web session — if ADP coverage drops back to
nothing on a later live pull, re-copy it. Without the cookie the app still
gets ADP from the rankings-sheet import (printed while logged in, it carries
ECR-vs-ADP for every player), then FFC's free API as the last fallback.

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
  - `Player` (team rides in the cell); `Pos` / `Pos#` — position and
    positional rank (WR3).
  - `Value` (stable salary-cap baseline) and `Worth` (live price) side by side.
  - `ADP` — where the market actually drafts him (rankings-sheet import →
    FantasyPros ADP page → FFC, first available), and `±ADP` = ADP − ECR
    (green ≥ +10: experts rank him well ahead of the market — target).
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
data/            sample_players.json (committed, offline fallback); everything
                 else gitignored: players_raw.parquet (live cache),
                 auction_values.csv / rankings_tiers.csv (manual sheet imports
                 — see Data Setup)
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
- The draft-phase decay is likewise one global curve (`PHASE_DECAY = 0.2` in
  `src/rankings/inflation.py`); per-position decay (TE prices collapse once
  every team has one, while late RB scarcity can hold prices up) is a possible
  refinement.
- `target_share` / `team_total` / injury history are prior-season nflverse data
  (free, no key). Rookies and players with no NFL history have blank values —
  there's no projection-adjustment for a rookie's expected role.
- K/DST price at `$0` by design; they're tracked for ownership and bid only.
- FantasyPros' ADP page (`/nfl/adp/ppr-overall.php`) is registration-fenced to
  a ~5-row teaser for anonymous visitors; see *Optional: FantasyPros login for
  the full ADP table* under Data Setup for the `DRAFTDAY_FP_COOKIE` setup that
  unlocks the full table.
- FantasyPros projections are pulled with `week=draft` (full-season totals);
  without it the page defaults to next week's per-game numbers.
