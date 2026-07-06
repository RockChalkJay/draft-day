// ============================ Board: suggestions ============================
function renderTopOverall(){
  const row = document.getElementById("topOverallRow");
  row.innerHTML = "";
  const top5 = suggestable().slice().sort((a,b)=>(b.worth??-1)-(a.worth??-1)).slice(0,5);
  if(!top5.length){ row.innerHTML = `<div class="empty-hint">No players available.</div>`; return; }
  top5.forEach((p,i) => {
    const chip = document.createElement("div");
    chip.className = "chip" + (p.id===nominatedId ? " nominated" : "");
    chip.innerHTML = `<div class="rank">#${i+1}</div><div class="name">${p.name}</div><div class="meta">${p.position} · ${p.team}</div><div class="worth">${money(p.worth)}</div>`;
    chip.onclick = () => { nominatedId = p.id; renderAll(); };
    row.appendChild(chip);
  });
}
function renderBestStrip(){
  const strip = document.getElementById("bestStrip");
  strip.innerHTML = "";
  const avail = undraftedPlayers();
  SUGGESTION_POSITIONS.forEach(pos => {
    const top3 = avail.filter(p => p.position===pos).sort((a,b)=>(b.worth??-1)-(a.worth??-1)).slice(0,3);
    if(!top3.length) return;
    const card = document.createElement("div");
    card.className = "best-card";
    card.innerHTML = `<div class="pos">${pos}</div>` + top3.map(p =>
      `<div class="row" data-id="${p.id}"><span class="name">${p.name}</span><span class="worth">${money(p.worth)}</span></div>`).join("");
    card.querySelectorAll(".row").forEach(r => r.onclick = () => { nominatedId = r.dataset.id; renderAll(); });
    strip.appendChild(card);
  });
}
function renderNeedStrip(){
  const strip = document.getElementById("needStrip");
  strip.innerHTML = "";
  const needed = myNeededPositions().filter(pos => SUGGESTION_POSITIONS.includes(pos));
  if(!needed.length){ strip.innerHTML = `<div class="empty-hint">No open starter slots right now — nothing to suggest.</div>`; return; }
  const avail = undraftedPlayers();
  needed.forEach(pos => {
    const candidates = avail.filter(p => p.position===pos);
    if(!candidates.length) return;
    const best = candidates.reduce((a,b)=>(b.worth??-1)>(a.worth??-1)?b:a);
    const card = document.createElement("div");
    card.className = "need-card" + (best.id===nominatedId ? " nominated" : "");
    card.innerHTML = `<div class="pos">${pos} (open starter slot)</div><div class="name">${best.name}</div><div class="worth">${money(best.worth)}</div>`;
    card.onclick = () => { nominatedId = best.id; renderAll(); };
    strip.appendChild(card);
  });
}

// ============================ Board: nominate / record pick ============================
function renderNominateBar(){
  const bar = document.getElementById("nominateBar");
  bar.innerHTML = "";
  const select = document.createElement("select");
  select.innerHTML = `<option value="">— search/select a player —</option>` +
    undraftedPlayers().sort((a,b)=>(b.worth??-1)-(a.worth??-1)).map(p =>
      `<option value="${p.id}" ${p.id===nominatedId?"selected":""}>${p.name} (${p.position})</option>`).join("");
  select.onchange = () => { nominatedId = select.value || null; renderAll(); };

  const nomField = document.createElement("div"); nomField.className="field";
  nomField.innerHTML = `<label>Nominate</label>`; nomField.appendChild(select);

  const bidField = document.createElement("div"); bidField.className="field";
  bidField.innerHTML = `<label>Winning bid</label><input type="number" id="bidInput" min="1" value="1">`;

  const teamField = document.createElement("div"); teamField.className="field";
  teamField.innerHTML = `<label>Winning team</label><select id="teamSelect">` +
    teams.map(t=>`<option value="${t.id}">${t.name} ($${t.bankroll} · max $${maxBid(t)})</option>`).join("") + `</select>`;

  const recordBtn = document.createElement("button");
  recordBtn.className = "btn"; recordBtn.textContent = "Record Pick";
  recordBtn.onclick = recordPick;

  bar.appendChild(nomField);
  if(nominatedId){
    const p = byId.get(nominatedId);
    const ref = document.createElement("span"); ref.className="ref-price";
    ref.textContent = `Reference price: ${money(p.worth)}`;
    bar.appendChild(ref);
  }
  bar.appendChild(bidField);
  bar.appendChild(teamField);
  bar.appendChild(recordBtn);
}

