/* Ekran nazwanych punktów PTP — lista z pełnym CRUD (dodaj/edytuj/usuń),
 * ten sam wzorzec co ekran definicji SMART (smart.js): kopia robocza
 * lokalnie, "Zapisz" wysyła całą listę na serwer.
 */

const $ = (id) => document.getElementById(id);

const NAME_RE = /^[^\W\d_][\w-]*$/u;

let saved = {};   // ostatnie punkty potwierdzone przez serwer
let dirty = {};   // robocze zmiany: nazwa -> {x, y, z, note}
let current = null;

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
  const el = $("msg");
  el.textContent = text;
  el.className = "msg " + (ok ? "ok" : "err");
}

function num(value) {
  const v = String(value).trim().replace(",", ".");
  return v === "" ? NaN : Number(v);
}

function renderList() {
  const tbody = $("point-list");
  tbody.innerHTML = "";
  for (const name of Object.keys(dirty).sort()) {
    const p = dirty[name];
    const tr = document.createElement("tr");
    tr.style.cursor = "pointer";
    if (name === current) tr.className = "current";
    tr.innerHTML = "<td></td><td></td><td></td><td></td>";
    tr.children[0].textContent = name;
    tr.children[1].textContent = p.x;
    tr.children[2].textContent = p.y;
    tr.children[3].textContent = p.z;
    tr.onclick = () => selectPoint(name);
    tbody.appendChild(tr);
  }
}

function onEdit() {
  if (!current) return;
  dirty[current] = {
    x: num($("f-x").value),
    y: num($("f-y").value),
    z: num($("f-z").value),
    note: $("f-note").value,
  };
  const bad = ["x", "y", "z"].some((f) => Number.isNaN(dirty[current][f]));
  $("btn-save").disabled = bad;
  showMsg(bad ? "X/Y/Z: podaj liczby" : "", !bad);
  renderList();
}

function selectPoint(name) {
  current = name;
  const p = dirty[name];
  $("edit-name").textContent = name;
  $("f-x").value = p.x;
  $("f-y").value = p.y;
  $("f-z").value = p.z;
  $("f-note").value = p.note || "";
  renderList();
}

$("btn-new").onclick = () => {
  const name = $("new-name").value.trim();
  if (!NAME_RE.test(name)) {
    showMsg("nazwa: zacznij od litery, dalej litery, cyfry, podkreślenie albo myślnik");
    return;
  }
  if (name in dirty) {
    showMsg(`punkt „${name}" już istnieje — wybierz go z listy`);
    return;
  }
  dirty[name] = { x: 0, y: 0, z: 0, note: "" };
  $("new-name").value = "";
  selectPoint(name);
  showMsg(`nowy punkt „${name}" — ustaw współrzędne i zapisz`, true);
};

$("btn-save-as").onclick = () => {
  if (!current) return showMsg("najpierw wybierz punkt");
  const name = $("save-as-name").value.trim();
  if (!NAME_RE.test(name)) {
    showMsg("nazwa: zacznij od litery, dalej litery, cyfry, podkreślenie albo myślnik");
    return;
  }
  if (name === current) return showMsg("podaj inną nazwę niż bieżąca");
  if (name in dirty) return showMsg(`punkt „${name}" już istnieje — wybierz inną nazwę`);
  dirty[name] = { ...dirty[current] };
  $("save-as-name").value = "";
  selectPoint(name);
  showMsg(`skopiowano jako „${name}" — kliknij Zapisz`, true);
};

$("btn-delete").onclick = () => {
  if (!current) return showMsg("najpierw wybierz punkt");
  const name = current;
  delete dirty[name];
  const rest = Object.keys(dirty).sort();
  current = null;
  if (rest.length) {
    selectPoint(rest[0]);
  } else {
    $("edit-name").textContent = "—";
    ["f-x", "f-y", "f-z", "f-note"].forEach((id) => ($(id).value = ""));
    renderList();
  }
  showMsg(`usunięto „${name}" lokalnie — kliknij Zapisz, żeby zapisać do pliku`, true);
};

["f-x", "f-y", "f-z", "f-note"].forEach((id) =>
  $(id).addEventListener("input", onEdit)
);

// --- serwer ---------------------------------------------------------------

function applyPoints(data) {
  saved = data.points || {};
  dirty = JSON.parse(JSON.stringify(saved));
  if (data.file) $("file-path").textContent = "Plik: " + data.file;

  const names = Object.keys(dirty).sort();
  current = null;
  if (names.length) {
    selectPoint(names[0]);
  } else {
    $("edit-name").textContent = "—";
    renderList();
  }
}

async function loadPoints() {
  applyPoints(await api("GET", "/api/punkty"));
}

$("btn-save").onclick = async () => {
  onEdit();
  if ($("btn-save").disabled) return;
  try {
    const data = await api("PUT", "/api/punkty", { points: dirty });
    const keep = current;
    applyPoints({ ...data, file: null });
    if (keep && keep in dirty) selectPoint(keep);
    showMsg("zapisano punkty", true);
  } catch (e) {
    showMsg("nie zapisano — " + e.message);
  }
};

$("btn-reload").onclick = () =>
  loadPoints().catch((e) => showMsg("nie udało się wczytać: " + e.message));

loadPoints().catch((e) => showMsg("nie udało się wczytać punktów: " + e.message));
