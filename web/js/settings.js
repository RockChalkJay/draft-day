// ============================ Settings ============================
document.querySelectorAll(".toggle-row").forEach(row => {
  row.querySelectorAll("button").forEach(btn => {
    btn.onclick = () => {
      row.querySelectorAll("button").forEach(b => b.classList.remove("active-toggle"));
      btn.classList.add("active-toggle");
      const targets = [...row.parentElement.querySelectorAll("[id]")].filter(el => el.id.includes("-form") || el.id.includes("-json"));
      targets.forEach(el => el.style.display = "none");
      document.getElementById(btn.dataset.target).style.display = "block";
    };
  });
});
function val(id){ return document.getElementById(id).value; }
function readScoringConfig(){
  if(document.getElementById("scoring-json").style.display !== "none"){
    try { return JSON.parse(val("scoringJsonText")); }
    catch(e){ toast("Invalid scoring JSON"); throw e; }
  }
  // Form mode exposes only the common fields; merge them onto the current config
  // so imported values (yardage, etc.) aren't lost when saving from the form.
  const c = JSON.parse(JSON.stringify(scoringConfig || {}));
  delete c.preset;
  c.receiving = Object.assign({}, c.receiving, { rec: parseFloat(val("scRec")) });
  c.passing = Object.assign({}, c.passing, { td: parseFloat(val("scPassTd")), int: parseFloat(val("scInt")) });
  c.rushing = Object.assign({}, c.rushing, { td: parseFloat(val("scRushTd")) });
  return c;
}
function readRosterConfig(){
  if(document.getElementById("roster-json").style.display !== "none"){
    try { return JSON.parse(val("rosterJsonText")); }
    catch(e){ toast("Invalid roster JSON"); throw e; }
  }
  return {
    qb_starters: parseInt(val("rcQB")), rb_starters: parseInt(val("rcRB")),
    wr_starters: parseInt(val("rcWR")), te_starters: parseInt(val("rcTE")),
    flex_spots: parseInt(val("rcFlex")), k_starters: parseInt(val("rcK")),
    dst_starters: parseInt(val("rcDST")), bench_spots: parseInt(val("rcBench")),
  };
}
// Re-lay every team's roster slots to match rosterConfig. Skipped once any pick
// is recorded so a mid-draft settings change can't wipe drafted players.
function rebuildRosters(){
  if(players.some(p => p.drafted)) return false;
  const tmpl = buildRosterTemplate(rosterConfig);
  teams.forEach(t => t.roster = tmpl.map(pos => ({ pos, playerId:null })));
  return true;
}
document.getElementById("saveSettingsBtn").onclick = async () => {
  try {
    scoringConfig = readScoringConfig();
    rosterConfig = readRosterConfig();
  } catch(e){ return; }
  rebuildRosters();
  await recomputeStatic();
  toast("Settings applied — rankings recomputed.");
};
