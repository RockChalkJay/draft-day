// ============================ State ============================
let rawPlayers = [];      // from GET /api/players (raw merged columns)
let players = [];          // normalized UI objects + live valuations
let byId = new Map();
let staticResult = null;   // cached POST /api/rankings/static response
let pdmMap = {}, inflation = 1, marketHeat = 1;
let maxTierByPos = {};  // per-position badge color scale (tiers are per-position)
let teams = [];
let startingBankroll = 200;   // per-team starting budget, for live inflation
let draftStarted = false;
let myTeamId = "t0";
let nominatedId = null;
let sortKey = "ecr", sortDir = 1;  // default: FantasyPros overall ranking
let posFilter = null, searchQuery = "";
let numTiers = 5;
let scoringConfig = { preset: "ppr" };
let rosterConfig = { qb_starters:1, rb_starters:2, wr_starters:2, te_starters:1, flex_spots:1, k_starters:1, dst_starters:1, bench_spots:6 };
