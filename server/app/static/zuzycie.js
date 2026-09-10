/* Ekran zużycia osi (/zuzycie) — temat M.
 * Krok 3: podgląd (/api/zuzycie) — "dzisiaj" (tabela) i "trend" (wykresy
 * słupkowe, jeden per oś — rysowane ręcznie na <canvas>, ten sam wzorzec
 * co /sila i panel operatora, bez biblioteki wykresów).
 * Krok 4: definicje alarmów (/api/zuzycie/alarmy) — CRUD wzorem kalibracji
 * w sila.js (stan lokalny, mutacja, PUT całego obiektu, odśwież z
 * odpowiedzi) i stan oceny (z tego samego /api/zuzycie).
 */

const $ = (id) => document.getElementById(id);

const CSSVAR = (name, fallback) =>
  getComputedStyle(document.documentElement).getPropertyValue(name).trim() || fallback;

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

function showAlarmMsg(text, ok = false) {
  const el = $("alarmy-msg");
  el.textContent = text;
  el.className = "msg " + (ok ? "ok" : "err");
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

function fmt(v, digits = 1) {
  return v === null || v === undefined ? "—" : Number(v).toFixed(digits);
}

// --- "Dzisiaj" — tabela ----------------------------------------------------

function renderDzisiaj(dzisiaj) {
  const tbody = $("dzisiaj-tabela");
  const axes = Object.keys(dzisiaj).sort();
  $("dzisiaj-puste").style.display = axes.length ? "none" : "";
  tbody.innerHTML = axes
    .map((axis) => {
      const d = dzisiaj[axis];
      return `<tr>
        <td>${axis.toUpperCase()}</td>
        <td>${d.liczba_przebiegow}</td>
        <td>${fmt(d.dystans_mm_suma)}</td>
        <td>${fmt(d.moment_srednia_pct)}</td>
        <td>${fmt(d.moment_max_pct)}</td>
      </tr>`;
    })
    .join("");
}

// --- Trend — jeden wykres słupkowy per oś ----------------------------------

/* Małe wielokrotności (jeden wykres per oś) zamiast jednego wspólnego
 * wykresu wieloseriowego — osie mają zupełnie różne skale dystansu
 * (np. Z porusza się dużo mniej niż X/Y w typowym programie), więc
 * wspólna oś Y spłaszczyłaby mniejsze wartości. Każdy wykres ma swoją
 * skalę, więc nie trzeba normalizować ani używać drugiej osi Y. */
function drawTrendBar(canvas, days, color) {
  const { ctx, w, h } = _resizeCanvas(canvas);
  const muted = CSSVAR("--muted", "#93a1b1");
  const border = CSSVAR("--border", "#33404f");

  if (!days.length) {
    ctx.fillStyle = muted;
    ctx.font = "13px sans-serif";
    ctx.fillText("Brak jeszcze danych trendu dla tej osi.", 12, h / 2);
    return;
  }

  const maxVal = Math.max(1, ...days.map((d) => d.dystans_mm_suma));
  const pad = { l: 46, r: 8, t: 10, b: 20 };
  const plotW = w - pad.l - pad.r;
  const plotH = h - pad.t - pad.b;
  const barGap = 4;
  const barW = Math.max(2, plotW / days.length - barGap);

  ctx.strokeStyle = border;
  ctx.fillStyle = muted;
  ctx.font = "11px sans-serif";
  [0, maxVal / 2, maxVal].forEach((v) => {
    const y = pad.t + plotH - (v / maxVal) * plotH;
    ctx.beginPath();
    ctx.moveTo(pad.l, y);
    ctx.lineTo(w - pad.r, y);
    ctx.stroke();
    ctx.fillText(v.toFixed(0), 2, y + 4);
  });

  days.forEach((d, i) => {
    const x = pad.l + i * (barW + barGap);
    const barH = (d.dystans_mm_suma / maxVal) * plotH;
    const y = pad.t + plotH - barH;
    ctx.fillStyle = color;
    // zaokrąglony górny koniec słupka, zakotwiczony do osi — jak reszta
    // wykresów w aplikacji (patrz sila.js)
    const r = Math.min(3, barW / 2, Math.max(0, barH));
    ctx.beginPath();
    ctx.moveTo(x, y + r);
    ctx.arcTo(x, y, x + r, y, r);
    ctx.arcTo(x + barW, y, x + barW, y + r, r);
    ctx.lineTo(x + barW, pad.t + plotH);
    ctx.lineTo(x, pad.t + plotH);
    ctx.closePath();
    ctx.fill();
  });

  // etykiety dat — co N-ty słupek, żeby się nie nakładały
  ctx.fillStyle = muted;
  ctx.font = "10px sans-serif";
  ctx.textAlign = "center";
  const labelEvery = Math.max(1, Math.ceil((days.length * 40) / plotW));
  days.forEach((d, i) => {
    if (i % labelEvery !== 0) return;
    const x = pad.l + i * (barW + barGap) + barW / 2;
    ctx.fillText(d.data.slice(5), x, h - 4); // "MM-DD"
  });
  ctx.textAlign = "left";
}

function renderTrend(trend) {
  const byAxis = {};
  for (const entry of trend) {
    (byAxis[entry.os] = byAxis[entry.os] || []).push(entry);
  }
  const axes = Object.keys(byAxis).sort();
  $("trend-puste").style.display = axes.length ? "none" : "";

  const allDates = new Set(trend.map((e) => e.data));
  $("trend-count").textContent = allDates.size;

  const container = $("trend-charts");
  container.innerHTML = "";
  const accent = CSSVAR("--accent", "#3aa0ff");
  for (const axis of axes) {
    // najstarsze -> najnowsze (odwrotnie niż read_trend, który zwraca od najnowszych)
    const days = byAxis[axis].slice().reverse();
    const wrap = document.createElement("div");
    wrap.style.marginBottom = "18px";
    const title = document.createElement("p");
    title.className = "muted";
    title.style.margin = "0 0 4px";
    title.textContent = `Oś ${axis.toUpperCase()} — suma dystansu na dzień [mm]`;
    const viewWrap = document.createElement("div");
    viewWrap.className = "view-wrap";
    const canvas = document.createElement("canvas");
    canvas.style.height = "140px";
    viewWrap.appendChild(canvas);
    wrap.appendChild(title);
    wrap.appendChild(viewWrap);
    container.appendChild(wrap);
    drawTrendBar(canvas, days, accent);
  }
}

// --- Alarmy: stan oceny (z /api/zuzycie) -----------------------------------

const METRYKA_LABELS = {
  dystans_mm_suma: "dystans [mm]",
  moment_max_pct: "moment maks. [%]",
};
const OKRES_LABELS = { dzien: "dzień", tydzien: "tydzień" };

function renderAlarmyStatus(alarmy) {
  const tbody = $("alarmy-status-tabela");
  $("alarmy-status-puste").style.display = alarmy.length ? "none" : "";
  const ok = CSSVAR("--ok", "#2ecc71");
  const err = CSSVAR("--err", "#e74c3c");
  tbody.innerHTML = alarmy
    .map((a) => {
      const stanKolor = a.przekroczony ? err : ok;
      const stanTekst = a.wartosc == null ? "brak danych" : a.przekroczony ? "PRZEKROCZONY" : "OK";
      return `<tr>
        <td>${a.name}</td>
        <td>${a.os.toUpperCase()}</td>
        <td>${METRYKA_LABELS[a.metryka] || a.metryka}</td>
        <td>${OKRES_LABELS[a.okres] || a.okres}</td>
        <td>${fmt(a.prog)}</td>
        <td>${fmt(a.wartosc)}</td>
        <td style="color:${stanKolor}; font-weight:600">${stanTekst}</td>
      </tr>`;
    })
    .join("");
}

// --- Alarmy: definicje (CRUD, /api/zuzycie/alarmy) -------------------------

let alarmDefs = {};

function renderAlarmyDef() {
  const tbody = $("alarmy-def-tabela");
  const names = Object.keys(alarmDefs).sort();
  tbody.innerHTML = names
    .map((name) => {
      const d = alarmDefs[name];
      return `<tr data-name="${name}">
        <td>${name}</td>
        <td>${d.os.toUpperCase()}</td>
        <td>${METRYKA_LABELS[d.metryka] || d.metryka}</td>
        <td>${OKRES_LABELS[d.okres] || d.okres}</td>
        <td>${fmt(d.prog)}</td>
        <td>${d.aktywny ? "tak" : "nie"}</td>
        <td>${d.note || ""}</td>
        <td></td>
      </tr>`;
    })
    .join("");
  tbody.querySelectorAll("tr").forEach((tr) => {
    const btn = document.createElement("button");
    btn.className = "small";
    btn.textContent = "🗑";
    btn.title = "usuń alarm";
    btn.onclick = () => usunAlarm(tr.dataset.name);
    tr.lastElementChild.appendChild(btn);
  });
}

async function zapiszAlarmy() {
  try {
    const res = await api("PUT", "/api/zuzycie/alarmy", { alarmy: alarmDefs });
    alarmDefs = res.alarmy;
    renderAlarmyDef();
    showAlarmMsg("Zapisano.", true);
  } catch (e) {
    showAlarmMsg(e.message);
  }
}

function usunAlarm(name) {
  delete alarmDefs[name];
  zapiszAlarmy();
}

function dodajAlarm() {
  const name = $("def-name").value.trim();
  const prog = Number(String($("def-prog").value).replace(",", "."));
  if (!name) {
    showAlarmMsg("podaj nazwę alarmu");
    return;
  }
  if (!Number.isFinite(prog) || prog <= 0) {
    showAlarmMsg("próg: liczba dodatnia");
    return;
  }
  alarmDefs[name] = {
    os: $("def-os").value,
    metryka: $("def-metryka").value,
    okres: $("def-okres").value,
    prog,
    aktywny: true,
    note: $("def-note").value.trim(),
  };
  $("def-name").value = "";
  $("def-prog").value = "";
  $("def-note").value = "";
  zapiszAlarmy();
}

function fillSelect(id, values, labels) {
  $(id).innerHTML = values.map((v) => `<option value="${v}">${labels[v] || v}</option>`).join("");
}

async function loadAlarmyDef() {
  try {
    const res = await api("GET", "/api/zuzycie/alarmy");
    alarmDefs = res.alarmy;
    fillSelect("def-metryka", res.metryki, METRYKA_LABELS);
    fillSelect("def-okres", res.okresy, OKRES_LABELS);
    renderAlarmyDef();
  } catch (e) {
    showAlarmMsg(e.message);
  }
}

$("btn-dodaj-alarm").onclick = dodajAlarm;

// --- ładowanie i odświeżanie -------------------------------------------------

let lastData = null;

function renderAll() {
  if (!lastData) return;
  renderDzisiaj(lastData.dzisiaj || {});
  renderTrend(lastData.trend || []);
  renderAlarmyStatus(lastData.alarmy || []);
}

async function load() {
  try {
    const res = await fetch("/api/zuzycie");
    lastData = await res.json();
    renderAll();
  } catch (err) {
    $("dzisiaj-puste").style.display = "";
    $("dzisiaj-puste").textContent = "Nie udało się wczytać danych: " + err.message;
  }
}

load();
loadAlarmyDef();
// Przerysowanie (nie ponowne pobranie) przy zmianie rozmiaru okna —
// canvas trzeba przeskalować, ale dane sprzed chwili są nadal aktualne.
window.addEventListener("resize", renderAll);
