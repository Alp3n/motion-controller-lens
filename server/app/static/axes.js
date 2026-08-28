/* Ekran konfiguracji osi — długości, punkty bazowania, limity, przełożenia.
   Walidacja jest powtórzona po stronie serwera (app/axes.py); tutaj chodzi
   o to, żeby technolog zobaczył błąd zanim kliknie zapis. */

const $ = (id) => document.getElementById(id);

/* X/Y/Z są wymagane zawsze — geometria cięcia .prg jest w nich zdefiniowana
   (patrz REQUIRED_AXES w app/axes.py). Osie dodatkowe (podajnik, docisk...)
   admin może dopisać z tego ekranu, ale to dziś WYŁĄCZNIE zapis w pliku
   konfiguracji — mostek do sterownika zna komendy ruchu tylko dla X/Y/Z,
   więc dodatkowa oś nigdzie fizycznie nie pojedzie. Patrz docs/plan-rozwoju.md,
   temat C, i docs/zmiany/osie-dodatkowe-etap1.md. */
const REQUIRED_AXES = ["x", "y", "z"];
const AXIS_NAME_RE = /^[a-z][a-z0-9_]*$/;
const HOME_LABELS = {
  minus: "minus — zero na końcu −",
  plus: "plus — zero na końcu +",
  srodek: "środek osi",
};
// te same liczby co DEFAULT_VEL_JOG/DEFAULT_VEL_HOME w app/axes.py — awaryjny
// fallback, gdyby odpowiedź serwera nie miała tych pól (np. stary proces
// serwera sprzed tego pola, nieprzeładowany po git pull)
const FALLBACK_VEL_JOG = 500;
const FALLBACK_VEL_HOME = 1000;

let saved = null; // ostatnia konfiguracja potwierdzona przez serwer
let machineBusy = false; // RUNNING/HOMING — zapis odrzucany przez serwer
let homePoints = ["minus", "plus", "srodek"];
let extraAxes = []; // dodatkowe osie ponad X/Y/Z, w kolejności wyświetlania

function allAxes() {
  return REQUIRED_AXES.concat(extraAxes);
}

function num(value) {
  const v = String(value).trim().replace(",", ".");
  return v === "" ? NaN : Number(v);
}

function mm(v) {
  return Number(v).toFixed(3).replace(/\.?0+$/, "");
}

