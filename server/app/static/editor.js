/* Edytor technologa — edycja programów w tabeli, zapis do pliku .prg przez API.
 *
 * Pola operacji zależą od jej rodzaju, walidacja obszaru roboczego działa
 * na bieżąco, a podgląd toru rysuje to, co jest w tabeli — także przed zapisem.
 */

const $ = (id) => document.getElementById(id);

/* Definicja pól per rodzaj operacji — jedno źródło prawdy dla renderowania,
   walidacji i czyszczenia nieużywanych kolumn. */
const OP_SCHEMA = {
  PUNKT: { uses: ["x", "y", "z", "feed", "passes", "depth_step"], required: ["x", "y", "z"] },
  LINIA: {
    uses: ["x", "y", "z", "x2", "y2", "feed", "passes", "depth_step"],
    required: ["x", "y", "z", "x2", "y2"],
  },
  PROSTOKAT: {
    uses: ["x", "y", "z", "x2", "y2", "feed", "passes", "depth_step"],
    required: ["x", "y", "z", "x2", "y2"],
  },
  SZYBKI: { uses: ["x", "y", "feed"], required: ["x", "y"] },
  WRZECIONO: { uses: ["rpm"], required: ["rpm"] },
  PAUZA: { uses: [], required: [] },
};
const OP_TYPES = Object.keys(OP_SCHEMA);
const FIELDS = ["x", "y", "z", "x2", "y2", "feed", "rpm", "passes", "depth_step"];
const STEP = { passes: "1", feed: "1", rpm: "100", depth_step: "0.01" };
// nazwy kolumn tak, jak widzi je technolog w tabeli i w pliku .prg
const LABEL = {
  x: "X", y: "Y", z: "Z", x2: "X2", y2: "Y2",
  feed: "POSUW", rpm: "OBROTY", passes: "PRZEJSCIA", depth_step: "PRZYROST",
};

let currentNumber = null;
let workArea = null;

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
  const el = $("editor-msg");
  el.textContent = text;
  el.className = "msg " + (ok ? "ok" : "err");
}

// --- lista programów ------------------------------------------------------

async function refreshList() {
  const data = await api("GET", "/api/programs");
  const tbody = $("program-list");
  tbody.innerHTML = "";
  for (const p of data.programs) {
    const tr = document.createElement("tr");
    tr.style.cursor = "pointer";
    tr.innerHTML = `<td>${p.number}</td><td></td>`;
    tr.lastElementChild.textContent = p.valid ? p.name : "⚠ błąd w pliku";
    tr.onclick = () => loadProgram(p.number);
    tbody.appendChild(tr);
  }
}

// --- wiersz operacji ------------------------------------------------------

function numCell(field, value) {
  const input = document.createElement("input");
  input.type = "number";
  input.step = STEP[field] || "0.001";
  input.value = value ?? "";
  input.dataset.field = field;
  input.oninput = () => {
    // PRZEJSCIA i PRZYROST wykluczają się — wypełnienie jednego czyści drugie
    if (input.value && (field === "passes" || field === "depth_step")) {
      const other = field === "passes" ? "depth_step" : "passes";
      const el = input.closest("tr").querySelector(`input[data-field="${other}"]`);
      if (el) el.value = "";
    }
    onEdit();
  };
  return input;
}

function iconBtn(label, title, onClick) {
  const b = document.createElement("button");
  b.className = "small icon";
  b.textContent = label;
  b.title = title;
  b.onclick = onClick;
  return b;
}

function addOpRow(op = {}, after = null) {
  const tbody = $("op-rows");
  const tr = document.createElement("tr");

  const lpTd = document.createElement("td");

  const opTd = document.createElement("td");
  const select = document.createElement("select");
  for (const t of OP_TYPES) {
    const o = document.createElement("option");
    o.value = o.textContent = t;
    select.appendChild(o);
  }
  select.value = op.op_type || "PUNKT";
  select.onchange = () => {
    applyRowSchema(tr);
    onEdit();
  };
  opTd.appendChild(select);

  const fieldTds = FIELDS.map((f) => {
    const td = document.createElement("td");
    td.appendChild(numCell(f, op[f]));
    return td;
  });

  const noteTd = document.createElement("td");
  const noteInput = document.createElement("input");
  noteInput.value = op.note || "";
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
    iconBtn("+", "wstaw operację poniżej", () => addOpRow({}, tr)),
    iconBtn("✕", "usuń operację", () => {
      tr.remove();
      onEdit();
    })
  );

  tr.append(lpTd, opTd, ...fieldTds, noteTd, actTd);
  if (after) tbody.insertBefore(tr, after.nextElementSibling);
  else tbody.appendChild(tr);

  applyRowSchema(tr);
  onEdit();
  return tr;
}

