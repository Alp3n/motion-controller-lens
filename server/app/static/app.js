/* Panel operatora — status przez WebSocket, sterowanie przez REST API. */

const $ = (id) => document.getElementById(id);

let currentProgram = null; // ostatnio załadowany program (operacje do tabeli)
let simMode = false;
let lastStatus = null; // ostatni status — do przerysowania podglądu

function fmt(v) {
  return v === null || v === undefined ? "" : Number(v).toFixed(3);
}

function showMsg(el, text, ok = false) {
  el.textContent = text;
  el.className = "msg " + (ok ? "ok" : "err");
  setTimeout(() => (el.className = "msg"), 6000);
}

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

// --- status na żywo -------------------------------------------------------

function applyStatus(st) {
  const stateEl = $("state");
  stateEl.textContent = st.state;
  stateEl.className = "state-badge state-" + st.state;

  $("enable-dot").className = "enable-dot" + (st.safety_enable ? " on" : "");
  $("enable-text").textContent =
    "sygnał zezwolenia: " + (st.safety_enable ? "AKTYWNY" : "BRAK — ruch zablokowany");

  const alarm = $("alarm");
  if (st.alarm_message) {
    alarm.textContent = "ALARM: " + st.alarm_message;
    alarm.className = "msg err";
  } else {
    alarm.className = "msg";
  }

  /* RESET po alarmie na już zbazowanej maszynie wraca do READY zamiast
     NOT_HOMED (pozycja z enkodera zostaje wiarygodna) — ale to nie zwalnia
     operatora z obejrzenia maszyny, jeśli STOP przyszedł np. przez zacięty
     materiał. Ostrzeżenie gaśnie dopiero po kolejnym bazowaniu (patrz
     bridge/sc4hub_bridge.cpp i docs/zmiany/wznowienie-bez-bazowania.md). */
  const resumedWarn = $("resumed-warn");
  if (st.resumed_without_homing) {
    resumedWarn.textContent =
      "Uwaga: wznowiono po zatrzymaniu BEZ ponownego bazowania — pozycja pochodzi " +
      "z ostatniego bazowania. Obejrzyj maszynę (np. czy materiał się nie zaciął), " +
      "zanim użyjesz JEDŹ DO ZERA albo ruchu ręcznego. Zbazuj ponownie, jeśli masz " +
      "jakiekolwiek wątpliwości co do pozycji osi.";
    resumedWarn.className = "msg warn";
  } else {
    resumedWarn.className = "msg";
  }

  $("order").textContent = st.order_id || "—";
  $("prog-number").textContent = st.program_number || "—";
  $("prog-name").textContent = st.program_name || "—";
  $("pos-x").textContent = fmt(st.position.x);
  $("pos-y").textContent = fmt(st.position.y);
  $("pos-z").textContent = fmt(st.position.z);
  $("spindle").textContent = st.spindle_on ? "ZAŁ" : "WYŁ";
  renderOutputs(st.outputs || {});

  /* Obciążenie osi — podstawa funkcji SMART. Źródło pokazujemy zawsze
     i wprost: „symulacja" to liczby wymyślone przez symulator, nie pomiar.
     Bez tego ktoś dobrałby progi siły na zmyślonych wartościach. */
  const trq = st.torque || {};
  const source = st.torque_source || "brak";
  for (const axis of ["x", "y", "z"]) {
    const el = $("trq-" + axis);
    if (!el) continue;
    el.textContent =
      source === "brak" || trq[axis] == null ? "—" : trq[axis].toFixed(1) + " %";
  }
  const srcEl = $("trq-source");
  if (srcEl) {
    if (source === "sterownik") {
      srcEl.textContent = "źródło: pomiar ze sterownika (TrqMeasured)";
      srcEl.className = "muted";
    } else if (source === "symulacja") {
      srcEl.textContent =
        "źródło: SYMULACJA — wartości wymyślone przez symulator, nie pomiar; " +
        "nie dobieraj na nich progów siły";
      srcEl.className = "msg warn";
    } else {
      srcEl.textContent = "brak odczytu momentu — mostek go jeszcze nie wysyła";
      srcEl.className = "muted";
    }
  }

  const released = st.released_axes || [];
  document.querySelectorAll(".rel").forEach((btn) => {
    const axis = btn.dataset.axis;
    const isReleased =
      axis === "all" ? released.length === 3 : released.includes(axis);
    btn.classList.toggle("released", isReleased);
    const label = axis === "all" ? "WSZYSTKIE" : axis.toUpperCase();
    btn.textContent = isReleased ? label + " — zluzowana" : label;
  });

  document.querySelectorAll("#ops tr").forEach((tr) => {
    const lp = Number(tr.dataset.lp);
    tr.className =
      st.current_op === lp ? "current" : st.current_op && lp < st.current_op ? "done" : "";
  });
  $("progress").textContent = st.current_op
    ? `operacja ${st.current_op} z ${st.total_ops}`
    : "";

  const startBtn = $("btn-start");
  startBtn.textContent = st.state === "PAUSED" ? "WZNÓW" : "START";

  lastStatus = st;
  drawView(st);

  if (st.program_number && (!currentProgram || currentProgram.number !== st.program_number)) {
    loadProgramTable(st.program_number);
  }
}

