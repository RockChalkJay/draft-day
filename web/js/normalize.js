// ============================ Normalization ============================
function normalize(p){
  return {
    id: p.player_id, name: p.player_name, position: p.position, team: p.team,
    bye: num(p.fantasypros_ecr_bye), ecr: num(p.fantasypros_ecr_rank_ecr),
    ecr_vs_adp: num(p.ecr_vs_adp), adp: num(p.adp), pos_rank: num(p.pos_rank),
    live_auction_value: num(p.live_auction_value),
    worth: null, value: null, bargain: null, tier: null,
    target_share: num(p.target_share), team_total: num(p.team_total),
    injury_risk: p.injury_risk ?? "",
    drafted: false, bid: null,
  };
}
function reindex(){ byId = new Map(players.map(p => [p.id, p])); }
