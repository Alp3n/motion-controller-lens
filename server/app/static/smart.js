/* Ekran definicji SMART — nazwane zestawy parametrów procedur sterowanych siłą.
 *
 * Pola parametrów NIE są tu wypisane na sztywno: rysujemy je z rejestru
 * procedur, który przychodzi z serwera (`/api/smart` → `procedures`). Dzięki
 * temu dopisanie procedury albo parametru po stronie serwera/mostka pojawia
 * się na ekranie samo, bez zmiany tego pliku — ten sam wzorzec, co pola
 * zależne od rodzaju operacji w edytorze technologa.
 */

const $ = (id) => document.getElementById(id);

// musi odpowiadać _NAME_RE w app/smart.py — nazwa trafia też do pliku .prg,
// gdzie średnik rozdziela kolumny, więc bez spacji i średnika
const NAME_RE = /^[^\W\d_][\w-]*$/u;

let procedures = {};   // nazwa -> opis procedury z parametrami
let saved = {};        // ostatnie definicje potwierdzone przez serwer
let current = null;    // nazwa edytowanej definicji
let dirty = {};        // robocze zmiany: nazwa -> definicja (przed zapisem)
let machineBusy = false;

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
  const el = $("smart-msg");
  el.textContent = text;
  el.className = "msg " + (ok ? "ok" : "err");
}

function num(value) {
  const v = String(value).trim().replace(",", ".");
  return v === "" ? NaN : Number(v);
}

// --- lista definicji ------------------------------------------------------

function renderList() {
  const tbody = $("def-list");
  tbody.innerHTML = "";
  for (const name of Object.keys(dirty).sort()) {
    const tr = document.createElement("tr");
    tr.style.cursor = "pointer";
    if (name === current) tr.className = "current";
    const proc = procedures[dirty[name].procedure];
    tr.innerHTML = "<td></td><td></td>";
    tr.children[0].textContent = name;
    tr.children[1].textContent = proc ? proc.label : dirty[name].procedure;
    tr.onclick = () => selectDefinition(name);
    tbody.appendChild(tr);
  }
}

// --- pola parametrów ------------------------------------------------------

function paramId(name) {
  return "p-" + name;
}

/* Rysuje pola dla wybranej procedury. Liczbowe dostają min/max z rejestru,
   parametry z listą wartości (np. oś) dostają <select>. */
function buildParamFields(procName, values) {
  const wrap = $("param-fields");
  wrap.innerHTML = "";
  const proc = procedures[procName];
  $("proc-desc").textContent = proc ? proc.description : "";
  if (!proc) return;

  for (const spec of proc.params) {
    const div = document.createElement("div");
    div.className = "field";
    const label = document.createElement("label");
    label.textContent = spec.label + (spec.unit ? ` [${spec.unit}]` : "");
    if (spec.help) label.title = spec.help;
    div.appendChild(label);

    let input;
    if (spec.choices) {
      input = document.createElement("select");
      for (const c of spec.choices) {
        const o = document.createElement("option");
        o.value = c;
        o.textContent = c.toUpperCase();
        input.appendChild(o);
      }
    } else {
      input = document.createElement("input");
      input.type = "number";
      input.step = "any";
      if (spec.minimum !== null) input.min = spec.minimum;
      if (spec.maximum !== null) input.max = spec.maximum;
    }
    input.id = paramId(spec.name);
    input.value = values && spec.name in values ? values[spec.name] : spec.default;
    if (spec.help) input.title = spec.help;
    input.addEventListener("input", onEdit);
    input.addEventListener("change", onEdit);
    div.appendChild(input);
    wrap.appendChild(div);
  }
}

function readParams(procName) {
  const proc = procedures[procName];
  const out = {};
  if (!proc) return out;
  for (const spec of proc.params) {
    const el = $(paramId(spec.name));
    if (!el) continue;
    out[spec.name] = spec.choices ? el.value : num(el.value);
  }
  return out;
}