function connectWs() {
  const ws = new WebSocket(
    (location.protocol === "https:" ? "wss://" : "ws://") + location.host + "/ws/status"
  );
  ws.onmessage = (ev) => applyStatus(JSON.parse(ev.data));
  ws.onclose = () => setTimeout(connectWs, 1000);
}

async function loadProgramTable(number) {
  try {
    const data = await api("GET", `/api/programs/${number}`);
    if (!data.parsed) return;
    currentProgram = data.parsed;
    const tbody = $("ops");
    tbody.innerHTML = "";
    for (const op of currentProgram.operations) {
      const tr = document.createElement("tr");
      tr.dataset.lp = op.lp;
      tr.innerHTML =
        `<td>${op.lp}</td><td>${op.op_type}</td>` +
        `<td>${fmt(op.x)}</td><td>${fmt(op.y)}</td><td>${fmt(op.z)}</td>` +
        `<td>${fmt(op.x2)}</td><td>${fmt(op.y2)}</td><td></td>`;
      tr.lastElementChild.textContent = op.note || "";
      tbody.appendChild(tr);
    }
  } catch (e) {
    /* tabela pozostaje pusta; błąd pokaże się przy próbie startu */
  }
}

// --- sterowanie -----------------------------------------------------------

$("btn-start").onclick = () =>
  api("POST", "/api/machine/start").catch((e) => showMsg($("ctrl-msg"), e.message));
$("btn-stop").onclick = () =>
  api("POST", "/api/machine/stop").catch((e) => showMsg($("ctrl-msg"), e.message));
/* Bazowanie wszystkich osi. Dwa przyciski, jedna akcja: „Bazowanie" przy
   START/STOP i „⌂" na środku strzałek XY (wymóg z notatek funkcjonalnych §1).
   Kolejność osi ustawia ekran /homing — serwer wykonuje ją w symulatorze,
   na sprzęcie całą sekwencję robi serwo po komendzie HOME. */
const homeAll = () =>
  api("POST", "/api/machine/home").catch((e) => showMsg($("ctrl-msg"), e.message));
$("btn-home").onclick = homeAll;
$("btn-home-xy").onclick = homeAll;
/* Dojazd do zera po bazowaniu — ruch pozycyjny, nie ponowne bazowanie
   (maszyna po JOG-u albo cyklu stoi gdzie indziej niż punkt zerowy). */
$("btn-go-to-zero").onclick = () =>
  api("POST", "/api/machine/go-to-zero").catch((e) => showMsg($("ctrl-msg"), e.message));
$("btn-reset").onclick = () =>
  api("POST", "/api/machine/reset").catch((e) => showMsg($("ctrl-msg"), e.message));

/* Wyjścia cyfrowe (podajnik, wyrzutnik, lampka) — operator ma widzieć, co jest
   załączone. Etykiety z konfiguracji maszyny; dopóki się nie wczytają, pokazujemy
   nazwy techniczne, zamiast nie pokazywać nic. */
let outputLabels = {};

