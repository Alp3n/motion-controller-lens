/* Ekran zużycia osi (/zuzycie) — temat M, krok 3: sam podgląd, bez
 * alarmów/powiadomień (docs/analiza-zuzycia-osi.md). Dwie sekcje z
 * jednego zapytania (/api/zuzycie): "dzisiaj" (tabela) i "trend"
 * (wykresy słupkowe, jeden per oś — rysowane ręcznie na <canvas>, ten sam
 * wzorzec co /sila i panel operatora, bez biblioteki wykresów).
 */

const $ = (id) => document.getElementById(id);

const CSSVAR = (name, fallback) =>
  getComputedStyle(document.documentElement).getPropertyValue(name).trim() || fallback;

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

let lastData = null;

function renderAll() {
  if (!lastData) return;
  renderDzisiaj(lastData.dzisiaj || {});
  renderTrend(lastData.trend || []);
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
// Przerysowanie (nie ponowne pobranie) przy zmianie rozmiaru okna —
// canvas trzeba przeskalować, ale dane sprzed chwili są nadal aktualne.
window.addEventListener("resize", renderAll);
