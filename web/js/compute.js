// ============================ Compute (static + live) ============================
function leagueStatePayload(){
  return {
    teams: teams.map(t => ({ team_id:t.id, bankroll:t.bankroll,
      roster: t.roster.map(s => ({ pos:s.pos, player_id:s.playerId })) })),
    drafted_player_ids: players.filter(p => p.drafted).map(p => p.id),
    starting_bankroll: startingBankroll,
  };
}

async function recomputeStatic(){
  setStatus("Computing rankings…");
  staticResult = await apiPost("/api/rankings/static", {
    players: rawPlayers,
    scoring_config: scoringConfig,
    replacement_config: rosterConfig,
    num_teams: teams.length || 12,
    num_tiers: numTiers,
  });
  await recomputeLive();
}

async function recomputeLive(){
  if(!staticResult) return;
  setStatus("Updating values…");
  const live = await apiPost("/api/rankings/live", {
    static_result: staticResult,
    league_state: leagueStatePayload(),
  });
  const liveById = new Map(live.players.map(p => [p.player_id, p]));
  for(const pl of players){
    const lp = liveById.get(pl.id);
    if(lp){ pl.tier=num(lp.tier); pl.worth=num(lp.worth); pl.value=num(lp.value); pl.bargain=num(lp.bargain); pl.tcm=num(lp.tcm); }
  }
  inflation = live.inflation ?? 1; marketHeat = live.market_heat ?? 1;
  maxTierByPos = {};
  players.forEach(p => { if(p.tier) maxTierByPos[p.position] = Math.max(maxTierByPos[p.position] || 1, p.tier); });
  setStatus("");
  renderAll();
}
