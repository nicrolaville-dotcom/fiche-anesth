"use strict";
const $ = (s) => document.querySelector(s);
const view = $("#view"), titleEl = $("#title"), backBtn = $("#back"), sbox = $("#sbox"), q = $("#q");
let NAV = null, INDEX = null;
const enc = encodeURIComponent, dec = decodeURIComponent;
const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const fold = (s) => s.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();

async function loadNav() {
  if (!NAV) NAV = await (await fetch("data/nav.json")).json();
  return NAV;
}
async function loadIndex() {
  if (!INDEX) {
    INDEX = await (await fetch("data/search.json")).json();
    INDEX.forEach((r) => { r.f = fold(r.t + " " + r.x); r.ft = fold(r.t); });
  }
  return INDEX;
}
function findChapter(id) {
  for (const b of NAV) for (const d of b.domains) {
    const i = d.chapters.findIndex((c) => c.id === id);
    if (i >= 0) return { b, d, c: d.chapters[i], prev: d.chapters[i - 1], next: d.chapters[i + 1] };
  }
}
function setHeader(title, back) {
  titleEl.textContent = title;
  document.title = title === "Fiches" ? "Fiches anesth" : title;
  backBtn.hidden = !back;
  backBtn.dataset.to = back || "";
}

async function render() {
  const h = location.hash.slice(2); // après "#/"
  const parts = h.split("/").map(dec);
  await loadNav();
  window.scrollTo(0, 0);
  if (parts[0] === "s") return renderSearch(parts.slice(1).join("/"));
  if (parts[0] === "c" && parts[1]) return renderChapter(parts[1], parts[2]);
  sbox.hidden = false;
  if (!parts[0]) {
    setHeader("Fiches", null);
    view.innerHTML = `<div class="big">${NAV.map((b) => `<a class="tile" href="#/${enc(b.name)}">${esc(b.name)}<small>${b.domains.map((d) => esc(d.name)).join(" · ")}</small></a>`).join("")}</div>`;
    return;
  }
  const b = NAV.find((x) => x.name === parts[0]);
  if (!b) return (location.hash = "#/");
  if (!parts[1]) {
    setHeader(b.name, "#/");
    view.innerHTML = `<div class="big">${b.domains.map((d) => `<a class="tile" href="#/${enc(b.name)}/${enc(d.name)}">${esc(d.name)}<small>${d.chapters.length} chapitres</small></a>`).join("")}</div>`;
    return;
  }
  const d = b.domains.find((x) => x.name === parts[1]);
  if (!d) return (location.hash = "#/" + enc(b.name));
  setHeader(`${d.name} · ${b.name}`, "#/" + enc(b.name));
  view.innerHTML = `<ul class="list">${d.chapters.map((c) => `<li><a href="#/c/${c.id}">${esc(c.title)}</a>${c.sections.length > 1
    ? `<div class="subs">${c.sections.map((s) => `<a href="#/c/${c.id}/${s.id}">${esc(s.title)}</a>`).join("")}</div>` : ""}</li>`).join("")}</ul>`;
}

async function renderChapter(id, sec) {
  const f = findChapter(id);
  if (!f) return (location.hash = "#/");
  sbox.hidden = true;
  setHeader(f.c.title, `#/${enc(f.b.name)}/${enc(f.d.name)}`);
  view.innerHTML = `<p class="muted">Chargement…</p>`;
  let body;
  try { body = await (await fetch(`c/${id}.html`)).text(); } catch (e) { body = "<p>Hors ligne : chapitre pas encore en cache.</p>"; }
  const toc = f.c.sections.length > 1
    ? `<details class="toc"><summary>Sommaire du chapitre (${f.c.sections.length})</summary>${f.c.sections.map((s) => `<a href="#/c/${id}/${s.id}">${esc(s.title)}</a>`).join("")}</details>` : "";
  const pn = `<nav class="pn">${f.prev ? `<a href="#/c/${f.prev.id}">‹ ${esc(f.prev.title)}</a>` : "<span></span>"}${f.next ? `<a href="#/c/${f.next.id}">${esc(f.next.title)} ›</a>` : ""}</nav>`;
  view.innerHTML = `<p class="crumb">${esc(f.b.name)} › ${esc(f.d.name)}</p><h1 class="ct">${esc(f.c.title)}</h1>${toc}<article class="fiche">${body}</article>${pn}`;
  view.querySelectorAll(".fiche img").forEach((im) => im.addEventListener("click", () => zoom(im.src)));
  const hl = sessionStorage.getItem("hl"); sessionStorage.removeItem("hl");
  if (hl) highlight(view.querySelector(".fiche"), hl);
  if (sec) { const el = document.getElementById(sec); if (el) el.scrollIntoView(); }
  else if (hl) { const m = view.querySelector("mark"); if (m) m.scrollIntoView({ block: "center" }); }
}

