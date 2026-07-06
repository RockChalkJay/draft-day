// ============================ Start Draft modal ============================
const modalOverlay = document.getElementById("modalOverlay");
const teamRowsEl = document.getElementById("teamRows");
function addTeamRow(name=""){
  const row = document.createElement("div"); row.className = "team-row";
  const input = document.createElement("input"); input.value = name; input.placeholder = "Team name";
  const rm = document.createElement("button"); rm.className = "btn secondary"; rm.textContent = "×";
  rm.onclick = () => row.remove();
  row.appendChild(input); row.appendChild(rm); teamRowsEl.appendChild(row);
}
document.getElementById("startDraftBtn").onclick = () => {
  teamRowsEl.innerHTML = "";
  (teams.length ? teams.map(t=>t.name) : DEFAULT_TEAM_NAMES).forEach(n => addTeamRow(n));
  document.getElementById("modalNumTiers").value = numTiers;
  modalOverlay.style.display = "flex";
};
document.getElementById("cancelModalBtn").onclick = () => modalOverlay.style.display = "none";
document.getElementById("addTeamBtn").onclick = () => addTeamRow("");
document.getElementById("confirmStartBtn").onclick = async () => {
  const names = [...teamRowsEl.querySelectorAll("input")].map(i => i.value.trim()).filter(Boolean);
  if(!names.length){ toast("Add at least one team."); return; }
  const bankroll = parseFloat(document.getElementById("modalBankroll").value) || 200;
  startingBankroll = bankroll;
  numTiers = parseInt(document.getElementById("modalNumTiers").value) || 5;
  const tmpl = buildRosterTemplate(rosterConfig);
  teams = names.map((name,i) => ({ id:"t"+i, name, bankroll, roster: tmpl.map(pos=>({pos, playerId:null})) }));
  myTeamId = teams[0].id;
  draftStarted = true;
  modalOverlay.style.display = "none";
  await recomputeStatic();   // num_teams / num_tiers may have changed
};
