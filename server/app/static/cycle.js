/* Ekran cyklu maszyny — kroki poziomu admina wokół programu detalu.
   Walidacja jest powtórzona po stronie serwera (app/cycle.py); tutaj chodzi
   o to, żeby admin zobaczył błąd zanim kliknie zapis. Układ i konwencje jak
   w edytorze technologa (editor.js). */

const $ = (id) => document.getElementById(id);

/* Które pola ma sens wypełniać przy danym rodzaju kroku. Musi odpowiadać
   CycleStep.validate() z app/cycle.py — rozjazd oznaczałby, że ekran
   pozwala zapisać coś, co serwer odrzuci. */
const STEP_SCHEMA = {
  RUCH: { uses: ["profile", "x", "y", "z", "feed"] },
  PROGRAM: { uses: ["profile"] },
  WYJSCIE: { uses: ["profile", "output", "output_on"] },
  PAUZA: { uses: [] },
};
const STEP_KINDS = Object.keys(STEP_SCHEMA);
const AXES = ["x", "y", "z"];
const NUM_FIELDS = [...AXES, "feed"];

let profileNames = [];
let outputNames = [];
let axesCfg = null;
let machineBusy = false;

function num(value) {
  const v = String(value).trim().replace(",", ".");
  return v === "" ? null : Number(v);
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

function iconBtn(label, title, onClick) {
  const b = document.createElement("button");
  b.className = "small icon";
  b.textContent = label;
  b.title = title;
  b.onclick = onClick;
  return b;
}

function selectCell(field, options, value, labels = null) {
  const s = document.createElement("select");
  for (const o of options) {
    const opt = document.createElement("option");
    opt.value = o;
    opt.textContent = labels ? labels[o] || o : o;
    s.appendChild(opt);
  }
  if (value != null) s.value = value;
  s.dataset.field = field;
  s.onchange = onEdit;
  return s;
}

// --- budowa wiersza -------------------------------------------------------

function addStepRow(step = {}, after = null) {
  const tbody = $("step-rows");
  const tr = document.createElement("tr");

  const lpTd = document.createElement("td");

  const kindTd = document.createElement("td");
  const kindSel = selectCell("kind", STEP_KINDS, step.kind || "RUCH");
  kindSel.onchange = () => {
    applyRowSchema(tr);
    onEdit();
  };
  kindTd.appendChild(kindSel);

  // profil: pusty = zostaw aktywny
  const profTd = document.createElement("td");
  profTd.appendChild(
    selectCell("profile", ["", ...profileNames], step.profile || "", {
      "": "— aktywny —",
    })
  );

  const targets = step.targets || {};
  const numTds = NUM_FIELDS.map((f) => {
    const td = document.createElement("td");
    const input = document.createElement("input");
    input.type = "number";
    input.step = f === "feed" ? "1" : "0.1";
    input.dataset.field = f;
    const value = f === "feed" ? step.feed : targets[f];
    input.value = value == null ? "" : value;
    input.oninput = onEdit;
    td.appendChild(input);
    return td;
  });

  const outTd = document.createElement("td");
  outTd.appendChild(
    selectCell("output", ["", ...outputNames], step.output || "", { "": "—" })
  );

  const stateTd = document.createElement("td");
  const stateValue = step.output_on == null ? "" : step.output_on ? "1" : "0";
  stateTd.appendChild(
    selectCell("output_on", ["", "1", "0"], stateValue, {
      "": "—",
      1: "załącz",
      0: "wyłącz",
    })
  );

  const noteTd = document.createElement("td");
  const noteInput = document.createElement("input");
  noteInput.value = step.note || "";
  noteInput.dataset.field = "note";
  noteInput.oninput = onEdit;
  noteTd.appendChild(noteInput);

  const actTd = document.createElement("td");
  actTd.className = "row-actions";
  actTd.append(
    iconBtn("↑", "przenieś wyżej", () => {
      const prev = tr.previousElementSibling;
      if (prev) tbody.insertBefore(tr, prev);
      onEdit();
    }),
    iconBtn("↓", "przenieś niżej", () => {
      const next = tr.nextElementSibling;
      if (next) tbody.insertBefore(next, tr);
      onEdit();
    }),
    iconBtn("+", "wstaw krok poniżej", () => addStepRow({}, tr)),
    iconBtn("✕", "usuń krok", () => {
      tr.remove();
      onEdit();
    })
  );

  tr.append(lpTd, kindTd, profTd, ...numTds, outTd, stateTd, noteTd, actTd);
  if (after) after.after(tr);
  else tbody.appendChild(tr);
  applyRowSchema(tr);
  onEdit();
  return tr;
}

/* Pola nieużywane przez dany rodzaj kroku są wyłączane i czyszczone —
   inaczej zapisalibyśmy posuw przy PAUZIE, co serwer i tak odrzuci. */
function applyRowSchema(tr) {
  const kind = tr.querySelector('[data-field="kind"]').value;
  const uses = STEP_SCHEMA[kind].uses;
  tr.querySelectorAll("[data-field]").forEach((el) => {
    const f = el.dataset.field;
    if (f === "kind" || f === "note") return;
    const used = uses.includes(f);
    el.disabled = !used;
    el.classList.toggle("unused", !used);
    if (!used) el.value = "";
  });
}

function renumber() {
  document.querySelectorAll("#step-rows tr").forEach((tr, i) => {
    tr.firstElementChild.textContent = i + 1;
  });
}

// --- odczyt i walidacja ---------------------------------------------------

function readRows() {
  return [...document.querySelectorAll("#step-rows tr")].map((tr, i) => {
    const get = (f) => tr.querySelector(`[data-field="${f}"]`);
    const kind = get("kind").value;
    const targets = {};
    for (const a of AXES) {
      const v = num(get(a).value);
      if (v != null && !Number.isNaN(v)) targets[a] = v;
    }
    const outputOn = get("output_on").value;
    return {
      lp: i + 1,
      kind,
      profile: get("profile").value || null,
      targets,
      feed: num(get("feed").value),
      output: get("output").value || null,
      output_on: outputOn === "" ? null : outputOn === "1",
      note: get("note").value.trim(),
      tr,
    };
  });
}

/* Lustro CycleStep.validate() z app/cycle.py. Serwer i tak sprawdza przy
   zapisie — tu chodzi o wcześniejszy komunikat. */
function validate(steps) {
  const problems = [];
  document.querySelectorAll("#step-rows .bad").forEach((el) =>
    el.classList.remove("bad")
  );

  const mark = (step, field, message) => {
    const el = step.tr.querySelector(`[data-field="${field}"]`);
    if (el) el.classList.add("bad");
    problems.push(`krok ${step.lp}: ${message}`);
  };

  for (const step of steps) {
    if (step.kind === "RUCH") {
      if (Object.keys(step.targets).length === 0) {
        mark(step, "x", "RUCH wymaga co najmniej jednej osi docelowej");
      }
      if (step.feed != null && !(step.feed > 0)) {
        mark(step, "feed", "posuw musi być większy od zera");
      }
      for (const [axis, value] of Object.entries(step.targets)) {
        if (Number.isNaN(value)) {
          mark(step, axis, `oś ${axis.toUpperCase()}: podaj liczbę`);
          continue;
        }
        const cfg = axesCfg && axesCfg[axis];
        if (cfg && (value < cfg.soft_min - 1e-6 || value > cfg.soft_max + 1e-6)) {
          mark(
            step,
            axis,
            `oś ${axis.toUpperCase()}: ${value} poza limitem programowym ` +
              `(${cfg.soft_min}..${cfg.soft_max})`
          );
        }
      }
    }

    if (step.kind === "WYJSCIE") {
      if (!step.output) mark(step, "output", "WYJSCIE wymaga wskazania wyjścia");
      if (step.output_on == null) mark(step, "output_on", "WYJSCIE wymaga stanu");
    }

    if (step.profile && !profileNames.includes(step.profile)) {
      mark(step, "profile", `profil „${step.profile}" nie istnieje`);
    }
  }

  if (!steps.length) problems.push("cykl nie ma żadnego kroku");
  return problems;
}

function onEdit() {
  renumber();
  const steps = readRows();
  const problems = validate(steps);
  const info = $("validate-info");
  const saveBtn = $("btn-save");

  saveBtn.disabled = problems.length > 0 || machineBusy;
  if (problems.length) {
    info.textContent = problems.join("\n");
    info.className = "msg err";
    info.style.whiteSpace = "pre-line";
  } else if (machineBusy) {
    info.textContent = "maszyna w ruchu — zapis cyklu jest zablokowany";
    info.className = "msg err";
  } else {
    info.textContent = `kroków: ${steps.length}`;
    info.className = "msg";
  }
}

// --- zapis i wczytanie ----------------------------------------------------

function toPayload(steps) {
  return steps.map((s) => ({
    lp: s.lp,
    kind: s.kind,
    profile: s.profile,
    targets: s.targets,
    feed: s.feed,
    output: s.output,
    output_on: s.output_on,
    note: s.note,
  }));
}

async function save() {
  const steps = readRows();
  if (validate(steps).length) return;
  try {
    const data = await api("PUT", "/api/cycle", {
      name: $("f-name").value.trim(),
      steps: toPayload(steps),
    });
    const warn = (data.warnings || []).join("\n");
    showMsg($("cycle-msg"), warn ? "Zapisano. Uwagi:\n" + warn : "Zapisano cykl.", !warn);
    $("cycle-msg").style.whiteSpace = "pre-line";
  } catch (e) {
    showMsg($("cycle-msg"), e.message);
  }
}

function applyCycle(data) {
  const cyc = data.cycle || { name: "", steps: [] };
  $("f-name").value = cyc.name || "";
  $("step-rows").innerHTML = "";
  for (const step of cyc.steps) addStepRow(step);
  $("cycle-file").textContent = "Plik: " + (data.file || "");
  const warn = (data.warnings || []).join("\n");
  if (warn) {
    showMsg($("cycle-msg"), "Uwagi:\n" + warn);
    $("cycle-msg").style.whiteSpace = "pre-line";
  } else {
    $("cycle-msg").className = "msg";
    $("cycle-msg").textContent = "";
  }
  onEdit();
}

async function loadCycle() {
  applyCycle(await api("GET", "/api/cycle"));
}

// --- uruchamianie ---------------------------------------------------------

async function startCycle(loop) {
  try {
    await api("POST", "/api/machine/cycle/start", { loop: !!loop });
    showMsg($("run-msg"), loop ? "Cykl uruchomiony (tryb automatyczny)." : "Cykl uruchomiony.", true);
  } catch (e) {
    showMsg($("run-msg"), e.message);
  }
}

async function stopMachine() {
  try {
    await api("POST", "/api/machine/stop");
    showMsg($("run-msg"), "Zatrzymano.", true);
  } catch (e) {
    showMsg($("run-msg"), e.message);
  }
}

async function pollState() {
  try {
    const st = await api("GET", "/api/status");
    const busy = st.state === "RUNNING" || st.state === "HOMING";
    if (busy !== machineBusy) {
      machineBusy = busy;
      onEdit();
    }
    const step =
      st.cycle_step == null
        ? "—"
        : `${st.cycle_step} / ${st.total_cycle_steps}`;
    const outs = Object.entries(st.outputs || {})
      .map(([k, v]) => `${k}=${v ? "ON" : "off"}`)
      .join("  ");
    const mode = st.cycle_loop ? "AUTOMATYCZNY (pętla)" : "—";
    $("run-state").textContent =
      `Stan: ${st.state}   krok cyklu: ${step}   tryb: ${mode}   profil: ${st.active_profile || "—"}   ${outs}`;

    // podświetlenie wykonywanego kroku
    document.querySelectorAll("#step-rows tr").forEach((tr, i) => {
      tr.classList.toggle("running", st.cycle_step === i + 1);
    });
  } catch (e) {
    /* brak statusu nie blokuje edycji — zapis i tak sprawdzi serwer */
  }
}

// --- start ----------------------------------------------------------------

/* Wrzeciono — dwie opcje granic programu technologa i obroty domyślne.
   Zapis jest częściowy: przełącznik „rusza razem z maszyną" żyje na panelu
   operatora i ten ekran go nie nadpisuje. */
function applySpindle(data) {
  $("sp-start-program").checked = data.spindle.start_with_program;
  $("sp-stop-program").checked = data.spindle.stop_after_program;
  $("sp-rpm").value = data.spindle.default_rpm;
  if (data.warnings && data.warnings.length) {
    showMsg($("spindle-msg"), "Uwaga:\n" + data.warnings.join("\n"));
    $("spindle-msg").style.whiteSpace = "pre-line";
  } else {
    $("spindle-msg").className = "msg";
  }
}

async function saveSpindle() {
  const rpm = Number(String($("sp-rpm").value).trim().replace(",", "."));
  if (!(rpm >= 0)) {
    showMsg($("spindle-msg"), "obroty domyślne: podaj liczbę nieujemną");
    return;
  }
  try {
    const data = await api("PUT", "/api/spindle", {
      start_with_program: $("sp-start-program").checked,
      stop_after_program: $("sp-stop-program").checked,
      default_rpm: rpm,
    });
    applySpindle(data);
    if (!(data.warnings && data.warnings.length)) {
      showMsg($("spindle-msg"), "zapisano ustawienia wrzeciona", true);
    }
  } catch (e) {
    showMsg($("spindle-msg"), e.message);
  }
}

$("btn-spindle-save").onclick = saveSpindle;

$("btn-add").onclick = () => addStepRow();
$("btn-save").onclick = save;
$("btn-reload").onclick = () =>
  loadCycle().catch((e) => showMsg($("cycle-msg"), e.message));
$("btn-start").onclick = () => startCycle(false);
$("btn-start-loop").onclick = () => startCycle(true);
$("btn-stop").onclick = stopMachine;

api("GET", "/api/spindle")
  .then(applySpindle)
  .catch((e) =>
    showMsg($("spindle-msg"), "nie udało się wczytać ustawień wrzeciona: " + e.message)
  );

Promise.all([
  api("GET", "/api/cycle"),
  api("GET", "/api/profiles"),
  api("GET", "/api/axes"),
])
  .then(([cyc, prof, ax]) => {
    profileNames = Object.keys(prof.profiles || {});
    outputNames = cyc.outputs || [];
    axesCfg = ax.axes || null;
    applyCycle(cyc);
  })
  .catch((e) =>
    showMsg($("cycle-msg"), "nie udało się wczytać konfiguracji: " + e.message)
  );

pollState();
setInterval(pollState, 1000);