function highlight(root, terms) {
  const ts = terms.split(" ").filter((t) => t.length > 1);
  if (!ts.length) return;
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
  const nodes = []; let n;
  while ((n = walker.nextNode())) nodes.push(n);
  nodes.forEach((node) => {
    const f = fold(node.nodeValue);
    let ranges = [];
    ts.forEach((t) => { let i = f.indexOf(t); while (i >= 0) { ranges.push([i, i + t.length]); i = f.indexOf(t, i + t.length); } });
    if (!ranges.length) return;
    ranges.sort((a, b) => a[0] - b[0]);
    const frag = document.createDocumentFragment(); let pos = 0; const v = node.nodeValue;
    ranges.forEach(([a, b]) => { if (a < pos) return; frag.append(v.slice(pos, a)); const m = document.createElement("mark"); m.textContent = v.slice(a, b); frag.append(m); pos = b; });
    frag.append(v.slice(pos)); node.replaceWith(frag);
  });
}

function zoom(src) {
  const o = document.createElement("div");
  o.className = "zoom"; o.innerHTML = `<img src="${src}" alt=""><button aria-label="Fermer">×</button>`;
  o.querySelector("button").onclick = () => o.remove();
  o.querySelector("img").onclick = (e) => e.target.classList.toggle("x2");
  document.body.append(o);
}

function snippet(x, terms) {
  const f = fold(x); let i = -1;
  for (const t of terms) { i = f.indexOf(t); if (i >= 0) break; }
  const a = Math.max(0, i - 60), s = x.slice(a, a + 180);
  let out = esc((a > 0 ? "…" : "") + s + (a + 180 < x.length ? "…" : ""));
  terms.forEach((t) => { if (t.length > 1) out = out.replace(new RegExp(`(${[...t].map((c) => "[" + c + c.toUpperCase() + "\\u00C0-\\u017F]").join("")})`, "g"), (m) => fold(m) === t ? `<mark>${m}</mark>` : m); });
  return out;
}

async function renderSearch(raw) {
  sbox.hidden = false;
  if (q.value !== raw) q.value = raw;
  setHeader("Recherche", "#/");
  const terms = fold(raw).split(/\s+/).filter(Boolean);
  if (!terms.length) { view.innerHTML = `<p class="muted">Tape un mot-clé.</p>`; return; }
  const idx = await loadIndex();
  const res = idx.filter((r) => terms.every((t) => r.f.includes(t)))
    .map((r) => ({ r, score: terms.reduce((s, t) => s + (r.ft.includes(t) ? 10 : 0) + Math.min(5, r.f.split(t).length - 1), 0) }))
    .sort((a, b) => b.score - a.score).slice(0, 80);
  if (!res.length) { view.innerHTML = `<p class="muted">Aucun résultat pour « ${esc(raw)} ».</p>`; return; }
  view.innerHTML = `<p class="muted">${res.length}${res.length === 80 ? "+" : ""} résultat(s)</p><ul class="list res">${res.map(({ r }) => {
    const f = findChapter(r.c);
    const label = r.s ? `${f.c.title} › ${r.t}` : f.c.title;
    return `<li><a href="#/c/${r.c}${r.s ? "/" + r.s : ""}" data-hl="${esc(terms.join(" "))}"><span>${esc(label)}</span><small class="where">${esc(f.b.name)} › ${esc(f.d.name)}</small><small>${snippet(r.x, terms)}</small></a></li>`;
  }).join("")}</ul>`;
  view.querySelectorAll("a[data-hl]").forEach((a) => a.addEventListener("click", () => sessionStorage.setItem("hl", a.dataset.hl)));
}

let t;
q.addEventListener("input", () => { clearTimeout(t); t = setTimeout(() => { const v = q.value.trim(); history.replaceState(null, "", v ? "#/s/" + enc(v) : "#/"); render(); }, 200); });
q.addEventListener("focus", () => loadIndex());
$("#sbtn").addEventListener("click", () => { sbox.hidden = false; q.focus(); });
backBtn.addEventListener("click", () => { location.hash = backBtn.dataset.to || "#/"; });
window.addEventListener("hashchange", render);
if (!location.hash) history.replaceState(null, "", "#/");
render();

if ("serviceWorker" in navigator) {
  navigator.serviceWorker.register("sw.js").then((reg) => {
    const show = (w) => { $("#update").hidden = false; $("#reload").onclick = () => w.postMessage("skip"); };
    if (reg.waiting && navigator.serviceWorker.controller) show(reg.waiting);
    reg.addEventListener("updatefound", () => {
      const w = reg.installing;
      w.addEventListener("statechange", () => { if (w.state === "installed" && navigator.serviceWorker.controller) show(w); });
    });
    document.addEventListener("visibilitychange", () => { if (!document.hidden) reg.update(); });
  });
  let reloaded = false;
  navigator.serviceWorker.addEventListener("controllerchange", () => { if (!reloaded) { reloaded = true; location.reload(); } });
}
