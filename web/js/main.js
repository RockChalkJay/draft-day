// ============================ Boot ============================
async function init(){
  const tmpl = buildRosterTemplate(rosterConfig);
  teams = DEFAULT_TEAM_NAMES.map((name,i) => ({ id:"t"+i, name, bankroll:200, roster: tmpl.map(pos=>({pos, playerId:null})) }));
  myTeamId = teams[0].id;
  showView("board");
  try {
    setStatus("Loading players…");
    const data = await apiGet("/api/players");
    rawPlayers = data.players;
    players = rawPlayers.map(normalize);
    reindex();
    await recomputeStatic();   // preview values before a draft is formally started
    // Always show where the board's data came from — drafting off the bundled
    // demo sample (or a stale cache) without realizing it is the silent failure
    // mode that matters most on draft day.
    statusBase = `${data.count} players · ${data.source}`;
    const el = document.getElementById("loadStatus");
    if(data.source === "sample"){ el.style.color = "var(--warn)"; el.title = "Offline demo data — not real projections. Check your network and reload, or GET /api/players?refresh=true."; }
    setStatus("");
  } catch(e){
    setStatus("");
    toast("Failed to load: " + e.message);
  }
}
init();
