// ============================ Helpers ============================
function myTeam(){ return teams.find(t => t.id === myTeamId); }
function undraftedPlayers(){ return players.filter(p => !p.drafted); }
// Standard auction rule: a team must keep $1 for every other open slot, so the
// most it can put on one player is bankroll - (open slots - 1).
function maxBid(team){
  const open = team.roster.filter(s => !s.playerId).length;
  return Math.max(0, team.bankroll - Math.max(0, open - 1));
}
function suggestable(){ return undraftedPlayers().filter(p => SUGGESTION_POSITIONS.includes(p.position)); }
function myStarterPositions(){
  const t = myTeam(); if(!t) return {};
  const map = {};
  t.roster.forEach(slot => {
    if(slot.pos !== "BENCH" && slot.playerId){
      const p = byId.get(slot.playerId);
      if(p) (map[p.position] ||= []).push(p);
    }
  });
  return map;
}
function byeConflict(player){
  if(player.bye == null) return false;
  const starters = myStarterPositions()[player.position] || [];
  return starters.some(s => s.bye === player.bye);
}
function myNeededPositions(){
  const t = myTeam(); if(!t) return [];
  const empty = new Set(t.roster.filter(s => s.pos !== "BENCH" && !s.playerId).map(s => s.pos));
  if(empty.has("FLEX")){ empty.delete("FLEX"); ["RB","WR","TE"].forEach(p => empty.add(p)); }
  return [...empty];
}
function findEligibleSlot(team, pos){
  let slot = team.roster.find(s => s.pos === pos && !s.playerId);
  if(slot) return slot;
  if(["RB","WR","TE"].includes(pos)){
    slot = team.roster.find(s => s.pos === "FLEX" && !s.playerId);
    if(slot) return slot;
  }
  return team.roster.find(s => s.pos === "BENCH" && !s.playerId) || null;
}
