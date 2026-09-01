/* Ekran kontroli siły i kalibracji (/sila) — etap 2 tematu K, część bez
 * automatycznej próby przejazdu (patrz uwaga na ekranie i docs/funkcje-smart.md).
 *
 * Dwie niezależne rzeczy na jednej stronie:
 *   - podgląd momentu na żywo przez /ws/status (ten sam kanał co panel operatora)
 *   - kalibracja moment->siła: CRUD na /api/kalibracja, zapis całego obiektu
 *     przy każdej zmianie (prościej niż osobny stan "niezapisane zmiany")
 */

const $ = (id) => document.getElementById(id);

let kalibracja = { x: { punkty: [] }, y: { punkty: [] }, z: { punkty: [] } };

async function api(method, url, body) {
  const res = await fetch(url, {
    method,
    headers: { "Content-Type": "application/json" },
    body: body ? JSON.stringify(body) : undefined,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || res.statusText);
  return data;
}

function showMsg(text, ok = false) {
  const el = $("kalibracja-msg");
  el.textContent = text;
  el.className = "msg " + (ok ? "ok" : "err");
}

function num(value) {
  const v = String(value).trim().replace(",", ".");
  return v === "" ? NaN : Number(v);
}

// --- podgląd momentu na żywo (WebSocket, jak panel operatora) --------------

function applyStatus(st) {
  const trq = st.torque || {};
  const source = st.torque_source || "brak";
  for (const axis of ["x", "y", "z"]) {
    const el = $("trq-" + axis);
    if (!el) continue;
    el.textContent =
      source === "brak" || trq[axis] == null ? "—" : trq[axis].toFixed(1) + " %";
  }
  const srcEl = $("trq-source");
  if (source === "sterownik") {
    srcEl.textContent = "źródło: pomiar ze sterownika (TrqMeasured)";
    srcEl.className = "muted";
  } else if (source === "symulacja") {
    srcEl.textContent =
      "źródło: SYMULACJA — wartości wymyślone przez symulator, nie pomiar; " +
      "nie kalibruj na nich siłomierza";
    srcEl.className = "msg warn";
  } else {
    srcEl.textContent = "brak odczytu momentu — mostek go jeszcze nie wysyła";
    srcEl.className = "muted";
  }
}

function connectWs() {
  const ws = new WebSocket(
    (location.protocol === "https:" ? "wss://" : "ws://") + location.host + "/ws/status"
  );
  ws.onmessage = (ev) => applyStatus(JSON.parse(ev.data));
  ws.onclose = () => setTimeout(connectWs, 1000);
}

// --- kalibracja -------------------------------------------------------------

function renderAxis(axis) {
  const panel = document.querySelector(`#kalibracja-osie > [data-axis="${axis}"]`);
  const tbody = panel.querySelector(".punkty-list");
  const punkty = (kalibracja[axis] && kalibracja[axis].punkty) || [];
  tbody.innerHTML = "";
  punkty.forEach((p, i) => {
    const tr = document.createElement("tr");
    const data = p.data ? p.data.slice(0, 10) : "";
    tr.innerHTML =
      `<td>${p.moment_pct}</td><td>${p.sila_n}</td>` +
      `<td>${p.kierunek || ""}</td><td>${data}</td><td></td>`;
    const btnDel = document.createElement("button");
    btnDel.className = "small";
    btnDel.textContent = "🗑";
    btnDel.title = "usuń punkt";
    btnDel.onclick = () => usunPunkt(axis, i);
    tr.lastElementChild.appendChild(btnDel);
    tbody.appendChild(tr);
  });
}

function renderAll() {
  for (const axis of ["x", "y", "z"]) renderAxis(axis);
}

async function zapisz() {
  try {
    const res = await api("PUT", "/api/kalibracja", { kalibracja });
    kalibracja = res.kalibracja;
    renderAll();
    showMsg("Zapisano.", true);
  } catch (e) {
    showMsg(e.message);
  }
}

function usunPunkt(axis, index) {
  kalibracja[axis].punkty.splice(index, 1);
  zapisz();
}

function dodajPunkt(axis, panel) {
  const moment = num(panel.querySelector(".f-moment").value);
  const sila = num(panel.querySelector(".f-sila").value);
  if (!Number.isFinite(moment) || moment <= 0 || moment > 100) {
    showMsg("moment %: liczba w zakresie (0, 100]");
    return;
  }
  if (!Number.isFinite(sila) || sila < 0) {
    showMsg("siła N: liczba ≥ 0");
    return;
  }
  const kierunek = panel.querySelector(".f-kierunek").value.trim();
  const uwagi = panel.querySelector(".f-uwagi").value.trim();
  if (!kalibracja[axis]) kalibracja[axis] = { punkty: [] };
  kalibracja[axis].punkty.push({
    moment_pct: moment,
    sila_n: sila,
    kierunek,
    uwagi,
    data: "",
  });
  panel.querySelector(".f-moment").value = "";
  panel.querySelector(".f-sila").value = "";
  panel.querySelector(".f-kierunek").value = "";
  panel.querySelector(".f-uwagi").value = "";
  zapisz();
}

document.querySelectorAll("#kalibracja-osie > [data-axis]").forEach((panel) => {
  const axis = panel.dataset.axis;
  panel.querySelector(".btn-dodaj").onclick = () => dodajPunkt(axis, panel);
});

async function load() {
  try {
    const res = await api("GET", "/api/kalibracja");
    kalibracja = res.kalibracja;
    $("kalibracja-file").textContent = "plik: " + res.file;
    renderAll();
  } catch (e) {
    showMsg(e.message);
  }
}

load();
connectWs();

// --- przebieg ostatniego uruchomienia (moment + prędkość w czasie) --------
//
// Rysowanie ręczne na <canvas>, bez biblioteki wykresów — ten sam wzorzec co
// podgląd pozycji XY na panelu operatora (app.js: drawView/CSSVAR). Dane
// nagrywa serwer (Machine._record_sample, co 200 ms z _poll_loop) i trzyma
// do następnego uruchomienia — ten skrypt tylko je pobiera i rysuje.

const CSSVAR = (name, fallback) =>
  getComputedStyle(document.documentElement).getPropertyValue(name).trim() || fallback;

function _opKey(s) {
  if (s.op != null) return "op" + s.op;
  if (s.cycle_step != null) return "cs" + s.cycle_step;
  return null;
}

function _opLabel(s) {
  if (s.op != null) return "LP " + s.op;
  if (s.cycle_step != null) return "krok " + s.cycle_step;
  return "—";
}

function _resizeCanvas(c) {
  const dpr = window.devicePixelRatio || 1;
  const w = c.clientWidth;
  const h = c.clientHeight;
  if (c.width !== Math.round(w * dpr) || c.height !== Math.round(h * dpr)) {
    c.width = Math.round(w * dpr);
    c.height = Math.round(h * dpr);
  }
  const ctx = c.getContext("2d");
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, w, h);
  return { ctx, w, h };
}