function renderOutputs(state) {
  const el = $("outputs-line");
  if (!el) return;
  const entries = Object.entries(state);
  if (!entries.length) {
    el.textContent = "";
    return;
  }
  el.innerHTML = entries
    .map(([name, on]) => {
      const label = outputLabels[name] || name;
      return `${label}: <b>${on ? "ZAŁ" : "wył"}</b>`;
    })
    .join(" &nbsp; ");
}

fetch("/api/outputs")
  .then((r) => (r.ok ? r.json() : null))
  .then((data) => {
    if (!data) return;
    for (const [name, cfg] of Object.entries(data.outputs || {})) {
      outputLabels[name] =
        cfg.label || (cfg.purpose !== "nieuzywane" ? cfg.purpose : name);
    }
  })
  .catch(() => {
    /* brak etykiet nie psuje panelu — zostają nazwy techniczne */
  });

/* Wrzeciono przy starcie maszyny — przełącznik na ekranie Start/Stop
   (notatki funkcjonalne §4). Pozostałe ustawienia wrzeciona (granice programu
   technologa) są na ekranie cyklu maszyny; zapis jest częściowy, więc te dwa
   ekrany sobie nie kasują ustawień. */
async function loadSpindle() {
  try {
    const data = await api("GET", "/api/spindle");
    $("spindle-with-machine").checked = data.spindle.start_with_machine;
    if (data.warnings && data.warnings.length) {
      showMsg($("spindle-msg"), "Uwaga: " + data.warnings.join(" • "));
    } else {
      $("spindle-msg").className = "msg";
    }
  } catch (e) {
    showMsg($("spindle-msg"), "nie udało się wczytać ustawień wrzeciona: " + e.message);
  }
}

$("spindle-with-machine").addEventListener("change", async (ev) => {
  const enabled = ev.target.checked;
  try {
    const data = await api("PUT", "/api/spindle", { start_with_machine: enabled });
    const extra =
      data.warnings && data.warnings.length ? " Uwaga: " + data.warnings.join(" • ") : "";
    showMsg(
      $("spindle-msg"),
      (enabled
        ? "wrzeciono ruszy razem z maszyną"
        : "wrzeciono nie rusza razem z maszyną") + extra,
      !enabled
    );
  } catch (e) {
    ev.target.checked = !enabled; // serwer odmówił — przełącznik wraca
    showMsg($("spindle-msg"), e.message);
  }
});

loadSpindle();

document.querySelectorAll(".rel").forEach((btn) => {
  btn.addEventListener("click", () => {
    // stan docelowy to odwrotność bieżącego, odczytanego ze statusu
    const released = !btn.classList.contains("released");
    api("POST", "/api/machine/release", { axis: btn.dataset.axis, released }).catch((e) =>
      showMsg($("rel-msg"), e.message)
    );
  });
});

// --- JOG: „martwy człowiek" — ruch tylko przy przytrzymanym przycisku -----
/* Temat F w docs/plan-rozwoju.md: przytrzymanie = ruch, puszczenie =
   zatrzymanie. Mostek (i symulator) rozumie tylko ruch o zadany dystans
   (komenda JOG), nie „jedź, dopóki nie każę stanąć" — więc przytrzymanie
   realizujemy powtarzaniem krótkich przejazdów co najmniej co JOG_TICK_MS,
   dopóki przycisk jest wciśnięty. Puszczenie po prostu przestaje wysyłać
   kolejne przejazdy — trwający w tej chwili przejazd jest krótki (krok z
   listy), więc kończy się niemal natychmiast. To wygoda operatora, nie
   certyfikowana funkcja bezpieczeństwa — tę rolę pełni sprzętowy E-stop
   i Global Stop na SC4-Hub. */
const JOG_TICK_MS = 50;
let jogHold = null; // { axis, dir } | null — trzymany w tej chwili przycisk

async function jogLoop(axis, dir) {
  while (jogHold && jogHold.axis === axis && jogHold.dir === dir) {
    const distance = Number($("jog-step").value) * dir;
    const tickStart = performance.now();
    try {
      await api("POST", "/api/machine/jog", { axis, distance });
    } catch (e) {
      showMsg($("ctrl-msg"), e.message);
      jogHold = null;
      break;
    }
    const wait = JOG_TICK_MS - (performance.now() - tickStart);
    if (wait > 0) await new Promise((r) => setTimeout(r, wait));
  }
}

