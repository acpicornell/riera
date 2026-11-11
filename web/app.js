// Riera Balears — static web, vanilla JS.
// One fetch of data.json, then everything happens in memory.

const state = {
  entries: [],
  filtered: [],
  search: "",
  island: "",
  municipality: "",
  type: "",
  vol: "",
  conf: "",
  sort_col: "title",
  sort_dir: "asc",
};

const COLS = ["title", "place_type", "island", "municipality",
              "vol", "page", "confidence"];

function esc(s) {
  if (s == null) return "";
  return String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;")
    .replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#39;");
}
function $(id) { return document.getElementById(id); }
function fmt(n) { return Number(n).toLocaleString("ca-ES"); }
function norm(s) {
  if (!s) return "";
  return s.toString().toLowerCase()
    .normalize("NFD").replace(/[̀-ͯ]/g, "");
}

// === TABS ===
function gotoTab(t) {
  document.querySelectorAll(".tabs .tab").forEach(b =>
    b.classList.toggle("active", b.dataset.toptab === t));
  document.querySelectorAll(".tab-content").forEach(sec =>
    sec.classList.toggle("active", sec.dataset.toptab === t));
  if (t === "stats") renderStats();
  if (t === "demografia") renderDemografia();
  if (t === "map") renderMap();
  window.scrollTo({ top: 0, behavior: "smooth" });
}

function initTabs() {
  document.querySelectorAll(".tabs .tab").forEach(btn => {
    btn.addEventListener("click", () => gotoTab(btn.dataset.toptab));
  });
  document.querySelectorAll("[data-goto]").forEach(el => {
    el.addEventListener("click", ev => {
      ev.preventDefault();
      gotoTab(el.dataset.goto);
      window.scrollTo({ top: 0, behavior: "smooth" });
    });
  });
}

// === FILTERS ===
const FILTER_DEFS = [
  { id: "f-island",       stateKey: "island",       field: "island",       allLabel: "— Totes —" },
  { id: "f-municipality", stateKey: "municipality", field: "municipality", allLabel: "— Tots —" },
  { id: "f-type",         stateKey: "type",         field: "place_type",   allLabel: "— Tots —" },
  { id: "f-vol",          stateKey: "vol",          field: "vol",          allLabel: "— Tots —" },
  { id: "f-conf",         stateKey: "conf",         field: "confidence",   allLabel: "— Totes —" },
];

function matchesExcept(e, exceptKey) {
  for (const f of FILTER_DEFS) {
    if (f.stateKey === exceptKey) continue;
    const v = state[f.stateKey];
    if (v && e[f.field] !== v) return false;
  }
  if (state.search) {
    const hay = norm((e.title || "") + " " + (e.description || ""));
    if (!hay.includes(norm(state.search))) return false;
  }
  return true;
}

function refillFilters() {
  for (const f of FILTER_DEFS) {
    const counts = new Map();
    for (const e of state.entries) {
      if (!matchesExcept(e, f.stateKey)) continue;
      const v = e[f.field];
      if (v == null || v === "") continue;
      counts.set(v, (counts.get(v) || 0) + 1);
    }
    const arr = [...counts.entries()];
    if (f.id === "f-vol" || f.id === "f-municipality") {
      arr.sort((a, b) => a[0].localeCompare(b[0], "ca", { numeric: true }));
    } else if (f.id === "f-conf") {
      const order = { high: 0, medium: 1, low: 2 };
      arr.sort((a, b) => (order[a[0]] ?? 9) - (order[b[0]] ?? 9));
    } else {
      arr.sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]));
    }
    const cur = state[f.stateKey];
    if (cur && !counts.has(cur)) state[f.stateKey] = "";

    const labelMap = f.id === "f-conf"
      ? { high: "Alta", medium: "Mitjana", low: "Baixa" }
      : null;
    const opts = arr.map(([v, n]) => {
      const label = labelMap ? (labelMap[v] || v) : v;
      return `<option value="${esc(v)}">${esc(label)} (${n})</option>`;
    }).join("");
    const sel = $(f.id);
    sel.innerHTML = `<option value="">${f.allLabel}</option>` + opts;
    sel.value = state[f.stateKey] || "";
  }
}

function applyFilters() {
  state.filtered = state.entries.filter(e => matchesExcept(e, null));
  sortFiltered();
}

function sortFiltered() {
  const k = state.sort_col;
  const dir = state.sort_dir === "desc" ? -1 : 1;
  state.filtered.sort((a, b) => {
    let av = a[k], bv = b[k];
    if (av == null && bv == null) return 0;
    if (av == null) return 1;
    if (bv == null) return -1;
    if (typeof av === "number" && typeof bv === "number") return (av - bv) * dir;
    return String(av).localeCompare(String(bv), "ca", { numeric: true }) * dir;
  });
}

