/* Ekran konfiguracji bazowania — kolejność osi, sposób bazowania i parametry,
   które fizycznie żyją w serwie (ClearView). Walidacja jest powtórzona po
   stronie serwera (app/axes.py); tutaj chodzi o to, żeby admin zobaczył błąd
   zanim kliknie zapis. */

const $ = (id) => document.getElementById(id);

const MODE_LABELS = {
  hardstop: "HardStop — dojazd do oporu",
  programowe: "programowe — zerowanie pozycji",
};

let saved = null;      // ostatnia konfiguracja potwierdzona przez serwer
let axisNames = [];    // kolejność wyświetlania, z serwera
let requiredAxes = ["x", "y", "z"];
let modes = ["hardstop", "programowe"];
let machineBusy = false;

function num(value) {
  const v = String(value).trim().replace(",", ".");
  return v === "" ? NaN : Number(v);
}

function showMsg(el, text, ok = false) {
  el.textContent = text;
  el.className = "msg " + (ok ? "ok" : "err");
  el.style.whiteSpace = "pre-line";
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

// --- tabela ---------------------------------------------------------------

function buildRows() {
  const tbody = $("homing-rows");
  tbody.innerHTML = "";
  for (const axis of axisNames) {
    const options = modes
      .map((m) => `<option value="${m}">${MODE_LABELS[m] || m}</option>`)
      .join("");
    const extra = requiredAxes.includes(axis)
      ? ""
      : ` <span class="axis-extra-badge" title="Mostek nie zna komend ruchu dla` +
        ` tej osi — nie pojedzie, nawet z ustawioną kolejnością.">tylko konfiguracja</span>`;
    const tr = document.createElement("tr");
    tr.dataset.axis = axis;
    tr.innerHTML =
      `<td style="font-size:20px; font-weight:700; white-space:nowrap">` +
      `${axis.toUpperCase()}${extra}</td>` +
      `<td><input id="h-${axis}-order" type="number" step="1" min="0" style="width:80px"></td>` +
      `<td><select id="h-${axis}-mode">${options}</select></td>` +
      `<td><input id="h-${axis}-torque" type="number" step="1" min="0" max="100"></td>` +
      `<td><input id="h-${axis}-offset" type="number" step="0.1"></td>` +
      `<td><input id="h-${axis}-velhome" type="number" step="1" min="0"></td>` +
      `<td class="muted" id="h-${axis}-point"></td>`;
    tbody.appendChild(tr);
    tr.querySelectorAll("input, select").forEach((el) => {
      el.addEventListener("input", refresh);
      el.addEventListener("change", refresh);
    });
  }
}

function readAxis(axis) {
  return {
    home_order: num($(`h-${axis}-order`).value),
    home_mode: $(`h-${axis}-mode`).value,
    home_torque: num($(`h-${axis}-torque`).value),
    home_offset: num($(`h-${axis}-offset`).value),
    vel_home: num($(`h-${axis}-velhome`).value),
  };
}

function writeAxis(axis, cfg) {
  $(`h-${axis}-order`).value = cfg.home_order;
  $(`h-${axis}-mode`).value = cfg.home_mode;
  $(`h-${axis}-torque`).value = cfg.home_torque;
  $(`h-${axis}-offset`).value = cfg.home_offset;
  $(`h-${axis}-velhome`).value = cfg.vel_home;
}

// --- walidacja i podgląd --------------------------------------------------

/* Lustro AxisConfig.validate() z app/axes.py — te same warunki i komunikaty. */
function validateAxis(axis, cfg) {
  const label = `oś ${axis.toUpperCase()}`;
  const bad = [];
  if (!Number.isInteger(cfg.home_order) || cfg.home_order < 0) {
    bad.push([`h-${axis}-order`, `${label}: kolejność bazowania to liczba całkowita ≥ 0`]);
  }
  if (!(cfg.home_torque > 0 && cfg.home_torque <= 100)) {
    bad.push([`h-${axis}-torque`, `${label}: limit momentu musi być w zakresie (0, 100] %`]);
  }
  if (Number.isNaN(cfg.home_offset)) {
    bad.push([`h-${axis}-offset`, `${label}: podaj offset (0, jeśli żadnego nie ma)`]);
  }
  if (!(cfg.vel_home > 0)) {
    bad.push([`h-${axis}-velhome`, `${label}: prędkość bazowania musi być większa od zera`]);
  }
  return bad;
}

/* Kolejność, jaka wyjdzie z wpisanych numerów — ta sama zasada co
   home_groups() w app/axes.py: grupy rosnąco, w grupie osie razem. */
function drawPlan() {
  const list = $("homing-plan");
  list.innerHTML = "";
  const groups = new Map();
  for (const axis of axisNames) {
    const order = readAxis(axis).home_order;
    if (!(order > 0)) continue;
    if (!groups.has(order)) groups.set(order, []);
    groups.get(order).push(axis);
  }

  const lift = document.createElement("li");
  lift.innerHTML = "<b>Z</b> — odjazd w górę na wysokość bezpieczną " +
    "<span class='muted'>(zawsze, niezależnie od kolejności)</span>";
  list.appendChild(lift);

  if (!groups.size) {
    const none = document.createElement("li");
    none.className = "muted";
    none.textContent = "— żadna oś nie ma ustawionej kolejności: bazowanie nic nie zrobi";
    list.appendChild(none);
    return;
  }
  for (const order of [...groups.keys()].sort((a, b) => a - b)) {
    const axesInGroup = groups.get(order).sort();
    const skipped = axesInGroup.filter((a) => !requiredAxes.includes(a));
    const li = document.createElement("li");
    li.innerHTML =
      `<b>${axesInGroup.map((a) => a.toUpperCase()).join(" + ")}</b>` +
      ` — dojazd do zera osi` +
      (skipped.length
        ? ` <span class="msg err" style="display:inline">(${skipped
            .map((a) => a.toUpperCase())
            .join(", ")} nie pojedzie — brak komend ruchu)</span>`
        : "");
    list.appendChild(li);
  }
}

function refresh() {
  const errors = [];
  document.querySelectorAll("#homing-rows input, #homing-rows select").forEach((el) =>
    el.classList.remove("bad")
  );
  for (const axis of axisNames) {
    for (const [id, message] of validateAxis(axis, readAxis(axis))) {
      $(id).classList.add("bad");
      errors.push(message);
    }
  }
  drawPlan();

  const msg = $("homing-msg");
  $("btn-save").disabled = errors.length > 0 || machineBusy;
  if (errors.length) {
    showMsg(msg, errors.join("\n"));
  } else if (machineBusy) {
    showMsg(msg, "maszyna w ruchu — zapis konfiguracji bazowania jest zablokowany");
  } else {
    msg.className = "msg";
  }
  return errors.length === 0;
}

// --- serwer ---------------------------------------------------------------

function applyHoming(data, axisPoints) {
  saved = data.axes;
  axisNames = Object.keys(saved);
  if (data.required_axes) requiredAxes = data.required_axes;
  if (data.modes) modes = data.modes;
  buildRows();
  for (const axis of axisNames) writeAxis(axis, saved[axis]);
  if (axisPoints) {
    for (const axis of axisNames) {
      const cell = $(`h-${axis}-point`);
      if (cell && axisPoints[axis]) cell.textContent = axisPoints[axis].home;
    }
  }
  $("homing-file").textContent = "Plik konfiguracji: " + data.file;
  refresh();
  if (data.warnings && data.warnings.length) {
    showMsg($("homing-msg"), "Uwaga:\n" + data.warnings.join("\n"));
  }
}

async function loadHoming() {
  /* Punkt bazowania (minus/plus/środek) należy do ekranu konfiguracji osi —
     tu pokazujemy go tylko do odczytu, żeby było widać, dokąd oś dojedzie. */
  const [homing, axesData] = await Promise.all([
    api("GET", "/api/homing"),
    api("GET", "/api/axes").catch(() => null),
  ]);
  applyHoming(homing, axesData && axesData.axes);
}

async function save() {
  if (!refresh()) return;
  const payload = { axes: {} };
  for (const axis of axisNames) payload.axes[axis] = readAxis(axis);
  try {
    const data = await api("PUT", "/api/homing", payload);
    const axesData = await api("GET", "/api/axes").catch(() => null);
    applyHoming(data, axesData && axesData.axes);
    const extra =
      data.warnings && data.warnings.length ? "\nUwaga:\n" + data.warnings.join("\n") : "";
    showMsg($("homing-msg"), "zapisano konfigurację bazowania" + extra, true);
  } catch (e) {
    showMsg($("homing-msg"), e.message);
  }
}

async function pollState() {
  try {
    const st = await api("GET", "/api/status");
    const busy = st.state === "RUNNING" || st.state === "HOMING";
    if (busy !== machineBusy) {
      machineBusy = busy;
      refresh();
    }
  } catch (e) {
    /* brak statusu nie blokuje edycji — zapis i tak sprawdzi serwer */
  }
}

$("btn-save").onclick = save;
$("btn-reload").onclick = () =>
  loadHoming().catch((e) => showMsg($("homing-msg"), e.message));

loadHoming().catch((e) =>
  showMsg($("homing-msg"), "nie udało się wczytać konfiguracji bazowania: " + e.message)
);

pollState();
setInterval(pollState, 1500);