/* Wygasza pola, których dany rodzaj operacji nie używa, i czyści ich treść —
   inaczej po zmianie rodzaju zostałyby wartości, które parser odrzuci. */
function applyRowSchema(tr) {
  const type = tr.querySelector("select").value;
  const uses = OP_SCHEMA[type].uses;
  for (const f of FIELDS) {
    const input = tr.querySelector(`input[data-field="${f}"]`);
    const used = uses.includes(f);
    input.disabled = !used;
    input.parentElement.classList.toggle("off", !used);
    if (!used) input.value = "";
  }
}

function renumber() {
  document.querySelectorAll("#op-rows tr").forEach((tr, i) => {
    tr.firstElementChild.textContent = i + 1;
  });
}

// --- odczyt i walidacja ---------------------------------------------------

function readRows() {
  return [...document.querySelectorAll("#op-rows tr")].map((tr, i) => {
    const op = { lp: i + 1, op_type: tr.querySelector("select").value, tr };
    for (const f of [...FIELDS, "note"]) {
      const input = tr.querySelector(`[data-field="${f}"]`);
      const raw = input.value.trim();
      op[f] = f === "note" ? raw : raw === "" ? null : Number(raw.replace(",", "."));
    }
    return op;
  });
}

/* Sprawdza obszar roboczy i pola wymagane. Serwer i tak waliduje przy zapisie —
   tu chodzi o to, żeby technolog zobaczył błąd od razu, a nie po zapisie. */
function validate(ops) {
  const problems = [];
  document.querySelectorAll("#op-rows .bad").forEach((el) => el.classList.remove("bad"));

  const mark = (op, field, text) => {
    const el = op.tr.querySelector(`[data-field="${field}"]`);
    if (el) el.classList.add("bad");
    problems.push(`LP${op.lp}: ${text}`);
  };

  for (const op of ops) {
    const schema = OP_SCHEMA[op.op_type];
    for (const f of schema.required) {
      if (op[f] === null || Number.isNaN(op[f])) mark(op, f, `brak wartości ${LABEL[f]}`);
    }
    if (op.passes !== null && op.depth_step !== null)
      mark(op, "depth_step", "wypełnij PRZEJSCIA albo PRZYROST, nie oba");
    if (op.passes !== null && (!Number.isInteger(op.passes) || op.passes < 1))
      mark(op, "passes", "PRZEJSCIA musi być liczbą całkowitą ≥ 1");
    for (const f of ["feed", "depth_step"])
      if (op[f] !== null && op[f] <= 0) mark(op, f, `${LABEL[f]} musi być > 0`);
    if (op.rpm !== null && op.rpm < 0) mark(op, "rpm", "OBROTY nie mogą być ujemne");

    if (!workArea) continue;
    const a = workArea;
    for (const [fx, fy] of [["x", "y"], ["x2", "y2"]]) {
      if (op[fx] === null || op[fy] === null) continue;
      if (op[fx] < a.x_min || op[fx] > a.x_max) mark(op, fx, `${LABEL[fx]} poza obszarem`);
      if (op[fy] < a.y_min || op[fy] > a.y_max) mark(op, fy, `${LABEL[fy]} poza obszarem`);
    }
    if (op.z !== null && (op.z < a.z_min || op.z > a.z_max)) mark(op, "z", "Z poza zakresem");
  }
  return problems;
}

function onEdit() {
  renumber();
  const ops = readRows();
  const problems = validate(ops);
  const info = $("validate-info");
  if (problems.length) {
    info.textContent =
      `${problems.length} do poprawy: ` +
      problems.slice(0, 3).join("; ") +
      (problems.length > 3 ? " …" : "");
    info.className = "msg err";
  } else {
    info.textContent = ops.length ? `${ops.length} operacji, bez błędów` : "brak operacji";
    info.className = "msg ok";
  }
  drawEditView(ops);
}

// --- podgląd toru ---------------------------------------------------------

