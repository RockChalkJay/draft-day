// ============================ League ============================
function renderLeague(){
  const grid = document.getElementById("leagueGrid");
  grid.innerHTML = "";
  if(!teams.length){ grid.innerHTML = `<div style="color:var(--muted)">No league yet.</div>`; return; }
  teams.forEach(t => {
    const card = document.createElement("div");
    card.className = "team-card";
    const items = t.roster.map(slot => {
      const p = slot.playerId ? byId.get(slot.playerId) : null;
      const price = p?.bid != null ? `$${p.bid}` : "";
      return `<li class="${p?"filled":""}"><span class="lc-pos">${slot.pos}</span><span class="lc-name">${p?p.name:"—"}</span><span class="lc-price">${price}</span></li>`;
    }).join("");
    card.innerHTML = `<h3>${t.name}${t.id===myTeamId?" (You)":""}</h3><div class="bankroll">$${t.bankroll} remaining</div><ul>${items}</ul>`;
    grid.appendChild(card);
  });
}