/* Pionowe przerywane linie na granicach operacji/kroków, z etykietą LP —
   wspólne dla obu wykresów, żeby czas był czytelny w obu naraz. */
function _drawOpBoundaries(ctx, samples, X, padTop, plotBottom, muted) {
  ctx.save();
  ctx.setLineDash([4, 3]);
  ctx.strokeStyle = muted;
  ctx.fillStyle = muted;
  ctx.font = "11px sans-serif";
  let last = undefined;
  samples.forEach((s) => {
    const key = _opKey(s);
    if (key !== last) {
      const x = X(s.t);
      ctx.beginPath();
      ctx.moveTo(x, padTop);
      ctx.lineTo(x, plotBottom);
      ctx.stroke();
      if (key != null) ctx.fillText(_opLabel(s), x + 3, padTop + 10);
      last = key;
    }
  });
  ctx.restore();
}

function drawMomentChart(samples) {
  const c = $("przebieg-moment");
  if (!c) return;
  const { ctx, w, h } = _resizeCanvas(c);
  const muted = CSSVAR("--muted", "#93a1b1");
  const border = CSSVAR("--border", "#33404f");
  const colors = { x: CSSVAR("--accent", "#3aa0ff"), y: CSSVAR("--ok", "#2ecc71"), z: CSSVAR("--warn", "#f1c40f") };

  if (!samples.length) {
    ctx.fillStyle = muted;
    ctx.font = "13px sans-serif";
    ctx.fillText("Brak nagranego przebiegu — uruchom program albo cykl.", 12, h / 2);
    return;
  }

  const pad = { l: 34, r: 8, t: 8, b: 18 };
  const plotW = w - pad.l - pad.r;
  const plotH = h - pad.t - pad.b;
  const tMax = Math.max(samples[samples.length - 1].t, 0.1);
  const X = (t) => pad.l + (t / tMax) * plotW;
  const Y = (v) => pad.t + plotH - (Math.max(0, Math.min(100, Math.abs(v))) / 100) * plotH;

  ctx.strokeStyle = border;
  ctx.fillStyle = muted;
  ctx.font = "11px sans-serif";
  [0, 50, 100].forEach((v) => {
    const y = Y(v);
    ctx.beginPath();
    ctx.moveTo(pad.l, y);
    ctx.lineTo(w - pad.r, y);
    ctx.stroke();
    ctx.fillText(v + "%", 2, y + 4);
  });

  _drawOpBoundaries(ctx, samples, X, pad.t, h - pad.b, muted);

  for (const axis of ["x", "y", "z"]) {
    ctx.strokeStyle = colors[axis];
    ctx.lineWidth = 1.5;
    ctx.beginPath();
    samples.forEach((s, i) => {
      const px = X(s.t);
      const py = Y((s.torque && s.torque[axis]) || 0);
      if (i === 0) ctx.moveTo(px, py);
      else ctx.lineTo(px, py);
    });
    ctx.stroke();
  }
}