function drawEditView(ops) {
  const c = $("edit-view");
  if (!c || !workArea) return;
  const ctx = c.getContext("2d");
  const a = workArea;

  const dpr = window.devicePixelRatio || 1;
  const w = c.clientWidth;
  const h = c.clientHeight;
  if (c.width !== Math.round(w * dpr) || c.height !== Math.round(h * dpr)) {
    c.width = Math.round(w * dpr);
    c.height = Math.round(h * dpr);
  }
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, w, h);

  const css = (n, d) =>
    getComputedStyle(document.documentElement).getPropertyValue(n).trim() || d;
  const muted = css("--muted", "#93a1b1");
  const border = css("--border", "#33404f");
  const accent = css("--accent", "#3aa0ff");
  const err = css("--err", "#e74c3c");

  const pad = 26;

  /* Kadrowanie do zasięgu programu — przy obszarze roboczym ±100 mm detal
     wielkości kilkudziesięciu mm byłby nieczytelnym punktem w rogu.
     Bez operacji pokazujemy cały obszar roboczy. */
  const xs = [];
  const ys = [];
  for (const o of ops) {
    if (o.x !== null && !Number.isNaN(o.x)) xs.push(o.x);
    if (o.y !== null && !Number.isNaN(o.y)) ys.push(o.y);
    if (o.op_type === "LINIA") {
      if (o.x2 !== null && !Number.isNaN(o.x2)) xs.push(o.x2);
      if (o.y2 !== null && !Number.isNaN(o.y2)) ys.push(o.y2);
    }
  }
  let vx0 = a.x_min;
  let vx1 = a.x_max;
  let vy0 = a.y_min;
  let vy1 = a.y_max;
  if (xs.length && ys.length) {
    const m = Math.max(
      5,
      (Math.max(...xs) - Math.min(...xs)) * 0.15,
      (Math.max(...ys) - Math.min(...ys)) * 0.15
    );
    // Kadr nigdy nie wychodzi poza obszar roboczy — pojedyncza literówka
    // (np. X=999) inaczej rozjeżdżałaby cały rysunek. Błędny punkt i tak
    // jest oznaczony na czerwono w tabeli i w komunikacie walidacji.
    vx0 = Math.max(a.x_min, Math.min(...xs) - m);
    vx1 = Math.min(a.x_max, Math.max(...xs) + m);
    vy0 = Math.max(a.y_min, Math.min(...ys) - m);
    vy1 = Math.min(a.y_max, Math.max(...ys) + m);
    if (vx1 - vx0 < 1 || vy1 - vy0 < 1) {
      vx0 = a.x_min; vx1 = a.x_max; vy0 = a.y_min; vy1 = a.y_max;
    }
  }
  const spanX = vx1 - vx0;
  const spanY = vy1 - vy0;
  const s = Math.min((w - pad * 2) / spanX, (h - pad * 2) / spanY);
  const ox = pad + (w - pad * 2 - spanX * s) / 2;
  const oy = pad + (h - pad * 2 - spanY * s) / 2;
  const X = (mx) => ox + (mx - vx0) * s;
  const Y = (my) => oy + (vy1 - my) * s;

  // siatka o kroku dobranym do skali widoku
  const step = spanX > 300 ? 50 : spanX > 120 ? 20 : spanX > 60 ? 10 : spanX > 25 ? 5 : 1;
  ctx.lineWidth = 1;
  ctx.strokeStyle = border;
  ctx.beginPath();
  for (let v = Math.ceil(vx0 / step) * step; v <= vx1; v += step) {
    ctx.moveTo(Math.round(X(v)) + 0.5, Y(vy1));
    ctx.lineTo(Math.round(X(v)) + 0.5, Y(vy0));
  }
  for (let v = Math.ceil(vy0 / step) * step; v <= vy1; v += step) {
    ctx.moveTo(X(vx0), Math.round(Y(v)) + 0.5);
    ctx.lineTo(X(vx1), Math.round(Y(v)) + 0.5);
  }
  ctx.stroke();

  // osie zerowe — punkt odniesienia uchwytu płytki
  ctx.strokeStyle = muted;
  ctx.globalAlpha = 0.6;
  ctx.beginPath();
  if (vy0 <= 0 && vy1 >= 0) {
    ctx.moveTo(X(vx0), Math.round(Y(0)) + 0.5);
    ctx.lineTo(X(vx1), Math.round(Y(0)) + 0.5);
  }
  if (vx0 <= 0 && vx1 >= 0) {
    ctx.moveTo(Math.round(X(0)) + 0.5, Y(vy1));
    ctx.lineTo(Math.round(X(0)) + 0.5, Y(vy0));
  }
  ctx.stroke();
  ctx.globalAlpha = 1;

  // Granica obszaru roboczego — przy zbliżeniu widać tylko jej fragment,
  // więc kreskowana i przygaszona, żeby nie brać jej za element programu.
  ctx.save();
  ctx.setLineDash([6, 5]);
  ctx.globalAlpha = 0.45;
  ctx.strokeStyle = muted;
  ctx.strokeRect(
    X(a.x_min),
    Y(a.y_max),
    (a.x_max - a.x_min) * s,
    (a.y_max - a.y_min) * s
  );
  ctx.restore();

  // zakres widoku, żeby było wiadomo w jakiej skali patrzymy
  ctx.font = "11px system-ui, sans-serif";
  ctx.fillStyle = muted;
  ctx.fillText(`X ${vx0.toFixed(0)}…${vx1.toFixed(0)} mm`, 8, h - 18);
  ctx.fillText(`Y ${vy0.toFixed(0)}…${vy1.toFixed(0)} mm`, 8, h - 5);

  // przejazdy między kolejnymi operacjami — linia przerywana
  const pts = ops.filter((o) => o.x !== null && o.y !== null && !Number.isNaN(o.x));
  if (pts.length > 1) {
    ctx.save();
    ctx.setLineDash([4, 4]);
    ctx.strokeStyle = muted;
    ctx.globalAlpha = 0.5;
    ctx.beginPath();
    let prev = null;
    for (const o of pts) {
      if (prev) {
        ctx.moveTo(X(prev.x), Y(prev.y));
        ctx.lineTo(X(o.x), Y(o.y));
      }
      const isLine = o.op_type === "LINIA" && o.x2 !== null && o.y2 !== null;
      prev = { x: isLine ? o.x2 : o.x, y: isLine ? o.y2 : o.y };
    }
    ctx.stroke();
    ctx.restore();
  }

  // operacje
  for (const o of ops) {
    if (o.x === null || o.y === null || Number.isNaN(o.x) || Number.isNaN(o.y)) continue;
    const bad = o.tr.querySelector(".bad") !== null;
    ctx.strokeStyle = bad ? err : accent;
    ctx.fillStyle = bad ? err : accent;
    ctx.lineWidth = 2;
    if (o.op_type === "LINIA" && o.x2 !== null && o.y2 !== null) {
      ctx.beginPath();
      ctx.moveTo(X(o.x), Y(o.y));
      ctx.lineTo(X(o.x2), Y(o.y2));
      ctx.stroke();
    }
    if (o.op_type === "PROSTOKAT" && o.x2 !== null && o.y2 !== null) {
      ctx.strokeRect(X(o.x), Y(o.y), (o.x2 - o.x) * s, -(o.y2 - o.y) * s);
    }
    ctx.beginPath();
    ctx.arc(X(o.x), Y(o.y), 4, 0, Math.PI * 2);
    // SZYBKI to tylko przejazd — pusty znacznik, żeby nie mylił się ze skrawaniem
    if (o.op_type === "SZYBKI") ctx.stroke();
    else ctx.fill();
    ctx.fillText(String(o.lp), X(o.x) + 7, Y(o.y) - 6);
  }
}