async function recordPick(){
  if(!nominatedId){ toast("Nominate a player first."); return; }
  const bid = parseFloat(document.getElementById("bidInput").value) || 0;
  const teamId = document.getElementById("teamSelect").value;
  const team = teams.find(t=>t.id===teamId);
  const player = byId.get(nominatedId);
  if(bid < 1){ toast("Minimum bid is $1."); return; }
  const max = maxBid(team);
  if(bid > max){ toast(`${team.name} can bid at most $${max} — they must keep $1 for each other open slot.`); return; }
  const slot = findEligibleSlot(team, player.position);
  if(!slot){ toast(`Pick blocked: ${team.name} has no eligible open slot (position + BENCH full).`); return; }
  slot.playerId = player.id;
  team.bankroll -= bid;
  player.drafted = true;
  player.bid = bid;
  nominatedId = null;
  await recomputeLive();   // live valuation re-runs after the pick
}

async function undraftPlayer(playerId){
  const player = byId.get(playerId);
  if(!player) return;
  for(const team of teams){
    const slot = team.roster.find(s => s.playerId === playerId);
    if(slot){ team.bankroll += (player.bid ?? 0); slot.playerId = null; break; }
  }
  player.drafted = false; player.bid = null;
  if(nominatedId === playerId) nominatedId = null;
  await recomputeLive();
}

// ============================ Board: table ============================
function renderBoardHeader(){
  const tr = document.getElementById("boardHeaderRow");
  tr.innerHTML = "";
  COLS.forEach(c => {
    const th = document.createElement("th");
    th.textContent = c.label + (sortKey===c.key ? (sortDir===1?" ▲":" ▼") : " ↕");
    if(COLUMN_TOOLTIPS[c.key]) th.title = COLUMN_TOOLTIPS[c.key];
    if(sortKey===c.key) th.classList.add("sorted");
    th.onclick = () => { if(sortKey===c.key) sortDir*=-1; else { sortKey=c.key; sortDir=-1; } renderBoard(); };
    tr.appendChild(th);
  });
}
function renderPosFilter(){
  const bar = document.getElementById("posFilter");
  bar.innerHTML = "";
  const mk = (label, val) => {
    const btn = document.createElement("button");
    btn.className = "pos-btn" + (posFilter===val ? " active" : "");
    btn.textContent = label;
    btn.onclick = () => { posFilter = (posFilter===val ? null : val); if(val===null) posFilter=null; renderBoard(); };
    return btn;
  };
  const all = mk("All", null); all.onclick = () => { posFilter=null; renderBoard(); };
  bar.appendChild(all);
  POSITIONS.forEach(pos => bar.appendChild(mk(pos, pos)));
}
function sortVal(p, key, rankMap){
  if(key==="rank") return rankMap.get(p.id) ?? Infinity;
  if(key==="sleeper") return isSleeper(p) ? p.ecr_vs_adp : null;  // biggest gaps first
  return p[key];
}
function renderBoardBody(){
  const tbody = document.getElementById("boardBody");
  tbody.innerHTML = "";
  const rankMap = new Map();
  undraftedPlayers().slice().sort((a,b)=>(b.worth??-1)-(a.worth??-1)).forEach((p,i)=>rankMap.set(p.id,i+1));
  const ecrRankMap = new Map();
  undraftedPlayers().filter(p=>p.ecr!=null).sort((a,b)=>a.ecr-b.ecr).forEach((p,i)=>ecrRankMap.set(p.id,i+1));

  let rows = undraftedPlayers().filter(p =>
    (!posFilter || p.position===posFilter) &&
    (!searchQuery || p.name.toLowerCase().includes(searchQuery) || (p.team||"").toLowerCase().includes(searchQuery)));

  rows.sort((a,b) => {
    let av = sortVal(a, sortKey, rankMap), bv = sortVal(b, sortKey, rankMap);
    if(av==null) av = sortDir===1 ? Infinity : -Infinity;
    if(bv==null) bv = sortDir===1 ? Infinity : -Infinity;
    if(typeof av==="string") return (av>bv?1:av<bv?-1:0)*sortDir;
    return (av-bv)*sortDir;
  });

  if(!rows.length){ tbody.innerHTML = `<tr><td colspan="${COLS.length}" style="color:var(--muted);padding:14px;">No players match.</td></tr>`; return; }

  rows.forEach(p => {
    const tr = document.createElement("tr");
    if(p.id===nominatedId) tr.classList.add("selected");
    const conflict = byeConflict(p);
    if(conflict) tr.classList.add("bye-conflict");
    tr.onclick = () => { nominatedId = p.id; renderAll(); };
    const myRank = rankMap.get(p.id);
    tr.innerHTML = `
      <td style="color:var(--muted);font-size:11px;">${myRank}</td>
      <td style="color:var(--muted);font-size:12px;">${p.ecr==null?"–":p.ecr} ${ecrDivergence(p, rankMap, ecrRankMap)}</td>
      <td>${p.name}</td>
      <td style="color:var(--muted);">${p.team||"–"}</td>
      <td><span class="pill">${p.position}</span></td>
      <td style="color:var(--muted);font-size:12px;">${p.pos_rank==null?"–":p.position+Math.round(p.pos_rank)}</td>
      <td style="font-weight:600;">${money(p.worth)}</td>
      <td style="color:var(--muted);">${money(p.value)}</td>
      <td style="color:var(--muted);">${money(p.live_auction_value==null?null:Math.round(p.live_auction_value))}</td>
      <td style="color:var(--muted);font-size:12px;">${p.adp==null?"–":Number(p.adp).toFixed(1)}</td>
      <td>${adpCell(p.ecr_vs_adp)}</td>
      <td>${bargainCell(p.bargain)}</td>
      <td>${tierCell(p)}</td>
      <td class="bye">${p.bye==null?"–":p.bye}${conflict?" ⚠":""}</td>
      <td>${injuryCell(p.injury_risk)}</td>
      <td>${pct(p.target_share)}</td>
      <td>${p.team_total==null?"–":Number(p.team_total).toFixed(1)}</td>
      <td>${sleeperCell(p)}</td>`;
    tbody.appendChild(tr);
  });
}