// === TABLE ===
function renderTable() {
  applyFilters();
  const tbody = $("tbody-riera");
  const total = state.filtered.length;
  $("count").textContent = `${fmt(total)} entrades`;
  if (!total) {
    tbody.innerHTML = `<tr><td colspan="9" class="empty">No s'han trobat entrades que satisfacin els filtres seleccionats.</td></tr>`;
    return;
  }
  const slice = state.filtered.slice(0, 500);
  const dot = c => c === "high" ? "●" : c === "medium" ? "◐" : c === "low" ? "○" : "—";
  tbody.innerHTML = slice.map(e => {
    const volPage = e.bdcyl_url
      ? `<a href="${esc(e.bdcyl_url)}" target="_blank" rel="noopener" class="bdcyl-link" title="Obre el volum sencer a BDCyL">${esc(e.vol)}/${esc(e.page)} ↗</a>`
      : `${esc(e.vol)}/${esc(e.page)}`;
    return `<tr data-id="${e.id}" class="riera-row">
      <td><strong>${esc(e.title)}</strong></td>
      <td>${esc(e.place_type || "—")}</td>
      <td>${esc(e.island || "—")}</td>
      <td>${esc(e.municipality || "—")}</td>
      <td>${volPage}</td>
      <td class="conf-${esc(e.confidence || "")}">${dot(e.confidence)}</td>
    </tr>`;
  }).join("") + (total > 500
    ? `<tr><td colspan="6" class="empty">Es visualitzen 500 de ${fmt(total)} entrades. Refineu els filtres per restringir el resultat.</td></tr>`
    : "");
  tbody.querySelectorAll("tr.riera-row").forEach(tr =>
    tr.addEventListener("click", ev => {
      if (ev.target.closest("a")) return;
      toggleExpand(tr);
    }));
}

function toggleExpand(tr) {
  const next = tr.nextElementSibling;
  if (next && next.classList.contains("riera-expand")) {
    next.remove(); tr.classList.remove("expanded"); return;
  }
  document.querySelectorAll(".riera-expand").forEach(el => el.remove());
  document.querySelectorAll(".riera-row.expanded").forEach(el => el.classList.remove("expanded"));
  const id = Number(tr.dataset.id);
  const e = state.entries.find(x => x.id === id);
  if (!e) return;

  let statsHtml = "";
  if (e.stats && typeof e.stats === "object") {
    const items = Object.entries(e.stats).filter(([_, v]) => v != null && v !== "");
    if (items.length) {
      statsHtml = `<div class="entry-stats"><strong>Estadístiques:</strong> ` +
        items.map(([k, v]) =>
          `<span class="stat-pill">${esc(k)}: <strong>${esc(typeof v === "number" ? fmt(v) : v)}</strong></span>`
        ).join(" ") + `</div>`;
    }
  }
  let crefsHtml = "";
  if (e.cross_references && e.cross_references.length) {
    crefsHtml = `<div class="entry-crefs"><strong>Referències creuades:</strong> ` +
      e.cross_references.map(c => `<code>${esc(c)}</code>`).join(", ") + `</div>`;
  }
  let ocrNoteHtml = "";
  if (e.ocr_note) {
    ocrNoteHtml = `<details class="entry-ocr-note"><summary>Nota editorial / OCR</summary>` +
      `<p>${esc(e.ocr_note)}</p></details>`;
  }
  // Riera's nine-section template: render only the sections that
  // were populated by the LLM extraction.
  const SECTION_LABELS = [
    ["org_judicial",       "Organització judicial"],
    ["org_civil",          "Organització civil"],
    ["org_militar",        "Organització militar"],
    ["org_economica",      "Organització econòmica"],
    ["org_eclesiastica",   "Organització eclesiàstica"],
    ["servicio_publico",   "Servei públic"],
    ["obras_publicas",     "Obres públiques i comunicacions"],
    ["instruccion_publica","Instrucció pública"],
    ["poblacion",          "Població"],
    ["industria",          "Indústria"],
    ["geografia",          "Situació geogràfica i topogràfica"],
    ["historia",           "Història i biografia"],
  ];
  const toParas = (s) => esc(s).split(/\n{2,}/).map(p => `<p>${p.replace(/\n/g, " ")}</p>`).join("");
  const sectionsHtml = SECTION_LABELS
    .filter(([k, _]) => e[k])
    .map(([k, lbl]) => `<div class="riera-section"><h4>${lbl}</h4>${toParas(e[k])}</div>`)
    .join("");
  const descHtml = e.description
    ? `<div class="riera-section riera-desc">${toParas(e.description)}</div>` : "";

  const exp = document.createElement("tr");
  exp.className = "riera-expand";
  exp.innerHTML = `<td colspan="6">
    <div class="riera-article">
      ${descHtml}
      ${sectionsHtml}
      ${statsHtml}
      ${crefsHtml}
      ${ocrNoteHtml}
      <p class="riera-source">
        <span>Tom ${esc(e.vol)} · pàgina PDF ${esc(e.page)}</span>
        ${e.bdcyl_url ? `· <a href="${esc(e.bdcyl_url)}" target="_blank" rel="noopener">Veure volum a Biblioteca Digital de Castella i Lleó →</a>` : ""}
      </p>
    </div>
  </td>`;
  tr.classList.add("expanded");
  tr.insertAdjacentElement("afterend", exp);
}

