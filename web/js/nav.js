// ============================ Nav ============================
const views = ["board","league","settings"];
const navEl = document.getElementById("nav");
views.forEach(v => {
  const b = document.createElement("button");
  b.textContent = v[0].toUpperCase()+v.slice(1);
  b.dataset.view = v;
  b.onclick = () => showView(v);
  navEl.appendChild(b);
});
function showView(v){
  views.forEach(name => document.getElementById("view-"+name).classList.toggle("active", name===v));
  [...navEl.children].forEach(b => b.classList.toggle("active", b.dataset.view===v));
  renderAll();
}
