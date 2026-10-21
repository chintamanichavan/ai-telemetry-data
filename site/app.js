/* AI Telemetry — vanilla JS, no dependencies. Reads ../data/models.csv. */

const MODELS_URL = "../data/models.csv";
const SVG_NS = "http://www.w3.org/2000/svg";

// ---------- CSV parser (RFC 4180) ----------
function parseCSV(text) {
  const rows = [];
  let row = [], field = "", inQ = false;
  for (let i = 0; i < text.length; i++) {
    const c = text[i];
    if (inQ) {
      if (c === '"' && text[i + 1] === '"') { field += '"'; i++; }
      else if (c === '"') inQ = false;
      else field += c;
    } else {
      if (c === '"') inQ = true;
      else if (c === ',') { row.push(field); field = ""; }
      else if (c === '\n') { row.push(field); rows.push(row); row = []; field = ""; }
      else if (c === '\r') { /* skip */ }
      else field += c;
    }
  }
  if (field !== "" || row.length) { row.push(field); rows.push(row); }
  const headers = rows.shift();
  return rows
    .filter(r => r.length === headers.length)
    .map(r => Object.fromEntries(headers.map((h, i) => [h, r[i]])));
}

// ---------- SVG helpers ----------
function el(name, attrs = {}, children = []) {
  const n = document.createElementNS(SVG_NS, name);
  for (const [k, v] of Object.entries(attrs)) n.setAttribute(k, v);
  for (const c of children) n.appendChild(c);
  return n;
}

// ---------- main ----------
async function main() {
  const text = await (await fetch(MODELS_URL)).text();
  const all = parseCSV(text);
  const current = all.filter(r => !r.valid_to);

  renderMeta(current, all);
  renderComputeChart(current);
  renderReleasesChart(current);
  renderOrgsTable(current);
}

function renderMeta(current, all) {
  const updated = all
    .map(r => r.observed_at)
    .filter(Boolean)
    .sort()
    .pop();
  const dateOnly = updated ? updated.slice(0, 10) : "—";
  document.getElementById("updated").textContent = "Updated " + dateOnly;
}

// ---------- chart 1: training compute over time (log-y scatter) ----------
function renderComputeChart(rows) {
  const points = rows
    .map(r => ({
      x: Date.parse(r.release_date),
      y: parseFloat(r.training_compute_flop),
      tier: r.capability_tier,
      name: r.name,
      org: r.org_id,
      date: r.release_date,
    }))
    .filter(p => p.x && p.y > 0);

  const W = 900, H = 360, M = { t: 16, r: 16, b: 36, l: 56 };
  const innerW = W - M.l - M.r, innerH = H - M.t - M.b;
  const xMin = Math.min(...points.map(p => p.x));
  const xMax = Math.max(...points.map(p => p.x));
  const yMinLog = Math.floor(Math.log10(Math.min(...points.map(p => p.y))));
  const yMaxLog = Math.ceil(Math.log10(Math.max(...points.map(p => p.y))));

  const sx = x => M.l + ((x - xMin) / (xMax - xMin)) * innerW;
  const sy = y => M.t + (1 - (Math.log10(y) - yMinLog) / (yMaxLog - yMinLog)) * innerH;

  const svg = el("svg", { viewBox: `0 0 ${W} ${H}` });

  // y gridlines + labels (one per log decade)
  for (let exp = yMinLog; exp <= yMaxLog; exp++) {
    const y = sy(Math.pow(10, exp));
    svg.appendChild(el("line", {
      class: "gridline", x1: M.l, x2: W - M.r, y1: y, y2: y,
    }));
    const t = el("text", {
      class: "axis-label", x: M.l - 8, y: y + 3,
      "text-anchor": "end", fill: "var(--ink-soft)", "font-size": 11,
    });
    t.textContent = "10" + supDigits(exp);
    svg.appendChild(t);
  }

  // x ticks: one per year
  const yrStart = new Date(xMin).getUTCFullYear();
  const yrEnd = new Date(xMax).getUTCFullYear();
  for (let y = yrStart; y <= yrEnd; y++) {
    const xPx = sx(Date.UTC(y, 0, 1));
    if (xPx < M.l || xPx > W - M.r) continue;
    svg.appendChild(el("line", {
      class: "gridline", x1: xPx, x2: xPx, y1: M.t, y2: H - M.b,
    }));
    const t = el("text", {
      x: xPx, y: H - M.b + 16, "text-anchor": "middle",
      fill: "var(--ink-soft)", "font-size": 11,
    });
    t.textContent = y;
    svg.appendChild(t);
  }

  // axis frames
  svg.appendChild(el("line", {
    class: "axis", x1: M.l, x2: W - M.r, y1: H - M.b, y2: H - M.b,
    stroke: "var(--rule)",
  }));
  svg.appendChild(el("line", {
    class: "axis", x1: M.l, x2: M.l, y1: M.t, y2: H - M.b,
    stroke: "var(--rule)",
  }));

  // y-axis title
  const yTitle = el("text", {
    x: -((H + M.t) / 2), y: 16, transform: "rotate(-90)",
    "text-anchor": "middle", fill: "var(--ink-soft)", "font-size": 11,
  });
  yTitle.textContent = "Training compute (FLOP)";
  svg.appendChild(yTitle);

  // points
  for (const p of points) {
    const c = el("circle", {
      class: "point " + p.tier,
      cx: sx(p.x), cy: sy(p.y), r: p.tier === "frontier" ? 5 : 3.5,
    });
    const title = document.createElementNS(SVG_NS, "title");
    title.textContent = `${p.name} (${p.org})\n${p.date}\n${p.y.toExponential(2)} FLOP`;
    c.appendChild(title);
    svg.appendChild(c);
  }

  document.getElementById("compute-chart").appendChild(svg);

  const front = points.filter(p => p.tier === "frontier").length;
  const note = points.filter(p => p.tier === "notable").length;
  document.getElementById("compute-caption").textContent =
    `${points.length} models · ${front} frontier · ${note} notable · ` +
    `log scale; hover for details.`;
}