// --- walidacja (lustro app/smart.py) --------------------------------------

function validate(procName, params) {
  const proc = procedures[procName];
  const problems = [];
  document.querySelectorAll("#param-fields .bad").forEach((el) =>
    el.classList.remove("bad")
  );
  if (!proc) return problems;

  const mark = (name, text) => {
    const el = $(paramId(name));
    if (el) el.classList.add("bad");
    problems.push(text);
  };

  for (const spec of proc.params) {
    const v = params[spec.name];
    if (spec.choices) {
      if (!spec.choices.includes(v)) mark(spec.name, `${spec.label}: wybierz wartość`);
      continue;
    }
    if (Number.isNaN(v)) {
      mark(spec.name, `${spec.label}: podaj liczbę`);
      continue;
    }
    if (spec.minimum !== null && v < spec.minimum)
      mark(spec.name, `${spec.label}: nie mniej niż ${spec.minimum}`);
    if (spec.maximum !== null && v > spec.maximum)
      mark(spec.name, `${spec.label}: nie więcej niż ${spec.maximum}`);
  }

  // zależności między parametrami — te same co validate() w app/smart.py
  if (procName === "ciecie_adaptacyjne") {
    const zwol = params.prog_zwolnienia;
    const przysp = params.prog_przyspieszenia;
    if (!Number.isNaN(zwol) && !Number.isNaN(przysp) && przysp >= zwol) {
      mark("prog_przyspieszenia",
        "próg przyspieszenia musi być mniejszy od progu zwolnienia");
    }
    if (!Number.isNaN(params.v_wolna) && !Number.isNaN(params.v_szybka) &&
        params.v_wolna > params.v_szybka) {
      mark("v_wolna", "prędkość wolna nie może być większa od szybkiej");
    }
  }
  return problems;
}

/* Zbiera bieżący stan pól do `dirty`, waliduje i przestawia przycisk zapisu. */
function onEdit() {
  if (!current) return;
  const procName = $("f-procedure").value;
  const params = readParams(procName);
  dirty[current] = {
    name: current,
    procedure: procName,
    params,
    note: $("f-note").value,
  };
  const problems = validate(procName, params);
  $("btn-save").disabled = problems.length > 0 || machineBusy;
  if (problems.length) {
    showMsg(problems.join("\n"));
    $("smart-msg").style.whiteSpace = "pre-line";
  } else if (machineBusy) {
    showMsg("maszyna w ruchu — zapis definicji jest zablokowany");
  } else {
    $("smart-msg").className = "msg";
  }
}

// --- wybór i tworzenie ----------------------------------------------------

function selectDefinition(name) {
  current = name;
  const def = dirty[name];
  $("edit-name").textContent = name;
  $("f-procedure").value = def.procedure;
  buildParamFields(def.procedure, def.params);
  $("f-note").value = def.note || "";
  renderList();
  onEdit();
}

$("f-procedure").onchange = () => {
  // zmiana procedury = inny zestaw parametrów; wypełniamy domyślnymi
  buildParamFields($("f-procedure").value, null);
  onEdit();
};

$("btn-new").onclick = () => {
  const name = $("new-name").value.trim();
  if (!NAME_RE.test(name)) {
    showMsg("nazwa: zacznij od litery, dalej litery, cyfry, podkreślenie albo myślnik");
    return;
  }
  if (name in dirty) {
    showMsg(`definicja „${name}" już istnieje — wybierz ją z listy`);
    return;
  }
  const procName = Object.keys(procedures)[0];
  dirty[name] = { name, procedure: procName, params: null, note: "" };
  $("new-name").value = "";
  selectDefinition(name);
  showMsg(`nowa definicja „${name}" — ustaw parametry i zapisz`, true);
};

