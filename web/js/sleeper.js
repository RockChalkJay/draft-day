// ============================ Sleeper import ============================
document.getElementById("sleeperFetchBtn").onclick = async () => {
  const leagueId = document.getElementById("sleeperLeagueId").value.trim();
  const status = document.getElementById("sleeperStatus");
  if(!leagueId){ status.textContent = "Enter a league ID first."; return; }
  status.style.color = "var(--muted)"; status.textContent = "Fetching…";
  try {
    const res = await fetch(`https://api.sleeper.app/v1/league/${leagueId}`);
    if(!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    const s = data.scoring_settings || {};
    const positions = data.roster_positions || [];
    const rec = s.rec ?? 0;
    const preset = rec >= 1 ? "ppr" : rec >= 0.5 ? "half_ppr" : "standard";

    // Full scoring config from Sleeper — all categories, not just the common few,
    // so yardage and reception weights import correctly.
    scoringConfig = {
      passing: { yds: s.pass_yd ?? 0.04, td: s.pass_td ?? 4, int: s.pass_int ?? -2 },
      rushing: { yds: s.rush_yd ?? 0.1, td: s.rush_td ?? 6 },
      receiving: { rec: rec, yds: s.rec_yd ?? 0.1, td: s.rec_td ?? 6 },
      misc: { fl: s.fum_lost ?? -2 },
    };
    // Reflect it in the form + JSON views.
    document.getElementById("scoringPreset").value = preset;
    document.getElementById("scRec").value = rec;
    document.getElementById("scPassTd").value = scoringConfig.passing.td;
    document.getElementById("scRushTd").value = scoringConfig.rushing.td;
    document.getElementById("scInt").value = scoringConfig.passing.int;
    document.getElementById("scoringJsonText").value = JSON.stringify(scoringConfig, null, 2);

    // Roster from Sleeper's roster_positions. Tags with no dedicated slot type
    // here (SUPER_FLEX, IDP slots, ...) are folded into BENCH: the valuation
    // math keys on total slot count (budget - slots discretionary money, $1
    // reserves), so silently dropping them would skew every price on the board.
    const count = pos => positions.filter(p => p === pos).length;
    const KNOWN = new Set(["QB","RB","WR","TE","K","DEF","BN","FLEX","WRRB_FLEX","REC_FLEX","WRRB_WRT"]);
    const unmapped = positions.filter(p => !KNOWN.has(p)).length;
    const flexCount = count("FLEX") + count("WRRB_FLEX") + count("REC_FLEX") + count("WRRB_WRT");
    const benchCount = count("BN") + unmapped;
    rosterConfig = {
      qb_starters: count("QB"), rb_starters: count("RB"), wr_starters: count("WR"),
      te_starters: count("TE"), flex_spots: flexCount,
      k_starters: count("K"), dst_starters: count("DEF"), bench_spots: benchCount,
    };
    if(unmapped) toast(`${unmapped} roster slot(s) (e.g. SUPER_FLEX/IDP) mapped to BENCH — slot count preserved for pricing.`);
    document.getElementById("rcQB").value = rosterConfig.qb_starters;
    document.getElementById("rcRB").value = rosterConfig.rb_starters;
    document.getElementById("rcWR").value = rosterConfig.wr_starters;
    document.getElementById("rcTE").value = rosterConfig.te_starters;
    document.getElementById("rcFlex").value = rosterConfig.flex_spots;
    document.getElementById("rcK").value = rosterConfig.k_starters;
    document.getElementById("rcDST").value = rosterConfig.dst_starters;
    document.getElementById("rcBench").value = rosterConfig.bench_spots;
    document.getElementById("rosterJsonText").value = JSON.stringify(rosterConfig, null, 2);

    // Apply immediately: relay roster slots and recompute so the board reflects
    // the league right away (no separate Save click needed).
    rebuildRosters();
    await recomputeStatic();

    status.style.color = "var(--good)";
    status.textContent = `✓ Loaded & applied "${data.name}" (${data.season}, ${data.total_rosters} teams, ${preset.toUpperCase()}).`;
  } catch(e){
    status.style.color = "var(--warn)";
    status.textContent = `Error: ${e.message}`;
  }
};