function supDigits(n) {
  const m = { "-": "⁻", "0": "⁰", "1": "¹", "2": "²", "3": "³", "4": "⁴",
              "5": "⁵", "6": "⁶", "7": "⁷", "8": "⁸", "9": "⁹" };
  return String(n).split("").map(c => m[c] || c).join("");
}

// ---------- chart 2: releases per quarter ----------
function renderReleasesChart(rows) {
  const quarters = {};
  for (const r of rows) {
    if (!r.release_date) continue;
    const d = new Date(r.release_date);
    if (isNaN(d)) continue;
    const q = `${d.getUTCFullYear()}Q${Math.floor(d.getUTCMonth() / 3) + 1}`;
    quarters[q] = (quarters[q] || 0) + 1;
  }
  const keys = Object.keys(quarters).sort();
  const last8 = keys.slice(-8);
  const max = Math.max(...last8.map(k => quarters[k]));

  const W = 900, H = 220, M = { t: 16, r: 16, b: 36, l: 40 };
  const innerW = W - M.l - M.r, innerH = H - M.t - M.b;
  const barW = innerW / last8.length * 0.7;
  const gap = innerW / last8.length * 0.3;

  const svg = el("svg", { viewBox: `0 0 ${W} ${H}` });

  // y gridlines (every 5)
  const yStep = max <= 10 ? 2 : 5;
  for (let v = 0; v <= max; v += yStep) {
    const yPx = M.t + (1 - v / max) * innerH;
    svg.appendChild(el("line", {
      class: "gridline", x1: M.l, x2: W - M.r, y1: yPx, y2: yPx,
    }));
    const t = el("text", {
      x: M.l - 8, y: yPx + 3, "text-anchor": "end",
      fill: "var(--ink-soft)", "font-size": 11,
    });
    t.textContent = v;
    svg.appendChild(t);
  }

  last8.forEach((q, i) => {
    const count = quarters[q];
    const x = M.l + (i + 0.5) * (innerW / last8.length) - barW / 2;
    const h = (count / max) * innerH;
    const rect = el("rect", {
      class: "bar", x, y: H - M.b - h, width: barW, height: h,
    });
    const title = document.createElementNS(SVG_NS, "title");
    title.textContent = `${q}: ${count} releases`;
    rect.appendChild(title);
    svg.appendChild(rect);

    const lbl = el("text", {
      x: x + barW / 2, y: H - M.b + 16, "text-anchor": "middle",
      fill: "var(--ink-soft)", "font-size": 11,
    });
    lbl.textContent = q;
    svg.appendChild(lbl);

    const cnt = el("text", {
      x: x + barW / 2, y: H - M.b - h - 4, "text-anchor": "middle",
      fill: "var(--ink)", "font-size": 11, "font-weight": 500,
    });
    cnt.textContent = count;
    svg.appendChild(cnt);
  });

  document.getElementById("releases-chart").appendChild(svg);
  document.getElementById("releases-caption").textContent =
    `Last 8 quarters (${last8[0]}–${last8[last8.length - 1]}). ` +
    `Notable + frontier combined.`;
}

// ---------- table: top orgs by frontier model count ----------
function renderOrgsTable(rows) {
  const byOrg = {};
  for (const r of rows) {
    const o = r.org_id;
    if (!byOrg[o]) byOrg[o] = { notable: 0, frontier: 0, latest: "" };
    if (r.capability_tier === "frontier") {
      byOrg[o].frontier++;
      if (r.release_date > byOrg[o].latest) byOrg[o].latest = r.release_date;
    } else {
      byOrg[o].notable++;
    }
  }
  const orgs = Object.entries(byOrg)
    .filter(([, v]) => v.frontier > 0)
    .sort((a, b) => b[1].frontier - a[1].frontier
                  || (b[1].latest > a[1].latest ? 1 : -1));

  const table = document.createElement("table");
  table.innerHTML = `
    <thead><tr>
      <th>Organization</th>
      <th class="num">Frontier</th>
      <th class="num">Notable</th>
      <th>Most recent frontier release</th>
    </tr></thead><tbody></tbody>`;
  const tb = table.querySelector("tbody");
  for (const [org, v] of orgs) {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${escape(org)}</td>
      <td class="num">${v.frontier}</td>
      <td class="num">${v.notable}</td>
      <td>${v.latest || "<span class=\"secondary\">—</span>"}</td>`;
    tb.appendChild(tr);
  }
  document.getElementById("orgs-table").appendChild(table);
}

function escape(s) {
  return String(s).replace(/[&<>"']/g, c => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  })[c]);
}

main().catch(e => {
  document.body.insertAdjacentHTML("afterbegin",
    `<div style="padding:20px;background:#fee;color:#900">
       Error loading data: ${escape(e.message)}.
       Serve from a local HTTP server: <code>python3 -m http.server</code>
       then open <code>http://localhost:8000/site/</code>.
     </div>`);
});
