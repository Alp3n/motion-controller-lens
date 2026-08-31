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