function startJog(btn) {
  if (jogHold) return; // inny przycisk już trzymany — ignorujemy
  const axis = btn.dataset.axis;
  const dir = Number(btn.dataset.dir);
  jogHold = { axis, dir };
  jogLoop(axis, dir);
}

function stopJog() {
  jogHold = null;
}

document.querySelectorAll(".jog").forEach((btn) => {
  btn.addEventListener("mousedown", () => startJog(btn));
  btn.addEventListener("touchstart", (ev) => {
    ev.preventDefault(); // bez tego telefon/tablet dodatkowo emuluje kliknięcie
    startJog(btn);
  });
  btn.addEventListener("mouseleave", stopJog);
  btn.addEventListener("touchend", stopJog);
  btn.addEventListener("touchcancel", stopJog);
});
// siatka bezpieczeństwa: puszczenie poza przyciskiem albo utrata fokusu karty
// (np. alt-tab w trakcie trzymania) też musi zatrzymać ruch
window.addEventListener("mouseup", stopJog);
window.addEventListener("blur", stopJog);

$("btn-mes").onclick = async () => {
  const order = $("mes-order").value.trim();
  const program = $("mes-program").value.trim();
  if (!/^\d{12}$/.test(program)) {
    showMsg($("mes-msg"), "numer programu musi mieć dokładnie 12 cyfr");
    return;
  }
  try {
    const data = await api("POST", "/api/mes/select-order", {
      order_id: order || "TEST",
      program_number: program,
    });
    currentProgram = null; // wymuś przeładowanie tabeli operacji
    showMsg($("mes-msg"), `załadowano program: ${data.program.name}`, true);
  } catch (e) {
    showMsg($("mes-msg"), e.message);
  }
};

// przełącznik zezwolenia dostępny tylko w symulacji
$("sim-enable").onchange = (ev) =>
  api("POST", "/api/sim/safety-enable", { enabled: ev.target.checked }).catch(() => {});

api("POST", "/api/sim/safety-enable", { enabled: true })
  .then(() => {
    simMode = true;
    $("sim-enable-row").style.display = "block";
    $("sim-enable").checked = true;
  })
  .catch(() => {});

// --- podgląd pozycji ------------------------------------------------------
/* Rysunek obszaru roboczego w osiach XY plus wskaźnik osi Z. Odświeżany
   z każdą ramką statusu, więc pokazuje pozycję rzeczywistą (zmierzoną przez
   enkodery), a nie zadaną. */

/* Deklaracja musi stać PRZED initView()/connectWs() na końcu pliku: `const`
   nie jest hoistowane jak `function`, więc wywołanie initView() powyżej tej
   linii kończyło się „Cannot access 'view' before initialization". Skrypt
   przerywał się w tym miejscu, przez co connectWs() już się nie wykonywało —
   panel nie odbierał statusu i pozycja stała w miejscu. */
const view = { cvs: null, ctx: null, area: null, trail: [], prevState: null };

const CSSVAR = (name, fallback) =>
  getComputedStyle(document.documentElement).getPropertyValue(name).trim() || fallback;

async function initView() {
  view.cvs = $("view");
  if (!view.cvs) return;
  view.ctx = view.cvs.getContext("2d");
  // Obszar roboczy skaluje cały rysunek — bez sensownych wartości podgląd
  // zostałby pusty, więc każdy brak pola cofa nas do wartości domyślnych.
  const fallback = { x_min: -100, x_max: 100, y_min: -100, y_max: 100, z_min: -20, z_max: 50 };
  try {
    const a = (await api("GET", "/api/config")).work_area || {};
    const ok = ["x_min", "x_max", "y_min", "y_max", "z_min", "z_max"].every(
      (k) => typeof a[k] === "number"
    );
    view.area = ok ? a : fallback;
  } catch (e) {
    view.area = fallback;
  }
  window.addEventListener("resize", () => drawView(lastStatus));
  drawView(lastStatus);
}