function showMsg(el, text, ok = false) {
  el.textContent = text;
  el.className = "msg " + (ok ? "ok" : "err");
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

// --- model ----------------------------------------------------------------

/* Zakres fizyczny osi — musi odpowiadać physical_range() z app/axes.py. */
function physRange(cfg) {
  if (cfg.home === "minus") return [0, cfg.length];
  if (cfg.home === "plus") return [-cfg.length, 0];
  return [-cfg.length / 2, cfg.length / 2];
}

function readAxis(axis) {
  return {
    length: num($(`f-${axis}-length`).value),
    home: $(`f-${axis}-home`).value,
    soft_min: num($(`f-${axis}-min`).value),
    soft_max: num($(`f-${axis}-max`).value),
    mm_per_rev: num($(`f-${axis}-mmrev`).value),
    vel_jog: num($(`f-${axis}-veljog`).value),
    vel_home: num($(`f-${axis}-velhome`).value),
  };
}

function writeAxis(axis, cfg) {
  $(`f-${axis}-length`).value = cfg.length;
  $(`f-${axis}-home`).value = cfg.home;
  $(`f-${axis}-min`).value = cfg.soft_min;
  $(`f-${axis}-max`).value = cfg.soft_max;
  $(`f-${axis}-mmrev`).value = cfg.mm_per_rev;
  $(`f-${axis}-veljog`).value = cfg.vel_jog ?? FALLBACK_VEL_JOG;
  $(`f-${axis}-velhome`).value = cfg.vel_home ?? FALLBACK_VEL_HOME;
}

// --- budowa tabeli --------------------------------------------------------

function buildRows(axisNames) {
  $("axis-rows").innerHTML = "";
  for (const axis of axisNames) addAxisRow(axis, !REQUIRED_AXES.includes(axis));
}

function addAxisRow(axis, extra) {
  const tbody = $("axis-rows");
  const tr = document.createElement("tr");
  tr.dataset.axis = axis;
  const options = homePoints
    .map((h) => `<option value="${h}">${HOME_LABELS[h] || h}</option>`)
    .join("");
  const nameCell = extra
    ? `${axis.toUpperCase()} <span class="axis-extra-badge" ` +
      `title="Zapisuje się w konfiguracji, ale mostek do sterownika nie zna ` +
      `jeszcze komend ruchu dla tej osi — dziś jeździ tylko X/Y/Z.">tylko konfiguracja</span>`
    : axis.toUpperCase();
  const actions = extra
    ? `<button class="small icon" title="usuń oś" data-action="remove-axis">✕</button>`
    : "";
  tr.innerHTML =
    `<td style="font-size:20px; font-weight:700; white-space:nowrap">${nameCell}</td>` +
    `<td><input id="f-${axis}-length" type="number" step="0.1" min="0"></td>` +
    `<td><select id="f-${axis}-home">${options}</select></td>` +
    `<td class="muted" id="f-${axis}-phys" style="white-space:nowrap"></td>` +
    `<td><input id="f-${axis}-min" type="number" step="0.1"></td>` +
    `<td><input id="f-${axis}-max" type="number" step="0.1"></td>` +
    `<td><input id="f-${axis}-mmrev" type="number" step="0.001" min="0"></td>` +
    `<td><input id="f-${axis}-veljog" type="number" step="1" min="0"></td>` +
    `<td><input id="f-${axis}-velhome" type="number" step="1" min="0"></td>` +
    `<td class="row-actions">${actions}</td>`;
  tbody.appendChild(tr);
  tr.querySelectorAll("input, select").forEach((el) => {
    el.addEventListener("input", refresh);
    el.addEventListener("change", refresh);
  });
  const removeBtn = tr.querySelector('[data-action="remove-axis"]');
  if (removeBtn) removeBtn.onclick = () => removeAxis(axis);
}

/* Usunięcie jest tylko lokalne, dopóki admin nie kliknie „Zapisz konfigurację" —
   ten sam wzorzec co dodanie: zmiana trafia do pliku dopiero świadomym zapisem. */
function removeAxis(axis) {
  extraAxes = extraAxes.filter((a) => a !== axis);
  const tr = $("axis-rows").querySelector(`tr[data-axis="${axis}"]`);
  if (tr) tr.remove();
  refresh();
}

function addNewAxis() {
  const input = $("new-axis-name");
  const msg = $("new-axis-msg");
  const raw = input.value.trim().toLowerCase();

  if (!AXIS_NAME_RE.test(raw)) {
    showMsg(msg, "nazwa osi: małe litery, cyfry, podkreślenie, zaczynając od litery");
    return;
  }
  if (allAxes().includes(raw)) {
    showMsg(msg, `oś „${raw.toUpperCase()}" już istnieje`);
    return;
  }

  extraAxes.push(raw);
  addAxisRow(raw, true);
  // wartości startowe, żeby nowy wiersz nie był od razu czerwony od pustych pól
  writeAxis(raw, {
    length: 100,
    home: "srodek",
    soft_min: -50,
    soft_max: 50,
    mm_per_rev: 5,
    vel_jog: FALLBACK_VEL_JOG,
    vel_home: FALLBACK_VEL_HOME,
  });
  input.value = "";
  msg.className = "msg";
  refresh();
}

// --- walidacja i podgląd --------------------------------------------------

function validateAxis(axis, cfg) {
  const label = `oś ${axis.toUpperCase()}`;
  const bad = [];
  if (!(cfg.length > 0)) {
    bad.push([`f-${axis}-length`, `${label}: długość fizyczna musi być większa od zera`]);
  }
  if (!(cfg.mm_per_rev > 0)) {
    bad.push([`f-${axis}-mmrev`, `${label}: przełożenie (mm na obrót) musi być większe od zera`]);
  }
  if (!(cfg.vel_jog > 0)) {
    bad.push([`f-${axis}-veljog`, `${label}: prędkość JOG musi być większa od zera`]);
  }
  if (!(cfg.vel_home > 0)) {
    bad.push([`f-${axis}-velhome`, `${label}: prędkość bazowania musi być większa od zera`]);
  }
  if (Number.isNaN(cfg.soft_min)) bad.push([`f-${axis}-min`, `${label}: podaj limit MIN`]);
  if (Number.isNaN(cfg.soft_max)) bad.push([`f-${axis}-max`, `${label}: podaj limit MAX`]);
  if (bad.length) return bad;

  if (cfg.soft_min >= cfg.soft_max) {
    return [
      [`f-${axis}-min`, `${label}: limit MIN musi być mniejszy od MAX`],
      [`f-${axis}-max`, ""],
    ];
  }
  const [lo, hi] = physRange(cfg);
  const out = [];
  if (cfg.soft_min < lo - 1e-6) {
    out.push([`f-${axis}-min`, `${label}: limit MIN poza zakresem fizycznym (${mm(lo)}..${mm(hi)})`]);
  }
  if (cfg.soft_max > hi + 1e-6) {
    out.push([`f-${axis}-max`, `${label}: limit MAX poza zakresem fizycznym (${mm(lo)}..${mm(hi)})`]);
  }
  return out;
}

function refresh() {
  const errors = [];
  const notes = [];
  document.querySelectorAll("#axis-rows input, #axis-rows select").forEach((el) =>
    el.classList.remove("bad")
  );

  for (const axis of allAxes()) {
    const cfg = readAxis(axis);
    const physCell = $(`f-${axis}-phys`);
    if (cfg.length > 0) {
      const [lo, hi] = physRange(cfg);
      physCell.textContent = `${mm(lo)} … ${mm(hi)}`;
    } else {
      physCell.textContent = "—";
    }

    for (const [id, message] of validateAxis(axis, cfg)) {
      $(id).classList.add("bad");
      if (message) errors.push(message);
    }
    if (!Number.isNaN(cfg.soft_min) && !Number.isNaN(cfg.soft_max)) {
      if (!(cfg.soft_min <= 0 && 0 <= cfg.soft_max)) {
        notes.push(
          `oś ${axis.toUpperCase()}: punkt bazowania (zero) leży poza limitami ` +
            `programowymi — po bazowaniu maszyna stanie poza dozwolonym zakresem`
        );
      }
    }
  }

  drawBars();

  const msg = $("axes-msg");
  const saveBtn = $("btn-save");
  saveBtn.disabled = errors.length > 0 || machineBusy;
  if (errors.length) {
    showMsg(msg, errors.join("\n"));
    msg.style.whiteSpace = "pre-line";
  } else if (machineBusy) {
    showMsg(msg, "maszyna w ruchu — zapis konfiguracji osi jest zablokowany");
  } else if (notes.length) {
    showMsg(msg, "Uwaga:\n" + notes.join("\n"));
    msg.style.whiteSpace = "pre-line";
  } else {
    msg.className = "msg";
  }
  return errors.length === 0;
}

/* Pasek zakresu: cała szerokość to zakres fizyczny, wypełnienie to obszar
   dozwolony programowo. Operator widzi na oko, ile z osi faktycznie oddał
   do dyspozycji programom. */
function drawBars() {
  const wrap = $("axis-bars");
  wrap.innerHTML = "";
  for (const axis of allAxes()) {
    const cfg = readAxis(axis);
    if (!(cfg.length > 0)) continue;
    const [lo, hi] = physRange(cfg);
    const span = hi - lo;
    const clamp = (v) => Math.max(0, Math.min(100, ((v - lo) / span) * 100));
    const softLo = Number.isNaN(cfg.soft_min) ? lo : cfg.soft_min;
    const softHi = Number.isNaN(cfg.soft_max) ? hi : cfg.soft_max;

    const row = document.createElement("div");
    row.className = "axis-bar-row";
    row.innerHTML =
      `<span class="axis-bar-name">${axis.toUpperCase()}</span>` +
      `<span class="axis-bar-end">${mm(lo)}</span>` +
      `<span class="axis-bar">` +
      `<span class="axis-bar-soft" style="left:${clamp(softLo)}%; width:${
        Math.max(0, clamp(softHi) - clamp(softLo))
      }%"></span>` +
      `<span class="axis-bar-zero" style="left:${clamp(0)}%"></span>` +
      `</span>` +
      `<span class="axis-bar-end">${mm(hi)}</span>` +
      `<span class="muted" style="min-width:190px">limity ${mm(softLo)} … ${mm(softHi)} mm` +
      `<br>${mm(cfg.mm_per_rev)} mm/obrót</span>`;
    wrap.appendChild(row);
  }
}

// --- serwer ---------------------------------------------------------------

/* Zawsze przebudowuje tabelę od zera z tego, co potwierdził serwer — także
   po zapisie. Dzięki temu „Przywróć zapisane" poprawnie odrzuca lokalnie
   dodane/usunięte wiersze, których admin nie zapisał, a kolejność osi
   dodatkowych jest zawsze zgodna z plikiem konfiguracji. */
function applyAxes(data) {
  saved = data.axes;
  if (data.home_points) homePoints = data.home_points;
  extraAxes = Object.keys(saved)
    .filter((a) => !REQUIRED_AXES.includes(a))
    .sort();
  buildRows(allAxes());
  for (const axis of allAxes()) writeAxis(axis, saved[axis]);
  $("axes-file").textContent = "Plik konfiguracji: " + data.file;
  refresh();
  if (data.warnings && data.warnings.length) {
    showMsg($("axes-msg"), "Uwaga:\n" + data.warnings.join("\n"));
    $("axes-msg").style.whiteSpace = "pre-line";
  }
}

async function loadAxes() {
  applyAxes(await api("GET", "/api/axes"));
}

async function save() {
  if (!refresh()) return;
  const payload = { axes: {} };
  for (const axis of allAxes()) payload.axes[axis] = readAxis(axis);
  try {
    const data = await api("PUT", "/api/axes", payload);
    applyAxes(data);
    const extra = data.warnings && data.warnings.length ? "\nUwaga:\n" + data.warnings.join("\n") : "";
    showMsg($("axes-msg"), "zapisano konfigurację osi" + extra, true);
    $("axes-msg").style.whiteSpace = "pre-line";
  } catch (e) {
    showMsg($("axes-msg"), e.message);
  }
}

/* Skrót przy pierwszym uruchamianiu maszyny: limity programowe równe całemu
   zakresowi fizycznemu. Świadomie osobny przycisk, a nie wartość domyślna —
   zawężenie limitów jest normalną praktyką, a nie wyjątkiem. */
function limitsToPhysical() {
  for (const axis of allAxes()) {
    const cfg = readAxis(axis);
    if (!(cfg.length > 0)) continue;
    const [lo, hi] = physRange(cfg);
    $(`f-${axis}-min`).value = lo;
    $(`f-${axis}-max`).value = hi;
  }
  refresh();
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
$("btn-reload").onclick = () => loadAxes().catch((e) => showMsg($("axes-msg"), e.message));
$("btn-full").onclick = limitsToPhysical;
$("btn-add-axis").onclick = addNewAxis;
$("new-axis-name").addEventListener("keydown", (ev) => {
  if (ev.key === "Enter") addNewAxis();
});

loadAxes().catch((e) =>
  showMsg($("axes-msg"), "nie udało się wczytać konfiguracji: " + e.message)
);

pollState();
setInterval(pollState, 1500);
