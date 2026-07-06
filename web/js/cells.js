// ============================ Board: table config + cell renderers ============================
// Rank | ECR | Player | Team | Pos | Pos# | Worth | Value | ESPN Value | ADP |
// ±ADP | Bargain | Tier | Bye | Inj | Tgt% | TmTot | Sleeper.
// Worth/Value/ESPN Value sit together: live price, computed
// scarcity-based value, and the real market's own live auction consensus.
const COLS = [
  {key:"rank", label:"Rank"}, {key:"ecr", label:"ECR"}, {key:"name", label:"Player"},
  {key:"team", label:"Team"}, {key:"position", label:"Pos"}, {key:"pos_rank", label:"Pos#"},
  {key:"worth", label:"Worth"}, {key:"value", label:"Value"}, {key:"live_auction_value", label:"ESPN Value"},
  {key:"adp", label:"ADP"}, {key:"ecr_vs_adp", label:"±ADP"},
  {key:"bargain", label:"Bargain"}, {key:"tier", label:"Tier"}, {key:"bye", label:"Bye"},
  {key:"injury_risk", label:"Inj"}, {key:"target_share", label:"Tgt%"}, {key:"team_total", label:"TmTot"},
  {key:"sleeper", label:"Sleeper"},
];
// A "sleeper" = the experts rank him well ahead of where the market drafts him
// (±ADP strongly positive) at a late-round price — the computed version of an
// editorial sleepers list, derived from FantasyPros ECR/ADP for every player.
const SLEEPER_MIN_DELTA = 15, SLEEPER_MIN_ADP = 60;
function isSleeper(p){ return p.ecr_vs_adp!=null && p.adp!=null && p.ecr_vs_adp >= SLEEPER_MIN_DELTA && p.adp >= SLEEPER_MIN_ADP; }
function sleeperCell(p){
  if(!isSleeper(p)) return `<span style="color:var(--muted);">–</span>`;
  return `<span title="Sleeper: experts rank him ${p.ecr_vs_adp} spots ahead of market ADP (${Number(p.adp).toFixed(0)}) — late-round value the room may miss.">💤</span>`;
}
// One entry per COLS key so every column header gets a hover tooltip;
// anything added to COLS without an entry here just shows no tooltip rather
// than silently being skipped from a growing if-chain (the bug that let four
// columns go untitled before this was a lookup).
const COLUMN_TOOLTIPS = {
  rank: "Overall rank by live Worth (Price). Compare with ECR to spot divergence.",
  ecr: "FantasyPros expert consensus overall rank (ECR)",
  name: "Player name",
  team: "NFL team",
  position: "Position: QB, RB, WR, TE, K, or DST",
  pos_rank: "Positional rank (e.g. 3 on a WR row = WR3)",
  worth: "Price — what it'll take to win him right now (Value scaled by live market inflation)",
  value: "Value — stable salary-cap dollars from FantasyPros projections (what he's worth)",
  live_auction_value: "ESPN Value — ESPN's live auction value: the average of what real ESPN drafters are actually paying, across many live ESPN auction leagues. Calibrated to ESPN's typical league, not necessarily yours — a comparison number, not blended into Value/Worth.",
  adp: "Average Draft Position — where the market actually drafts him (ESPN's live consensus, or FFC as fallback)",
  ecr_vs_adp: "Expert rank (ECR) vs market ADP. Positive = experts rank him higher than the market drafts him — potential value.",
  bargain: "Value − Price. Green = underpriced (target), red = overpriced (reach).",
  tier: "Tier — colored badge, per-position (each position's best cluster is tier 1). 🚨 = a live tier cliff is opening up right below him.",
  bye: "Bye week — flagged with ⚠ if it collides with a starter you already roster at this position",
  injury_risk: "Injury risk from multi-season injury history (weeks Out/Doubtful per season)",
  target_share: "Prior-season target share (nflverse)",
  team_total: "Team's Vegas implied points total — offensive environment",
  sleeper: `💤 = experts rank him ≥${SLEEPER_MIN_DELTA} spots ahead of market ADP at a late-round price (ADP ${SLEEPER_MIN_ADP}+) — computed sleepers list. Sort to see the biggest gaps.`,
};
function bargainCell(b){
  if(b==null || b===0) return `<span style="color:var(--muted);">–</span>`;
  const col = b>0 ? "var(--good)" : "var(--warn)";
  return `<span style="color:${col};font-weight:600;" title="${b>0?"underpriced — target":"overpriced — reach"}">${b>0?"+":""}${b}</span>`;
}
function injuryCell(r){
  if(!r) return `<span style="color:var(--muted);">–</span>`;
  const col = r==="High" ? "var(--warn)" : r==="Med" ? "var(--accent)" : "var(--good)";
  return `<span style="color:${col};font-size:12px;">${r}</span>`;
}
function tierCell(p){
  const t = p.tier;
  if(t==null) return `<span style="color:var(--muted);">–</span>`;
  // Tiers are per-position (each position's best cluster is tier 1), so both
  // the color scale and the tooltip are anchored to that position's tier count.
  const maxT = maxTierByPos[p.position] || Math.max(numTiers, t);
  const frac = maxT>1 ? (t-1)/(maxT-1) : 0;
  const col = frac<=0.34 ? "var(--good)" : frac<=0.67 ? "var(--accent)" : "var(--warn)";
  // Live tier-cliff marker: points drop >10% within two undrafted spots below
  // him at his position — grab-him-now urgency the static tier can't show.
  const cliff = p.tcm!=null && p.tcm >= 1.1
    ? `<span title="Tier cliff: big projected-points drop right below him at ${p.position} — last chance at this level." style="margin-left:4px;">🚨</span>`
    : "";
  return `<span class="tier-badge" style="background:${col};" title="${p.position} tier ${t} of ${maxT}">${t}</span>${cliff}`;
}
function adpCell(d){
  if(d==null) return `<span style="color:var(--muted);">–</span>`;
  const txt = (d>0?"+":"") + d;
  if(d >= 10) return `<span style="color:var(--good);font-weight:600;" title="Experts rank him ${d} spots above market ADP — the room may underprice him.">${txt}</span>`;
  if(d <= -10) return `<span style="color:var(--warn);" title="Market ADP is ${-d} spots above expert rank — the room may overpay.">${txt}</span>`;
  return `<span style="color:var(--muted);">${txt}</span>`;
}
function ecrDivergence(p, rankMap, ecrRankMap){
  // Both ranks computed over undrafted players only, so the comparison stays
  // apples-to-apples as the board thins (a static overall ECR would drift).
  const mine = rankMap.get(p.id), fp = ecrRankMap.get(p.id);
  if(mine==null || fp==null) return "";
  const diff = fp - mine;  // positive: our algo ranks him better than FP
  if(diff >= 3) return `<span style="color:var(--good);" title="Our algo ranks him ${diff} spots higher than FantasyPros — potential value the room may not see.">▲</span>`;
  if(diff <= -3) return `<span style="color:var(--warn);" title="FantasyPros ranks him ${-diff} spots higher than our algo — the room may pay more than we think he's worth.">▼</span>`;
  return "";
}