/* Prędkość wypadkowa liczona z odległości między kolejnymi próbkami pozycji
   — serwer nagrywa x/y/z, nie samą prędkość, więc liczymy ją tutaj. */
function _speeds(samples) {
  const out = [];
  for (let i = 1; i < samples.length; i++) {
    const a = samples[i - 1];
    const b = samples[i];
    const dt = b.t - a.t;
    if (dt <= 0) {
      out.push(0);
      continue;
    }
    const dist = Math.hypot(b.x - a.x, b.y - a.y, b.z - a.z);
    out.push((dist / dt) * 60); // mm/min
  }
  return [0, ...out];
}

function drawSpeedChart(samples, speeds) {
  const c = $("przebieg-predkosc");
  if (!c) return;
  const { ctx, w, h } = _resizeCanvas(c);
  const muted = CSSVAR("--muted", "#93a1b1");
  const border = CSSVAR("--border", "#33404f");
  const accent = CSSVAR("--accent", "#3aa0ff");

  if (!samples.length) return;

  const pad = { l: 44, r: 8, t: 8, b: 18 };
  const plotW = w - pad.l - pad.r;
  const plotH = h - pad.t - pad.b;
  const tMax = Math.max(samples[samples.length - 1].t, 0.1);
  const vMax = Math.max(...speeds, 1);
  const X = (t) => pad.l + (t / tMax) * plotW;
  const Y = (v) => pad.t + plotH - (Math.max(0, v) / vMax) * plotH;

  ctx.strokeStyle = border;
  ctx.fillStyle = muted;
  ctx.font = "11px sans-serif";
  [0, vMax / 2, vMax].forEach((v) => {
    const y = Y(v);
    ctx.beginPath();
    ctx.moveTo(pad.l, y);
    ctx.lineTo(w - pad.r, y);
    ctx.stroke();
    ctx.fillText(Math.round(v), 2, y + 4);
  });

  _drawOpBoundaries(ctx, samples, X, pad.t, h - pad.b, muted);

  ctx.strokeStyle = accent;
  ctx.lineWidth = 1.5;
  ctx.beginPath();
  samples.forEach((s, i) => {
    const px = X(s.t);
    const py = Y(speeds[i] || 0);
    if (i === 0) ctx.moveTo(px, py);
    else ctx.lineTo(px, py);
  });
  ctx.stroke();
}

function renderPrzebiegTabela(samples) {
  const tbody = $("przebieg-tabela");
  if (!tbody) return;
  tbody.innerHTML = "";
  const groups = [];
  let current = null;
  for (const s of samples) {
    const key = _opKey(s);
    if (!current || current.key !== key) {
      current = { key, label: _opLabel(s), tStart: s.t, tEnd: s.t, torque: { x: [], y: [], z: [] } };
      groups.push(current);
    }
    current.tEnd = s.t;
    for (const axis of ["x", "y", "z"]) current.torque[axis].push((s.torque && s.torque[axis]) || 0);
  }
  for (const g of groups) {
    if (g.key == null) continue; // próbki poza operacją (np. dojazd) — pomijamy w tabeli
    const tr = document.createElement("tr");
    const cells = ["x", "y", "z"].map((axis) => {
      const vals = g.torque[axis];
      const avg = vals.reduce((a, b) => a + b, 0) / (vals.length || 1);
      const max = Math.max(...vals.map(Math.abs));
      return `${avg.toFixed(1)} / ${max.toFixed(1)} %`;
    });
    tr.innerHTML =
      `<td>${g.label}</td><td>${(g.tEnd - g.tStart).toFixed(1)} s</td>` +
      cells.map((c) => `<td>${c}</td>`).join("");
    tbody.appendChild(tr);
  }
}

async function loadPrzebieg() {
  try {
    const res = await api("GET", "/api/przebieg");
    const samples = res.samples || [];
    const speeds = _speeds(samples);
    drawMomentChart(samples);
    drawSpeedChart(samples, speeds);
    renderPrzebiegTabela(samples);
  } catch (e) {
    // ekran działa też bez tej sekcji (np. brak uprawnień) — cicho pomijamy
  }
}

window.addEventListener("resize", loadPrzebieg);
loadPrzebieg();
setInterval(loadPrzebieg, 1000);
