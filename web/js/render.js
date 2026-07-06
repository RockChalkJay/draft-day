// ============================ Render all ============================
function renderBoard(){ renderBoardHeader(); renderPosFilter(); renderBoardBody(); }
function renderAll(){
  document.getElementById("myBankroll").textContent = myTeam() ? `$${myTeam().bankroll}` : "$0";
  document.getElementById("myMaxBid").textContent = myTeam() ? `$${maxBid(myTeam())}` : "$0";
  const infEl = document.getElementById("inflation");
  const market = inflation * marketHeat;  // effective price level Worth is computed at
  infEl.textContent = market.toFixed(2) + "×";
  infEl.style.color = market > 1.03 ? "var(--warn)" : market < 0.97 ? "var(--good)" : "var(--accent)";
  infEl.title = `Cash-vs-board inflation ${inflation.toFixed(2)}× · draft-phase decay ${marketHeat.toFixed(2)}× (prices sag as rosters fill)`;
  renderBoard(); renderTopOverall(); renderBestStrip(); renderNeedStrip();
  renderNominateBar(); renderMyTeam(); renderLeague();
}
document.getElementById("boardSearch").addEventListener("input", e => { searchQuery = e.target.value.trim().toLowerCase(); renderBoard(); });
