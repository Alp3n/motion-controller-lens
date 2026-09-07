/* Ekran "prowadzenie za rękę" — przybliżenie trybu podatnego bez trybu
 * momentu w SDK (docs/prowadzenie-za-reke.md): niski limit momentu +
 * doganianie wykrytego odchylenia pozycji. Przeglądarka woła
 * /api/machine/hand-guide/tick w pętli, dopóki przycisk osi jest aktywny —
 * to jest zabezpieczenie "martwego człowieka" (jak przytrzymanie JOG):
 * zamknięcie karty albo utrata sieci po prostu kończy prowadzenie.
 */

const $ = (id) => document.getElementById(id);

const NAME_RE = /^[^\W\d_][\w-]*$/u;
const TICK_MS = 150;

let lastStatus = null;
let activeAxis = null;   // oś aktualnie prowadzona, albo null
let tickTimer = null;

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

function showMsg(el, text, ok = false) {
  el.textContent = text;
  el.className = "msg " + (ok ? "ok" : "err");
}

function fmt(v) {
  return v === null || v === undefined ? "—" : Number(v).toFixed(3);
}

// --- status na żywo ----------------------------------------------------

function applyStatus(st) {
  lastStatus = st;
  $("pos-x").textContent = fmt(st.position.x);
  $("pos-y").textContent = fmt(st.position.y);
  $("pos-z").textContent = fmt(st.position.z);
}

async function pollStatus() {
  try {
    applyStatus(await api("GET", "/api/status"));
  } catch (e) {
    /* chwilowy brak statusu nie blokuje ekranu */
  }
}

// --- prowadzenie za rękę -------------------------------------------------

function setButtonsUi() {
  document.querySelectorAll(".guide").forEach((btn) => {
    const on = btn.dataset.axis === activeAxis;
    btn.classList.toggle("active", on);
    btn.textContent = (on ? "Zakończ " : "Prowadź ") + btn.dataset.axis.toUpperCase();
  });
}

async function tick() {
  if (!activeAxis) return;
  try {
    const r = await api("POST", "/api/machine/hand-guide/tick");
    $(`pos-${r.axis}`).textContent = fmt(r.position);
    showMsg($("guide-msg"), `moment: ${fmt(r.torque)}%` + (r.moving ? " — w ruchu" : ""), true);
  } catch (e) {
    showMsg($("guide-msg"), "przerwano: " + e.message);
    await stopGuiding(false);
    return;
  }
  tickTimer = setTimeout(tick, TICK_MS);
}

async function startGuiding(axis) {
  const torque = Number($("f-torque").value);
  try {
    await api("POST", "/api/machine/hand-guide/start", { axis, torque_pct: torque });
  } catch (e) {
    showMsg($("guide-msg"), "nie uruchomiono — " + e.message);
    return;
  }
  activeAxis = axis;
  setButtonsUi();
  showMsg($("guide-msg"), `prowadzenie osi ${axis.toUpperCase()} aktywne`, true);
  tick();
}

async function stopGuiding(callServer = true) {
  clearTimeout(tickTimer);
  activeAxis = null;
  setButtonsUi();
  if (callServer) {
    try {
      await api("POST", "/api/machine/hand-guide/stop");
    } catch (e) {
      /* zakończenie i tak lokalnie zatrzymuje pętlę */
    }
  }
}

document.querySelectorAll(".guide").forEach((btn) => {
  btn.addEventListener("click", () => {
    const axis = btn.dataset.axis;
    if (activeAxis === axis) {
      stopGuiding();
    } else if (activeAxis) {
      showMsg($("guide-msg"), `najpierw zakończ prowadzenie osi ${activeAxis.toUpperCase()}`);
    } else {
      startGuiding(axis);
    }
  });
});

window.addEventListener("beforeunload", () => {
  if (activeAxis) navigator.sendBeacon?.("/api/machine/hand-guide/stop");
});

// --- zapis punktu -----------------------------------------------------------

$("btn-save").onclick = async () => {
  const name = $("f-name").value.trim();
  if (!NAME_RE.test(name)) {
    showMsg($("save-msg"), "nazwa: zacznij od litery, dalej litery, cyfry, podkreślenie albo myślnik");
    return;
  }
  if (!lastStatus) {
    showMsg($("save-msg"), "brak aktualnej pozycji — spróbuj ponownie za chwilę");
    return;
  }
  try {
    const current = await api("GET", "/api/punkty");
    const points = { ...current.points };
    const existed = name in points;
    points[name] = {
      x: lastStatus.position.x,
      y: lastStatus.position.y,
      z: lastStatus.position.z,
      note: points[name] ? points[name].note : "",
    };
    await api("PUT", "/api/punkty", { points });
    showMsg(
      $("save-msg"),
      (existed ? `nadpisano punkt „${name}"` : `zapisano nowy punkt „${name}"`) +
        ` (${fmt(points[name].x)}, ${fmt(points[name].y)}, ${fmt(points[name].z)})`,
      true
    );
  } catch (e) {
    showMsg($("save-msg"), "nie zapisano — " + e.message);
  }
};

pollStatus();
setInterval(pollStatus, 1000);
