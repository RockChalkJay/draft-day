// ============================ Config / constants ============================
const POSITIONS = ["QB","RB","WR","TE","K","DST"];
const SUGGESTION_POSITIONS = ["QB","RB","WR","TE"]; // K/DST excluded from suggestions
const DEFAULT_TEAM_NAMES = ["Me","Dynasty Disasters","Gridiron Gang","End Zone Elite","Touchdown Titans","Blitz Brigade","Pigskin Pirates","Hail Mary Heroes","Red Zone Renegades","Fumble Force","Sack Attack","The Waiver Wired"];

// Build the ordered list of roster slots from the roster config, so My Roster and
// every team match the league's actual settings (Sleeper roster_positions).
function buildRosterTemplate(cfg){
  const t = [];
  const push = (pos, n) => { for(let i=0;i<(n||0);i++) t.push(pos); };
  push("QB", cfg.qb_starters); push("RB", cfg.rb_starters); push("WR", cfg.wr_starters);
  push("TE", cfg.te_starters); push("FLEX", cfg.flex_spots);
  push("K", cfg.k_starters); push("DST", cfg.dst_starters); push("BENCH", cfg.bench_spots);
  return t;
}