function initSort() {
  document.querySelectorAll("#table-riera th").forEach((th, i) => {
    const col = COLS[i];
    if (!col) return;
    th.classList.add("sortable");
    th.addEventListener("click", () => {
      if (state.sort_col === col) state.sort_dir = state.sort_dir === "asc" ? "desc" : "asc";
      else { state.sort_col = col; state.sort_dir = "asc"; }
      document.querySelectorAll("#table-riera th").forEach(x => x.classList.remove("sort-asc", "sort-desc"));
      th.classList.add(`sort-${state.sort_dir}`);
      renderTable();
    });
  });
}

function update() { refillFilters(); renderTable(); }

function bindFilters() {
  let t;
  $("f-search").addEventListener("input", e => {
    clearTimeout(t);
    t = setTimeout(() => { state.search = e.target.value.trim(); update(); }, 180);
  });
  const sel = (id, key) => $(id).addEventListener("change", e => { state[key] = e.target.value; update(); });
  sel("f-island", "island");
  sel("f-municipality", "municipality"); sel("f-type", "type");
  sel("f-vol", "vol"); sel("f-conf", "conf");
  $("f-clear").addEventListener("click", () => {
    Object.assign(state, {
      search: "", island: "",
      municipality: "", type: "", vol: "", conf: "",
    });
    $("f-search").value = "";
    update();
  });
  $("f-export").addEventListener("click", exportCSV);
}