// --- zapis ----------------------------------------------------------------

function fmtCell(v) {
  return v === null || v === undefined || Number.isNaN(v) ? "" : String(v);
}

function collectContent() {
  const today = new Date().toISOString().slice(0, 10);
  const lines = [
    "[NAGLOWEK]",
    "FORMAT;3",
    `PROGRAM;${currentNumber}`,
    `NAZWA;${$("f-name").value.trim()}`,
  ];
  if ($("f-material").value.trim()) lines.push(`MATERIAL;${$("f-material").value.trim()}`);
  if ($("f-author").value.trim()) lines.push(`AUTOR;${$("f-author").value.trim()}`);
  lines.push(
    `DATA;${today}`,
    `OBROTY_FREZU;${$("f-rpm").value}`,
    `POSUW_ROBOCZY;${$("f-feed-work").value}`,
    `POSUW_DOJAZDU;${$("f-feed-travel").value}`,
    `Z_BEZPIECZNE;${$("f-z-safe").value}`,
    "",
    "[OPERACJE]",
    "LP;OPERACJA;X;Y;Z;X2;Y2;POSUW;OBROTY;PRZEJSCIA;PRZYROST;UWAGI"
  );
  for (const op of readRows()) {
    lines.push(
      [
        op.lp,
        op.op_type,
        ...FIELDS.map((f) => fmtCell(op[f])),
        String(op.note).replaceAll(";", ","),
      ].join(";")
    );
  }
  return lines.join("\n") + "\n";
}

