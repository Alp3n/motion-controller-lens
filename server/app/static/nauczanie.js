/* Ekran "prowadzenie za rękę" — zwolnienie osi (POST /api/machine/release,
 * mechanizm już istniejący, patrz app.js/panel operatora) + zapis bieżącej
 * pozycji jako nazwanego punktu (POST/PUT /api/punkty).
 *
 * Świadomie NIE ma tu żadnej nowej komendy mostka ani "trybu podatnego" —
 * sFoundation SDK nie udostępnia sterowania momentem z hosta (potwierdzone
 * 2026-09-06, docs/prowadzenie-za-reke.md). Zwolnienie to pełne zdjęcie
 * momentu, nie regulowany opór.
 */

const $ = (id) => document.getElementById(id);

const NAME_RE = /^[^\W\d_][\w-]*$/u;

let lastStatus = null;

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

// --- status na żywo (pozycja + które osie są zwolnione) --------------------

function applyStatus(st) {
  lastStatus = st;
  $("pos-x").textContent = fmt(st.position.x);
  $("pos-y").textContent = fmt(st.position.y);
  $("pos-z").textContent = fmt(st.position.z);

  const released = st.released_axes || [];
  document.querySelectorAll(".rel").forEach((btn) => {
    const isReleased = released.includes(btn.dataset.axis);
    btn.classList.toggle("released", isReleased);
    btn.textContent = (isReleased ? "Zaciśnij " : "Zwolnij ") + btn.dataset.axis.toUpperCase();
  });
}

async function pollStatus() {
  try {
    applyStatus(await api("GET", "/api/status"));
  } catch (e) {
    /* chwilowy brak statusu nie blokuje ekranu */
  }
}

document.querySelectorAll(".rel").forEach((btn) => {
  btn.addEventListener("click", () => {
    const released = !btn.classList.contains("released");
    api("POST", "/api/machine/release", { axis: btn.dataset.axis, released })
      .then(() => showMsg($("rel-msg"), "", true))
      .catch((e) => showMsg($("rel-msg"), e.message));
  });
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
setInterval(pollStatus, 500);