// ============================ Board: My Roster ============================
function renderMyTeam(){
  const t = myTeam();
  const grid = document.getElementById("myRosterGrid");
  grid.innerHTML = "";
  if(!t){ grid.innerHTML = `<tr><td colspan="5" style="color:var(--muted);padding:8px;">No team.</td></tr>`; return; }
  t.roster.forEach(slot => {
    const p = slot.playerId ? byId.get(slot.playerId) : null;
    const tr = document.createElement("tr");
    if(p){
      tr.innerHTML = `<td>${slot.pos}</td><td>${p.name}</td><td class="r-bye">${p.bye==null?"":"bye "+p.bye}</td><td class="r-price">${p.bid!=null?"$"+p.bid:""}</td><td><button class="undraft-btn" title="Undo pick">↩</button></td>`;
      tr.querySelector(".undraft-btn").onclick = (e)=>{ e.stopPropagation(); undraftPlayer(p.id); };
    } else {
      tr.innerHTML = `<td>${slot.pos}</td><td class="empty-slot" colspan="4">—</td>`;
    }
    grid.appendChild(tr);
  });

  const banner = document.getElementById("nomBanner");
  if(!nominatedId){
    banner.className = "nom-banner none";
    banner.textContent = "No player currently nominated.";
  } else {
    const p = byId.get(nominatedId);
    const conflict = byeConflict(p);
    banner.className = "nom-banner" + (conflict ? " warn" : "");
    banner.textContent = conflict
      ? `⚠ ${p.name} (bye ${p.bye}) shares a bye week with a current ${p.position} starter on your roster.`
      : `Nominated: ${p.name} (${p.position}${p.bye!=null?", bye "+p.bye:""}) — no bye conflict with your starters.`;
  }
}