async function loadProgram(number) {
  const data = await api("GET", `/api/programs/${number}`);
  currentNumber = number;
  $("edit-number").textContent = number;
  $("op-rows").innerHTML = "";
  if (data.parsed) {
    const p = data.parsed;
    $("f-name").value = p.name;
    $("f-material").value = p.material;
    $("f-author").value = p.author;
    $("f-rpm").value = p.spindle_rpm;
    $("f-feed-work").value = p.feed_work;
    $("f-feed-travel").value = p.feed_travel;
    $("f-z-safe").value = p.z_safe;
    p.operations.forEach((op) => addOpRow(op));
    showMsg(`załadowano program ${number}`, true);
  } else {
    showMsg(`plik ${number}.prg zawiera błąd: ${data.error} — popraw i zapisz ponownie`);
  }
  onEdit();
}

$("btn-new").onclick = () => {
  const number = $("new-number").value.trim();
  if (!/^\d{12}$/.test(number)) {
    showMsg("numer programu musi mieć dokładnie 12 cyfr");
    return;
  }
  currentNumber = number;
  $("edit-number").textContent = number;
  $("f-name").value = "";
  $("f-material").value = "";
  $("f-author").value = "";
  $("f-rpm").value = 12000;
  $("f-feed-work").value = 300;
  $("f-feed-travel").value = 3000;
  $("f-z-safe").value = 10;
  $("op-rows").innerHTML = "";
  addOpRow();
  showMsg(`nowy program ${number} — uzupełnij dane i zapisz`, true);
};

$("btn-add-op").onclick = () => {
  if (!currentNumber) return showMsg("najpierw wybierz lub utwórz program");
  addOpRow();
};

$("btn-save").onclick = async () => {
  if (!currentNumber) return showMsg("najpierw wybierz lub utwórz program");
  try {
    const data = await api("PUT", `/api/programs/${currentNumber}`, {
      content: collectContent(),
    });
    showMsg(`zapisano program ${data.number} (${data.name})`, true);
    refreshList();
  } catch (e) {
    showMsg("nie zapisano — " + e.message);
  }
};

$("btn-save-as").onclick = async () => {
  if (!currentNumber) return showMsg("najpierw wybierz lub utwórz program");
  const input = $("save-as-number");
  const newNumber = input.value.trim();
  if (!/^\d{12}$/.test(newNumber)) {
    showMsg("nowy numer programu musi mieć dokładnie 12 cyfr");
    return;
  }
  if (newNumber === currentNumber) {
    showMsg("podaj inny numer niż bieżący — to już jest ten program");
    return;
  }
  try {
    const list = await api("GET", "/api/programs");
    if (list.programs.some((p) => p.number === newNumber)) {
      showMsg(
        `program ${newNumber} już istnieje — wybierz inny numer albo otwórz go ` +
          "z listy i zapisz nad nim świadomie"
      );
      return;
    }
  } catch (e) {
    /* brak listy nie blokuje próby zapisu — PUT poniżej i tak sprawdzi numer */
  }

  const previousNumber = currentNumber;
  currentNumber = newNumber; // collectContent() czyta numer z tej zmiennej
  try {
    const data = await api("PUT", `/api/programs/${newNumber}`, { content: collectContent() });
    $("edit-number").textContent = newNumber;
    input.value = "";
    showMsg(`zapisano jako nowy program ${data.number} (${data.name}) — edytujesz teraz kopię`, true);
    refreshList();
  } catch (e) {
    currentNumber = previousNumber; // nieudany zapis nie może przełączyć edytora na nieistniejący numer
    showMsg("nie zapisano — " + e.message);
  }
};

$("btn-download").onclick = () => {
  if (!currentNumber) return showMsg("najpierw wybierz lub utwórz program");
  window.open(`/api/programs/${currentNumber}/raw`, "_blank");
};

window.addEventListener("resize", () => drawEditView(readRows()));

(async () => {
  try {
    workArea = (await api("GET", "/api/config")).work_area;
  } catch (e) {
    workArea = { x_min: -100, x_max: 100, y_min: -100, y_max: 100, z_min: -20, z_max: 50 };
  }
  await refreshList();
  onEdit();
})();
