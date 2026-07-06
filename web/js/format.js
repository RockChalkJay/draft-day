// ============================ Formatting helpers ============================
function num(x){ return (x===null || x===undefined || Number.isNaN(x)) ? null : Number(x); }
function money(w){ return w==null ? "–" : "$"+w; }
function f2(x){ return x==null ? "–" : Number(x).toFixed(2); }
function ri(x){ return x==null ? "–" : Math.round(x); }
function pct(x){ return x==null ? "–" : Math.round(x*100)+"%"; }
