// ============================ API helpers ============================
async function apiGet(path){ const r = await fetch(path); if(!r.ok) throw new Error(path+" → "+r.status); return r.json(); }
async function apiPost(path, body){
  const r = await fetch(path, {method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify(body)});
  if(!r.ok) throw new Error(path+" → "+r.status);
  return r.json();
}
let statusBase = "";  // persistent line (data source) shown whenever no transient status is active
function setStatus(t){ document.getElementById("loadStatus").textContent = t || statusBase; }
function toast(msg){ const el=document.getElementById("toast"); el.textContent=msg; el.style.display="block"; setTimeout(()=>el.style.display="none", 3200); }