function drawView(st) {
  const c = view.cvs;
  const ctx = view.ctx;
  const area = view.area;
  if (!c || !ctx || !area) return;

  const dpr = window.devicePixelRatio || 1;
  const w = c.clientWidth;
  const h = c.clientHeight;
  if (c.width !== Math.round(w * dpr) || c.height !== Math.round(h * dpr)) {
    c.width = Math.round(w * dpr);
    c.height = Math.round(h * dpr);
  }
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, w, h);

  const muted = CSSVAR("--muted", "#93a1b1");
  const border = CSSVAR("--border", "#33404f");
  const accent = CSSVAR("--accent", "#3aa0ff");
  const warn = CSSVAR("--warn", "#f1c40f");
  const err = CSSVAR("--err", "#e74c3c");

  // układ: rysunek XY z lewej, wskaźnik Z z prawej
  const zW = 78;
  const pad = 26;
  const plotW = w - zW - pad * 2;
  const plotH = h - pad * 2;
  const spanX = area.x_max - area.x_min;
  const spanY = area.y_max - area.y_min;
  const s = Math.min(plotW / spanX, plotH / spanY);
  const ox = pad + (plotW - spanX * s) / 2;
  const oy = pad + (plotH - spanY * s) / 2;
  const X = (mx) => ox + (mx - area.x_min) * s;
  const Y = (my) => oy + (area.y_max - my) * s; // oś Y rośnie w górę

  // siatka co 10 mm (rzadsza, gdy obszar duży)
  const step = spanX > 300 ? 50 : spanX > 120 ? 20 : 10;
  ctx.lineWidth = 1;
  ctx.strokeStyle = border;
  ctx.beginPath();
  for (let v = Math.ceil(area.x_min / step) * step; v <= area.x_max; v += step) {
    ctx.moveTo(Math.round(X(v)) + 0.5, Y(area.y_max));
    ctx.lineTo(Math.round(X(v)) + 0.5, Y(area.y_min));
  }
  for (let v = Math.ceil(area.y_min / step) * step; v <= area.y_max; v += step) {
    ctx.moveTo(X(area.x_min), Math.round(Y(v)) + 0.5);
    ctx.lineTo(X(area.x_max), Math.round(Y(v)) + 0.5);
  }
  ctx.stroke();

  // osie zerowe
  ctx.strokeStyle = muted;
  ctx.globalAlpha = 0.5;
  ctx.beginPath();
  ctx.moveTo(X(area.x_min), Math.round(Y(0)) + 0.5);
  ctx.lineTo(X(area.x_max), Math.round(Y(0)) + 0.5);
  ctx.moveTo(Math.round(X(0)) + 0.5, Y(area.y_max));
  ctx.lineTo(Math.round(X(0)) + 0.5, Y(area.y_min));
  ctx.stroke();
  ctx.globalAlpha = 1;

  // obrys obszaru roboczego
  ctx.strokeStyle = muted;
  ctx.strokeRect(X(area.x_min), Y(area.y_max), spanX * s, spanY * s);
  ctx.fillStyle = muted;
  ctx.font = "11px system-ui, sans-serif";
  ctx.fillText(`${area.x_min}`, X(area.x_min), Y(area.y_min) + 14);
  ctx.fillText(`${area.x_max}`, X(area.x_max) - 20, Y(area.y_min) + 14);
  ctx.fillText(`${area.y_max}`, X(area.x_min) - 22, Y(area.y_max) + 4);
  ctx.fillText(`${area.y_min}`, X(area.x_min) - 22, Y(area.y_min) + 4);

  // operacje programu
  if (currentProgram && currentProgram.operations) {
    for (const op of currentProgram.operations) {
      if (op.x === null || op.y === null) continue;
      const cur = st && st.current_op === op.lp;
      ctx.strokeStyle = cur ? accent : muted;
      ctx.fillStyle = cur ? accent : muted;
      ctx.lineWidth = cur ? 2 : 1;
      if (op.op_type === "LINIA" && op.x2 !== null && op.y2 !== null) {
        ctx.beginPath();
        ctx.moveTo(X(op.x), Y(op.y));
        ctx.lineTo(X(op.x2), Y(op.y2));
        ctx.stroke();
      }
      ctx.beginPath();
      ctx.arc(X(op.x), Y(op.y), cur ? 6 : 4, 0, Math.PI * 2);
      ctx.stroke();
      ctx.globalAlpha = 0.8;
      ctx.fillText(String(op.lp), X(op.x) + 8, Y(op.y) - 6);
      ctx.globalAlpha = 1;
    }
  }

  if (!st) return;
  const px = st.position.x;
  const py = st.position.y;
  const pz = st.position.z;

  // tor przebyty — kasowany przy każdym nowym starcie cyklu
  if (view.prevState !== "RUNNING" && st.state === "RUNNING") view.trail = [];
  view.prevState = st.state;
  const lastPt = view.trail[view.trail.length - 1];
  if (!lastPt || Math.abs(lastPt.x - px) > 0.05 || Math.abs(lastPt.y - py) > 0.05) {
    view.trail.push({ x: px, y: py });
    if (view.trail.length > 600) view.trail.shift();
  }
  if (view.trail.length > 1) {
    ctx.strokeStyle = "#2b6ea8";
    ctx.lineWidth = 2;
    ctx.beginPath();
    view.trail.forEach((p, i) => (i ? ctx.lineTo(X(p.x), Y(p.y)) : ctx.moveTo(X(p.x), Y(p.y))));
    ctx.stroke();
  }

  // narzędzie: krzyż + punkt, kolor zależny od stanu
  const toolColor = st.state === "ALARM" ? err : st.state === "RUNNING" ? accent : warn;
  ctx.strokeStyle = toolColor;
  ctx.fillStyle = toolColor;
  ctx.lineWidth = 1;
  ctx.globalAlpha = 0.55;
  ctx.beginPath();
  ctx.moveTo(X(area.x_min), Math.round(Y(py)) + 0.5);
  ctx.lineTo(X(area.x_max), Math.round(Y(py)) + 0.5);
  ctx.moveTo(Math.round(X(px)) + 0.5, Y(area.y_max));
  ctx.lineTo(Math.round(X(px)) + 0.5, Y(area.y_min));
  ctx.stroke();
  ctx.globalAlpha = 1;
  ctx.beginPath();
  ctx.arc(X(px), Y(py), 6, 0, Math.PI * 2);
  ctx.fill();
  if (st.spindle_on) {
    ctx.strokeStyle = toolColor;
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.arc(X(px), Y(py), 11, 0, Math.PI * 2);
    ctx.stroke();
  }

  // --- wskaźnik osi Z ---
  const zx = w - zW + 18;
  const zTop = pad;
  const zBot = h - pad;
  const zSpan = area.z_max - area.z_min;
  const Z = (mz) => zBot - ((mz - area.z_min) / zSpan) * (zBot - zTop);

  ctx.strokeStyle = border;
  ctx.lineWidth = 1;
  ctx.strokeRect(zx, zTop, 16, zBot - zTop);
  ctx.fillStyle = muted;
  ctx.fillText("Z", zx + 2, zTop - 8);
  ctx.fillText(`${area.z_max}`, zx + 22, zTop + 4);
  ctx.fillText(`${area.z_min}`, zx + 22, zBot + 4);

  // poziom zera Z
  ctx.strokeStyle = muted;
  ctx.globalAlpha = 0.6;
  ctx.beginPath();
  ctx.moveTo(zx, Math.round(Z(0)) + 0.5);
  ctx.lineTo(zx + 16, Math.round(Z(0)) + 0.5);
  ctx.stroke();
  ctx.globalAlpha = 1;

  // słupek od zera do bieżącej pozycji + znacznik
  ctx.fillStyle = toolColor;
  ctx.globalAlpha = 0.35;
  const zNow = Z(pz);
  ctx.fillRect(zx + 1, Math.min(zNow, Z(0)), 14, Math.abs(zNow - Z(0)));
  ctx.globalAlpha = 1;
  ctx.fillRect(zx - 3, Math.round(zNow) - 1.5, 22, 3);

  // odczyt liczbowy przy podglądzie
  const info = $("view-info");
  if (info) {
    const rel = (st.released_axes || []).map((a) => a.toUpperCase()).join(", ");
    info.textContent =
      `X ${fmt(px)}   Y ${fmt(py)}   Z ${fmt(pz)} mm` + (rel ? `   •  zluzowane: ${rel}` : "");
  }
}

// --- start ----------------------------------------------------------------
/* Na samym końcu, po wszystkich deklaracjach — patrz komentarz przy `view`. */
initView();
connectWs();