$("btn-save-as").onclick = () => {
  if (!current) return showMsg("najpierw wybierz definicję");
  const name = $("save-as-name").value.trim();
  if (!NAME_RE.test(name)) {
    showMsg("nazwa: zacznij od litery, dalej litery, cyfry, podkreślenie albo myślnik");
    return;
  }
  if (name === current) {
    showMsg("podaj inną nazwę niż bieżąca — to już jest ta definicja");
    return;
  }
  if (name in dirty) {
    showMsg(`definicja „${name}" już istnieje — wybierz inną nazwę`);
    return;
  }
  const procName = $("f-procedure").value;
  dirty[name] = {
    name,
    procedure: procName,
    params: readParams(procName),
    note: $("f-note").value,
  };
  $("save-as-name").value = "";
  selectDefinition(name);
  showMsg(`skopiowano jako „${name}" — kliknij Zapisz, żeby zapisać do pliku`, true);
};

$("btn-delete").onclick = () => {
  if (!current) return showMsg("najpierw wybierz definicję");
  const name = current;
  delete dirty[name];
  const rest = Object.keys(dirty).sort();
  current = null;
  if (rest.length) {
    selectDefinition(rest[0]);
  } else {
    $("edit-name").textContent = "—";
    $("param-fields").innerHTML = "";
    renderList();
  }
  showMsg(`usunięto „${name}" lokalnie — kliknij Zapisz, żeby zapisać do pliku`, true);
};

// --- serwer ---------------------------------------------------------------

function applySmart(data) {
  saved = data.definitions || {};
  if (data.procedures) {
    procedures = {};
    for (const p of data.procedures) procedures[p.name] = p;
    const sel = $("f-procedure");
    sel.innerHTML = "";
    for (const p of data.procedures) {
      const o = document.createElement("option");
      o.value = p.name;
      o.textContent = p.label;
      sel.appendChild(o);
    }
  }
  // kopia robocza — dopiero „Zapisz" wysyła ją na serwer
  dirty = JSON.parse(JSON.stringify(saved));
  if (data.file) $("smart-file").textContent = "Plik definicji: " + data.file;

  const names = Object.keys(dirty).sort();
  current = null;
  if (names.length) {
    selectDefinition(names[0]);
  } else {
    $("edit-name").textContent = "—";
    $("param-fields").innerHTML = "";
    $("proc-desc").textContent = "";
    renderList();
  }

  const warn = $("smart-warn");
  if (data.warnings && data.warnings.length) {
    warn.textContent = "Uwaga:\n" + data.warnings.join("\n");
    $("smart-warn-panel").hidden = false;
  } else {
    $("smart-warn-panel").hidden = true;
  }
}

async function loadSmart() {
  applySmart(await api("GET", "/api/smart"));
}

$("btn-save").onclick = async () => {
  onEdit();
  if ($("btn-save").disabled) return;
  const payload = { definitions: {} };
  for (const name in dirty) {
    const d = dirty[name];
    payload.definitions[name] = {
      procedure: d.procedure,
      // definicja nietknięta od wczytania ma params === null tylko wtedy, gdy
      // powstała przed chwilą — wtedy bierzemy wartości domyślne z pól
      params: d.params || {},
      note: d.note || "",
    };
  }
  try {
    const data = await api("PUT", "/api/smart", payload);
    const keep = current;
    applySmart({ ...data, procedures: Object.values(procedures), file: null });
    if (keep && keep in dirty) selectDefinition(keep);
    showMsg("zapisano definicje SMART", true);
  } catch (e) {
    showMsg("nie zapisano — " + e.message);
  }
};

$("btn-reload").onclick = () =>
  loadSmart().catch((e) => showMsg("nie udało się wczytać: " + e.message));

async function pollState() {
  try {
    const st = await api("GET", "/api/status");
    const busy = st.state === "RUNNING" || st.state === "HOMING";
    if (busy !== machineBusy) {
      machineBusy = busy;
      onEdit();
    }
  } catch (e) {
    /* brak statusu nie blokuje edycji — zapis i tak sprawdzi serwer */
  }
}

loadSmart().catch((e) => showMsg("nie udało się wczytać definicji: " + e.message));
pollState();
setInterval(pollState, 1500);
