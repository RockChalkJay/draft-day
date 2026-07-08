// ============================ Formatting helpers ============================
function num(x){ return (x===null || x===undefined || Number.isNaN(x)) ? null : Number(x); }
function money(w){ return w==null ? "–" : "$"+w; }
function pct(x){ return x==null ? "–" : Math.round(x*100)+"%"; }