function exportCSV() {
  const fields = ["vol", "page", "title", "place_type", "island",
                  "municipality", "confidence", "description"];
  const cell = v => {
    if (v == null) return "";
    const s = String(v);
    return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
  };
  const lines = [fields.join(",")];
  for (const e of state.filtered) lines.push(fields.map(f => cell(e[f])).join(","));
  const blob = new Blob([lines.join("\n")], { type: "text/csv;charset=utf-8" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = `riera_balears_${state.filtered.length}.csv`;
  a.click();
  URL.revokeObjectURL(a.href);
}

// === HOME / INICI ===
function renderHome() {
  const total = state.entries.length;
  $("home-stat-entries").textContent = fmt(total);
  // Distinct tomos with entries.
  const vols = new Set(state.entries.map(e => e.vol).filter(Boolean));
  $("home-stat-tomos-done").textContent = vols.size;
  // Top place type.
  const typeCounts = new Map();
  for (const e of state.entries) {
    if (!e.place_type) continue;
    typeCounts.set(e.place_type, (typeCounts.get(e.place_type) || 0) + 1);
  }
  const topType = [...typeCounts.entries()].sort((a, b) => b[1] - a[1])[0];
  if (topType) {
    $("home-stat-toptype").textContent = fmt(topType[1]);
    $("home-stat-toptype-label").textContent = `${topType[0]} (tipus més freqüent)`;
  }

  // Per-island cards.
  const islandCounts = new Map();
  for (const e of state.entries) {
    if (!e.island) continue;
    islandCounts.set(e.island, (islandCounts.get(e.island) || 0) + 1);
  }
  const setIsland = (id, key) => {
    const el = $(id);
    if (el) el.textContent = fmt(islandCounts.get(key) || 0);
  };
  setIsland("home-src-mallorca", "Mallorca");
  setIsland("home-src-menorca", "Menorca");
  setIsland("home-src-ibiza", "Ibiza");
  setIsland("home-src-formentera", "Formentera");
  setIsland("home-src-cabrera", "Cabrera");

  // Featured entry — pick a random high-confidence one for the splash.
  const highs = state.entries.filter(e => e.confidence === "high" && e.description);
  const featured = highs.length
    ? highs[Math.floor(Math.random() * highs.length)]
    : state.entries.find(e => e.description);
  if (featured) {
    const card = $("home-featured");
    if (card) card.hidden = false;
    $("featured-title").textContent = featured.title;
    const meta = [
      featured.place_type, featured.island,
      featured.municipality && `Municipi: ${featured.municipality}`,
      `Tom ${featured.vol} · pàg. ${featured.page || "?"}`,
    ].filter(Boolean).join(" · ");
    $("featured-meta").textContent = meta;
    const txt = featured.description || featured.geografia || featured.poblacion || "";
    const excerpt = txt.length > 320 ? txt.slice(0, 320).trimEnd() + "…" : txt;
    $("featured-excerpt").textContent = excerpt;
    $("featured-open").addEventListener("click", () => {
      gotoTab("explore");
      requestAnimationFrame(() => {
        const tr = document.querySelector(`tr[data-id="${featured.id}"]`);
        if (tr) {
          tr.scrollIntoView({ behavior: "smooth", block: "center" });
          toggleExpand(tr);
        }
      });
    });
  }
}

// === EXPLORE STATS BAR ===
function renderStatsBar() {
  $("stat-text").textContent = fmt(state.entries.length);
  $("stat-volumes").textContent = new Set(
    state.entries.map(e => e.vol).filter(Boolean)
  ).size;
  $("stat-islands").textContent = new Set(
    state.entries.map(e => e.island).filter(Boolean)
  ).size;
  $("stat-types").textContent = new Set(
    state.entries.map(e => e.place_type).filter(Boolean)
  ).size;
}

// === BOOTSTRAP ===
async function boot() {
  initTabs();
  initSort();
  bindFilters();
  let payload;
  try {
    const r = await fetch("data.json?v=29");
    payload = await r.json();
  } catch (e) {
    console.error(e);
    $("tbody-riera").innerHTML =
      `<tr><td colspan="9" class="empty">Error en la càrrega de data.json.</td></tr>`;
    return;
  }
  state.entries = payload.entries || [];
  renderHome();
  renderStatsBar();
  update();
}

// ===========================================================================
// === ESTADÍSTIQUES TAB (corpus structure) ==================================
// ===========================================================================

let corpusStatsRendered = false;

const VOL_LABEL = {
  "01": "I", "02": "II", "03": "III", "04": "IV", "05": "V",  "06": "VI",
  "07": "VII", "08": "VIII", "09": "IX", "10": "X", "11": "XI", "12": "XII",
};

function renderStats() {
  if (corpusStatsRendered) return;
  corpusStatsRendered = true;

  const total = state.entries.length;
  const totalEl = $("stats-total-entries");
  if (totalEl) totalEl.textContent = fmt(total);

  const count = key => {
    const m = new Map();
    for (const e of state.entries) {
      const v = e[key];
      if (v == null || v === "") continue;
      m.set(v, (m.get(v) || 0) + 1);
    }
    return [...m.entries()].sort((a, b) => b[1] - a[1]);
  };
  const draw = (id, rows, opts = {}) => {
    const host = $(id);
    if (!host) return;
    host.innerHTML = rows.length ? svgBars(rows, opts) : '<p class="empty">—</p>';
  };

  draw("stat-by-island", count("island"),
       { barH: 22, gap: 10, labelW: 130 });
  draw("stat-by-type",   count("place_type"),
       { labelW: 160 });

  // Volume coverage in natural tom order (01–12), not by count;
  // re-labelled with the Roman numeral so it matches the rest of the UI.
  const byVol = count("vol")
    .sort((a, b) => a[0].localeCompare(b[0], "ca", { numeric: true }))
    .map(([v, n]) => [`Tom ${VOL_LABEL[v] || v}`, n]);
  draw("stat-by-vol", byVol, { labelW: 110 });

  // Top municipalities: a tag-cloud per municipality (shows the actual
  // dependent entry titles, not just a count). Only municipalities with
  // 2+ entries — singletons add no structural info.
  const muniMap = new Map();
  for (const e of state.entries) {
    const m = e.municipality;
    if (!m) continue;
    if (!muniMap.has(m)) muniMap.set(m, { titles: [], island: e.island });
    muniMap.get(m).titles.push(e.title);
  }
  const muniGroups = [...muniMap.entries()]
    .filter(([_, g]) => g.titles.length >= 2)
    .sort((a, b) => b[1].titles.length - a[1].titles.length);
  $("stat-by-muni").innerHTML = renderMunicipalityTags(muniGroups);

  // Confidence breakdown.
  const confLabel = { high: "Alta", medium: "Mitjana", low: "Baixa" };
  const confOrder = ["high", "medium", "low"];
  const confRows = confOrder
    .map(k => [confLabel[k], state.entries.filter(e => e.confidence === k).length])
    .filter(r => r[1] > 0);
  draw("stat-by-conf", confRows, { barH: 22, gap: 10, labelW: 130 });
}

// ===========================================================================
// === DEMOGRAFIA TAB ========================================================
// ===========================================================================

let demoRendered = false;

// Inline horizontal-bar chart. `rows` is [[label, value, sub?], ...]
// sorted descending. `fmtVal` formats the numeric value for display.
function svgBars(rows, opts = {}) {
  // Drop rows whose value isn't a finite number — one stray "11,???" would
  // otherwise NaN-poison Math.max and collapse every bar to width 0.
  rows = rows.filter(r => typeof r[1] === "number" && isFinite(r[1]));
  if (!rows.length) return '<p class="empty">Sense dades.</p>';
  const fmtVal = opts.fmt || fmt;
  const colour = opts.colour || "var(--accent)";
  const labelW = opts.labelW ?? 160;
  const barH = opts.barH ?? 18;
  const gap = opts.gap ?? 6;
  const valueW = opts.valueW ?? 110;
  const width = 720;
  const innerW = width - labelW - valueW - 20;
  const max = Math.max(...rows.map(r => r[1])) || 1;
  const height = rows.length * (barH + gap);
  const lines = rows.map((r, i) => {
    const [label, val, sub] = r;
    const w = max > 0 ? Math.max(1, (val / max) * innerW) : 0;
    const y = i * (barH + gap);
    return (
      `<g transform="translate(0,${y})">` +
      `<text x="${labelW - 6}" y="${barH * 0.72}" text-anchor="end" class="bar-label">${esc(label)}</text>` +
      `<rect x="${labelW}" y="0" width="${w}" height="${barH}" rx="2" fill="${colour}"/>` +
      `<text x="${labelW + w + 6}" y="${barH * 0.72}" class="bar-value">${esc(fmtVal(val))}${sub ? ` <tspan class="bar-sub">${esc(sub)}</tspan>` : ""}</text>` +
      `</g>`
    );
  }).join("");
  return `<svg viewBox="0 0 ${width} ${height}" class="bars-svg" preserveAspectRatio="xMinYMin meet" role="img">${lines}</svg>`;
}

function statsOf(e) {
  return (e.stats && typeof e.stats === "object") ? e.stats : null;
}

// Exclude island/province aggregates ("ISLA DE MALLORCA", "BALEARES")
// from per-entry charts: their habitantes figures are the sum of all
// the entries in our table — they'd dwarf everything.
function isIslandAggregate(e) {
  return e.place_type === "isla" || e.place_type === "islas"
      || e.island === "Baleares";
}

function isPlaceEntry(e) {
  return !isIslandAggregate(e);
}

function renderDemografia() {
  if (demoRendered) return;
  demoRendered = true;

  const total = state.entries.length;
  const numOf = (e, k) => {
    const v = statsOf(e)?.[k];
    return typeof v === "number" && isFinite(v) ? v : null;
  };
  const withHab = state.entries.filter(e => isPlaceEntry(e) && numOf(e, "habitantes") != null);
  const withEdif = state.entries.filter(e => isPlaceEntry(e) && numOf(e, "edificios") != null);

  $("stats-coverage").innerHTML =
    `<strong>Cobertura demogràfica:</strong> de ${total} entrades balears del corpus, ` +
    `${withHab.length} reporten habitants i ${withEdif.length} reporten edificis (xifres del cens del 1877). ` +
    `Els accidents geogràfics (cabos, illes, illots) i les entrades supramunicipals (Baleares, obispats) ` +
    `no tenen demografia pròpia i queden fora dels gràfics quantitatius.`;

  // === Chart 1: Top 25 by habitants ===
  const topPop = withHab
    .map(e => [
      e.title,
      statsOf(e).habitantes,
      statsOf(e).edificios ? `${fmt(statsOf(e).edificios)} edif.` : null,
    ])
    .sort((a, b) => b[1] - a[1])
    .slice(0, 25);
  $("stats-chart-top-pop").innerHTML = svgBars(topPop, { labelW: 220 });

  // === Chart 2: Composition of edificis (habitats/temporals/inhabitats) ===
  // Use 'habitados_temporalmente' and 'inhabitados' / 'edificios_inhabitados'
  // fields when present. 'habitados estables' = edificios - temporals - inhabitats.
  const compRows = [];
  for (const e of state.entries) {
    const s = statsOf(e);
    if (!s || !s.edificios) continue;
    const temp = s.habitados_temporalmente ?? s.edificios_habitados_temporalmente;
    const inhab = s.inhabitados ?? s.edificios_inhabitados;
    if (temp == null || inhab == null) continue;
    const total = s.edificios;
    const estable = Math.max(0, total - temp - inhab);
    compRows.push({ title: e.title, total, estable, temp, inhab });
  }
  compRows.sort((a, b) => b.total - a.total);
  $("stats-chart-buildings").innerHTML = renderBuildingsStacked(compRows.slice(0, 20));

  // === Chart 3: habitants + edificis per illa (twin bar) ===
  const islandHab = new Map();
  const islandEdif = new Map();
  for (const e of state.entries) {
    if (isIslandAggregate(e)) continue;
    const s = statsOf(e);
    if (!s) continue;
    const key = e.island || "(altres)";
    if (s.habitantes != null) islandHab.set(key, (islandHab.get(key) || 0) + s.habitantes);
    if (s.edificios != null) islandEdif.set(key, (islandEdif.get(key) || 0) + s.edificios);
  }
  const islandKeys = [...new Set([...islandHab.keys(), ...islandEdif.keys()])];
  const islandRows = islandKeys
    .map(k => [k, islandHab.get(k) || 0, islandEdif.get(k) || 0])
    .sort((a, b) => b[1] - a[1]);
  $("stats-chart-by-island").innerHTML = renderIslandTwinBars(islandRows);

  // === Chart 5: density (habitants / edifici) top 25 ===
  const densityRows = [];
  for (const e of state.entries) {
    const s = statsOf(e);
    if (!s || !s.habitantes || !s.edificios) continue;
    if (isIslandAggregate(e)) continue;
    const ratio = s.habitantes / s.edificios;
    densityRows.push([e.title, ratio, `${fmt(s.habitantes)} hab / ${fmt(s.edificios)} edif`]);
  }
  densityRows.sort((a, b) => b[1] - a[1]);
  $("stats-chart-density").innerHTML = svgBars(
    densityRows.slice(0, 20).map(r => [r[0], +r[1].toFixed(2), r[2]]),
    { labelW: 220, valueSuffix: " hab/edif" }
  );
}


// === Demographic chart renderers ===========================================

// renderIslandTwinBars: dos donuts (habitants i edificis) repartits per
// illa. Mostren les proporcions; el desequilibri Mallorca-vs-resta queda
// visible sense que les illes petites desapareguin. Cada porció pintada
// amb ISLAND_HUE (el mateix color que el mapa).
function renderIslandTwinBars(rows) {
  if (!rows.length) return '<p class="empty">Sense dades.</p>';
  const totalHab = rows.reduce((s, r) => s + r[1], 0);
  const totalEdif = rows.reduce((s, r) => s + r[2], 0);
  const W = 720, H = 320;
  const cx1 = 180, cx2 = 540, cy = 145, R = 96, r = 56;

  const arcPath = (cx, cy, R, r, a0, a1) => {
    const large = (a1 - a0) > Math.PI ? 1 : 0;
    const x0 = cx + R * Math.cos(a0), y0 = cy + R * Math.sin(a0);
    const x1 = cx + R * Math.cos(a1), y1 = cy + R * Math.sin(a1);
    const x2 = cx + r * Math.cos(a1), y2 = cy + r * Math.sin(a1);
    const x3 = cx + r * Math.cos(a0), y3 = cy + r * Math.sin(a0);
    return `M${x0},${y0} A${R},${R} 0 ${large} 1 ${x1},${y1} L${x2},${y2} A${r},${r} 0 ${large} 0 ${x3},${y3} Z`;
  };

  const drawDonut = (cx, total, valueFn, label) => {
    let svg = "";
    let a = -Math.PI / 2;
    for (const [isl, hab, edif] of rows) {
      const v = valueFn(hab, edif);
      if (!v) continue;
      const sweep = (v / total) * Math.PI * 2;
      const hue = ISLAND_HUE[isl] || "#475569";
      const a1 = a + sweep;
      const mid = (a + a1) / 2;
      const pct = (v / total) * 100;
      svg += `<path d="${arcPath(cx, cy, R, r, a, a1)}" fill="${hue}" style="stroke:var(--surface)" stroke-width="2"><title>${esc(isl)}: ${fmt(v)} (${pct.toFixed(1)}%)</title></path>`;
      if (pct >= 4) {
        const lx = cx + (R + 18) * Math.cos(mid);
        const ly = cy + (R + 18) * Math.sin(mid) + 4;
        const anchor = Math.cos(mid) > 0.2 ? "start" : Math.cos(mid) < -0.2 ? "end" : "middle";
        svg += `<text x="${lx}" y="${ly}" text-anchor="${anchor}" style="font-size:12px;fill:var(--text)">${esc(isl)} <tspan style="fill:var(--text-muted)">(${pct.toFixed(0)}%)</tspan></text>`;
      }
      a = a1;
    }
    svg += `<text x="${cx}" y="${cy - 4}" text-anchor="middle" style="font-size:22px;font-weight:700;fill:var(--text)">${fmt(total)}</text>`;
    svg += `<text x="${cx}" y="${cy + 16}" text-anchor="middle" style="font-size:11px;fill:var(--text-muted);letter-spacing:0.5px;text-transform:uppercase">${label}</text>`;
    svg += `<text x="${cx}" y="${H - 16}" text-anchor="middle" style="font-size:13px;font-weight:600;fill:var(--text)">${label === "habitants" ? "Habitants totals" : "Edificis totals"}</text>`;
    return svg;
  };

  let svg = `<svg viewBox="0 0 ${W} ${H}" class="bars-svg" preserveAspectRatio="xMidYMid meet" role="img" style="max-height:340px">`;
  svg += drawDonut(cx1, totalHab, (h) => h, "habitants");
  svg += drawDonut(cx2, totalEdif, (_, e) => e, "edificis");
  svg += `</svg>`;
  return svg;
}

// Layout HTML de municipi → llistat de nuclis (en lloc d'una barra
// que truncaria els noms). Cada bloc mostra el municipi, comptatge i
// la llista completa de nuclis Riera. Color de fons segons l'illa.
function renderMunicipalityTags(groups) {
  if (!groups.length) return '<p class="empty">Sense dades.</p>';
  const items = groups.map(([m, g]) => {
    const hue = ISLAND_HUE[g.island] || "#475569";
    const tags = g.titles
      .sort((a, b) => a.localeCompare(b))
      .map(t => `<span class="muni-tag">${esc(t)}</span>`).join("");
    return `<div class="muni-group">
      <div class="muni-head">
        <span class="muni-name" style="border-left:4px solid ${hue}">${esc(m)}</span>
        <span class="muni-count">${g.titles.length}</span>
      </div>
      <div class="muni-tags">${tags}</div>
    </div>`;
  }).join("");
  return `<div class="muni-grid">${items}</div>`;
}

// Stacked horizontal bar per entry: habitats stables / temporals / inhabitats
function renderBuildingsStacked(rows) {
  if (!rows.length) return '<p class="empty">Sense dades.</p>';
  const W = 720, labelW = 200, valueW = 110;
  const innerW = W - labelW - valueW - 20;
  const barH = 22, gap = 8;
  const max = Math.max(...rows.map(r => r.total));
  const H = rows.length * (barH + gap) + 30;
  const COLORS = {
    estable: "#0e7490",   // azul — habitats establement
    temp:    "#f59e0b",   // taronja — habitats temporalment
    inhab:   "#9ca3af",   // gris — inhabitats
  };
  let svg = `<svg viewBox="0 0 ${W} ${H}" class="bars-svg" preserveAspectRatio="xMinYMin meet" role="img">`;
  // Legend
  const lx = labelW, ly = 6;
  let lx0 = lx;
  for (const [k, label, col] of [
    ["estable", "habitats", COLORS.estable],
    ["temp", "temporals", COLORS.temp],
    ["inhab", "inhabitats", COLORS.inhab],
  ]) {
    svg += `<rect x="${lx0}" y="${ly}" width="10" height="10" fill="${col}"/>`;
    svg += `<text x="${lx0 + 14}" y="${ly + 9}" class="bar-sub">${label}</text>`;
    lx0 += 92;
  }
  rows.forEach((r, i) => {
    const y = 22 + i * (barH + gap);
    const w = (r.total / max) * innerW;
    const we = (r.estable / r.total) * w;
    const wt = (r.temp / r.total) * w;
    const wi = (r.inhab / r.total) * w;
    svg += `<text x="${labelW - 6}" y="${y + barH * 0.72}" text-anchor="end" class="bar-label">${esc(r.title)}</text>`;
    let x = labelW;
    svg += `<rect x="${x}" y="${y}" width="${we}" height="${barH}" fill="${COLORS.estable}"/>`; x += we;
    svg += `<rect x="${x}" y="${y}" width="${wt}" height="${barH}" fill="${COLORS.temp}"/>`; x += wt;
    svg += `<rect x="${x}" y="${y}" width="${wi}" height="${barH}" fill="${COLORS.inhab}"/>`;
    svg += `<text x="${labelW + w + 6}" y="${y + barH * 0.72}" class="bar-value">${fmt(r.total)} edif.</text>`;
  });
  svg += `</svg>`;
  return svg;
}


// ===========================================================================
// === Island palette and SVG helpers =======================================
// ===========================================================================

const ISLAND_HUE = {
  "Mallorca":   "#0070b8",
  "Menorca":    "#0f766e",
  "Ibiza":      "#c2410c",
  "Eivissa":    "#c2410c",
  "Formentera": "#a04545",
  "Cabrera":    "#7c3aed",
  "Baleares":   "#475569",
};

// ===========================================================================
// === MAPA TAB ===============================================================
// ===========================================================================

let mapInstance = null;
let mapMarkersAll = [];
let mapLeafletLoading = null;

// Lazy-load Leaflet's JS bundle from web/vendor/. Returns a promise that
// resolves once window.L is available. Subsequent calls reuse the same
// promise so we don't fetch twice.
function loadLeaflet() {
  if (window.L) return Promise.resolve();
  if (mapLeafletLoading) return mapLeafletLoading;
  mapLeafletLoading = new Promise((resolve, reject) => {
    const s = document.createElement("script");
    // Vendored (web/vendor/), Leaflet 1.9.4 byte for byte as unpkg served it
    // (same SRI hash), so the site depends on no third-party server.
    s.src = "vendor/leaflet.js";
    s.onload = resolve;
    s.onerror = () => reject(new Error("Leaflet failed to load"));
    document.head.appendChild(s);
  });
  return mapLeafletLoading;
}

function radiusForHabitantes(v) {
  if (!v || v <= 0) return 4;
  // sqrt scaling so Palma (60 000+ hab) isn't 1000× a 200-hab aldea.
  return Math.max(4, Math.min(28, Math.sqrt(v) * 0.15));
}

function buildPopupHTML(e) {
  const stats = e.stats || {};
  const bits = [];
  if (e.place_type) bits.push(e.place_type);
  if (e.island) bits.push(e.island);
  if (e.municipality) bits.push(`mun. ${e.municipality}`);
  if (stats.habitantes) bits.push(`${fmt(stats.habitantes)} hab.`);
  if (stats.edificios) bits.push(`${fmt(stats.edificios)} edif.`);
  const meta = bits.join(" · ");
  const desc = (e.description || e.geografia || e.poblacion || "").slice(0, 600);
  const more = (e.description || e.geografia || e.poblacion || "").length > 600 ? "…" : "";
  const matched = e.matched_toponym
    ? ` <span class="map-popup-meta">↔ ${esc(e.matched_toponym)}</span>` : "";
  const fbLabel = (e.coord_fallback && e.coord_fallback.startsWith("island-centroid"))
    ? "ubicació aproximada al centre de l'illa" : null;
  const fb = fbLabel ? ` <em style="color:#94a3b8">(${esc(fbLabel)})</em>` : "";
  return (
    `<h3 class="map-popup-title">${esc(e.title)}${matched}</h3>` +
    `<p class="map-popup-meta">${esc(meta)} · Tom ${e.vol} · pàg. ${e.page || "?"}${fb}</p>` +
    `<p class="map-popup-desc">${esc(desc)}${more}</p>` +
    (e.bdcyl_url
      ? `<a class="map-popup-link" href="${e.bdcyl_url}" target="_blank" rel="noopener">↗ Volum a BDCyL</a>`
      : "")
  );
}

async function renderMap() {
  await loadLeaflet();
  const el = $("map-canvas");
  if (!el) return;

  if (!mapInstance) {
    // Fit-bounds for Balearic archipelago
    mapInstance = L.map(el, {
      center: [39.7, 2.9],
      zoom: 8,
      zoomControl: true,
      scrollWheelZoom: true,
    });
    // OpenStreetMap's standard tiles. CARTO's basemaps, used until 2026,
    // now answer "API KEY REQUIRED" without a key.
    L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
      maxZoom: 19,
    }).addTo(mapInstance);

    // Build markers (only once — Leaflet keeps them in layers).
    for (const e of state.entries) {
      if (typeof e.lon !== "number" || typeof e.lat !== "number") continue;
      const r = radiusForHabitantes(e.stats?.habitantes);
      const colour = ISLAND_HUE[e.island] || "#475569";
      const m = L.circleMarker([e.lat, e.lon], {
        radius: r,
        color: "#fff",
        weight: 1.2,
        fillColor: colour,
        fillOpacity: e.coord_fallback ? 0.35 : 0.78,
      });
      m._riera_entry = e;
      m.bindPopup(() => buildPopupHTML(e), { maxWidth: 360, minWidth: 280 });
      mapMarkersAll.push(m);
    }

    // Wire fallback toggle
    const toggle = $("map-toggle-fallback");
    if (toggle) {
      toggle.addEventListener("change", () => syncMapMarkers(toggle.checked));
    }
    syncMapMarkers(toggle ? toggle.checked : true);

    // Fit bounds to all visible (non-fallback) markers
    const real = mapMarkersAll.filter(m => !m._riera_entry.coord_fallback);
    if (real.length) {
      const group = L.featureGroup(real);
      mapInstance.fitBounds(group.getBounds().pad(0.08));
    }
  } else {
    // Leaflet needs a kick when the container becomes visible again
    setTimeout(() => mapInstance.invalidateSize(), 60);
  }
}

function syncMapMarkers(showFallback) {
  if (!mapInstance) return;
  for (const m of mapMarkersAll) {
    const fb = m._riera_entry.coord_fallback;
    if (fb && !showFallback) {
      if (mapInstance.hasLayer(m)) mapInstance.removeLayer(m);
    } else {
      if (!mapInstance.hasLayer(m)) m.addTo(mapInstance);
    }
  }
}

boot();
