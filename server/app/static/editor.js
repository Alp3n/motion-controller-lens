/* Edytor technologa — edycja programów w tabeli, zapis do pliku .prg przez API. */

const $ = (id) => document.getElementById(id);
const OP_TYPES = ["PUNKT", "LINIA", "PAUZA"];

let currentNumber = null;

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

// --- edycja ---------------------------------------------------------------

function numCell(value, step = "0.001") {
  const input = document.createElement("input");
  input.type = "number";
  input.step = step;
  input.value = value ?? "";
  return input;
}

function addOpRow(op = {}) {
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
  opTd.appendChild(select);

  const cells = ["x", "y", "z", "x2", "y2"].map((k) => {
    const td = document.createElement("td");
    td.appendChild(numCell(op[k]));
    return td;
  });

  const noteTd = document.createElement("td");
  const noteInput = document.createElement("input");
  noteInput.value = op.note || "";
  noteTd.appendChild(noteInput);

  const delTd = document.createElement("td");
  const delBtn = document.createElement("button");
  delBtn.className = "small";
  delBtn.textContent = "✕";
  delBtn.onclick = () => {
    tr.remove();
    renumber();
  };
  delTd.appendChild(delBtn);

  tr.append(lpTd, opTd, ...cells, noteTd, delTd);
  tbody.appendChild(tr);
  renumber();
}

function renumber() {
  document.querySelectorAll("#op-rows tr").forEach((tr, i) => {
    tr.firstElementChild.textContent = i + 1;
  });
}

function collectContent() {
  const today = new Date().toISOString().slice(0, 10);
  const lines = [
    "[NAGLOWEK]",
    "FORMAT;1",
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
    "LP;OPERACJA;X;Y;Z;X2;Y2;UWAGI"
  );
  document.querySelectorAll("#op-rows tr").forEach((tr, i) => {
    const tds = tr.children;
    const val = (td) => td.querySelector("input,select").value.trim();
    lines.push(
      [
        i + 1,
        val(tds[1]),
        val(tds[2]),
        val(tds[3]),
        val(tds[4]),
        val(tds[5]),
        val(tds[6]),
        val(tds[7]).replaceAll(";", ","),
      ].join(";")
    );
  });
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
    p.operations.forEach(addOpRow);
    showMsg(`załadowano program ${number}`, true);
  } else {
    showMsg(`plik ${number}.prg zawiera błąd: ${data.error} — popraw i zapisz ponownie`);
  }
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

$("btn-download").onclick = () => {
  if (!currentNumber) return showMsg("najpierw wybierz lub utwórz program");
  window.open(`/api/programs/${currentNumber}/raw`, "_blank");
};

refreshList();
