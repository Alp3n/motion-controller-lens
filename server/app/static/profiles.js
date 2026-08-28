/* Ekran profili parametrów ruchu — siła i prędkość na trzech poziomach
   (globalny / cykl / program technologa), po jednym komplecie na oś.
   Walidacja jest powtórzona po stronie serwera (app/profiles.py); tutaj
   chodzi o to, żeby admin zobaczył błąd zanim kliknie zapis. */

const $ = (id) => document.getElementById(id);

const PROFILE_ORDER = ["globalny", "cykl", "program"];
const PROFILE_LABELS = {
  globalny: "Globalny",
  cykl: "Cykl maszyny",
  program: "Program technologa",
};

let saved = null;          // ostatnie profile potwierdzone przez serwer
let profilesShape = {};    // { nazwa_profilu: [osie w kolejności wyświetlania] }
let activeProfile = null;
let machineBusy = false;   // RUNNING/HOMING — zapis odrzucany przez serwer

function num(value) {
  const v = String(value).trim().replace(",", ".");
  return v === "" ? NaN : Number(v);
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

function sortedProfileNames(names) {
  const known = PROFILE_ORDER.filter((n) => names.includes(n));
  const rest = names.filter((n) => !PROFILE_ORDER.includes(n)).sort();
  return known.concat(rest);
}

function sortedAxesOf(axesObj) {
  const keys = Object.keys(axesObj);
  const required = ["x", "y", "z"].filter((a) => keys.includes(a));
  const rest = keys.filter((a) => !required.includes(a)).sort();
  return required.concat(rest);
}

function fieldId(profile, axis, field) {
  return `f-${profile}-${axis}-${field}`;
}

function writeAxisParams(profile, axis, p) {
  $(fieldId(profile, axis, "velmax")).value = p.vel_max;
  $(fieldId(profile, axis, "accel")).value = p.accel;
  $(fieldId(profile, axis, "decel")).value = p.decel;
  $(fieldId(profile, axis, "torque")).value = p.torque_pct;
}

function readAxisParams(profile, axis) {
  return {
    vel_max: num($(fieldId(profile, axis, "velmax")).value),
    accel: num($(fieldId(profile, axis, "accel")).value),
    decel: num($(fieldId(profile, axis, "decel")).value),
    torque_pct: num($(fieldId(profile, axis, "torque")).value),
  };
}

function validateParams(profile, axis, p) {
  const label = `${PROFILE_LABELS[profile] || profile}, oś ${axis.toUpperCase()}`;
  const bad = [];
  if (!(p.vel_max > 0)) {
    bad.push([fieldId(profile, axis, "velmax"), `${label}: prędkość maksymalna musi być większa od zera`]);
  }
  if (!(p.accel > 0)) {
    bad.push([fieldId(profile, axis, "accel"), `${label}: przyspieszenie musi być większe od zera`]);
  }
  if (!(p.decel > 0)) {
    bad.push([fieldId(profile, axis, "decel"), `${label}: hamowanie musi być większe od zera`]);
  }
  if (!(p.torque_pct > 0 && p.torque_pct <= 100)) {
    bad.push([fieldId(profile, axis, "torque"), `${label}: limit momentu musi mieścić się w przedziale (0, 100] %`]);
  }
  return bad;
}

// --- budowa kart ------------------------------------------------------

function buildCards(profiles) {
  const grid = $("profiles-grid");
  grid.innerHTML = "";
  for (const name of sortedProfileNames(Object.keys(profiles))) {
    const isActive = name === activeProfile;
    const axesList = profilesShape[name];
    const rows = axesList
      .map((axis) => {
        const id = (field) => fieldId(name, axis, field);
        return (
          `<tr>` +
          `<td style="font-weight:700">${axis.toUpperCase()}</td>` +
          `<td><input id="${id("velmax")}" type="number" step="1" min="0"></td>` +
          `<td><input id="${id("accel")}" type="number" step="1" min="0"></td>` +
          `<td><input id="${id("decel")}" type="number" step="1" min="0"></td>` +
          `<td><input id="${id("torque")}" type="number" step="1" min="0" max="100"></td>` +
          `</tr>`
        );
      })
      .join("");

    const card = document.createElement("div");
    card.className = "panel";
    card.dataset.profile = name;
    card.innerHTML =
      `<h2>${PROFILE_LABELS[name] || name} ` +
      `<span class="axis-extra-badge active-badge" style="background:var(--ok); color:#06280f; ` +
      `display:${isActive ? "inline-block" : "none"}">AKTYWNY</span></h2>` +
      `<div class="table-scroll"><table class="profile-table"><thead><tr>` +
      `<th>Oś</th><th title="prędkość maksymalna">Vmax [mm/min]</th>` +
      `<th title="przyspieszenie">Przysp. [mm/s²]</th>` +
      `<th title="hamowanie">Hamow. [mm/s²]</th>` +
      `<th title="limit momentu silnika — dziś tylko w symulatorze">Moment [%]</th>` +
      `</tr></thead><tbody>${rows}</tbody></table></div>` +
      `<div class="btn-row activate-row" style="margin-top:10px; display:${isActive ? "none" : "flex"}">` +
      `<button class="small" data-action="activate">Aktywuj</button></div>`;
    grid.appendChild(card);

    for (const axis of axesList) writeAxisParams(name, axis, profiles[name].axes[axis]);
    card.querySelectorAll("input").forEach((el) => {
      el.addEventListener("input", refresh);
      el.addEventListener("change", refresh);
    });
    const btn = card.querySelector('[data-action="activate"]');
    if (btn) btn.onclick = () => activate(name);
  }
}

// --- walidacja ----------------------------------------------------------

function refresh() {
  const errors = [];
  document.querySelectorAll("#profiles-grid input").forEach((el) => el.classList.remove("bad"));

  for (const name in profilesShape) {
    for (const axis of profilesShape[name]) {
      const p = readAxisParams(name, axis);
      for (const [id, message] of validateParams(name, axis, p)) {
        $(id).classList.add("bad");
        errors.push(message);
      }
    }
  }

  const msg = $("profiles-msg");
  const saveBtn = $("btn-save");
  saveBtn.disabled = errors.length > 0 || machineBusy;
  if (errors.length) {
    showMsg(msg, errors.join("\n"));
    msg.style.whiteSpace = "pre-line";
  } else if (machineBusy) {
    showMsg(msg, "maszyna w ruchu — zapis profili jest zablokowany");
  } else {
    msg.className = "msg";
  }
  return errors.length === 0;
}

// --- aktywacja i zapis ----------------------------------------------------

async function activate(name) {
  try {
    await api("POST", "/api/profiles/active", { active: name });
  } catch (e) {
    showMsg($("profiles-msg"), e.message);
    return;
  }
  activeProfile = name;
  document.querySelectorAll("#profiles-grid [data-profile]").forEach((card) => {
    const isActive = card.dataset.profile === activeProfile;
    card.querySelector(".active-badge").style.display = isActive ? "inline-block" : "none";
    card.querySelector(".activate-row").style.display = isActive ? "none" : "flex";
  });
  showMsg($("profiles-msg"), `aktywny profil: ${PROFILE_LABELS[name] || name}`, true);
}

function applyProfiles(data) {
  saved = data.profiles;
  activeProfile = data.active;
  profilesShape = {};
  for (const name in saved) profilesShape[name] = sortedAxesOf(saved[name].axes);
  buildCards(saved);
  $("profiles-file").textContent = "Plik konfiguracji: " + data.file;
  refresh();
  if (data.warnings && data.warnings.length) {
    showMsg($("profiles-msg"), "Uwaga:\n" + data.warnings.join("\n"));
    $("profiles-msg").style.whiteSpace = "pre-line";
  }
}

async function loadProfiles() {
  applyProfiles(await api("GET", "/api/profiles"));
}

async function save() {
  if (!refresh()) return;
  const payload = { profiles: {}, active: activeProfile };
  for (const name in profilesShape) {
    payload.profiles[name] = { axes: {} };
    for (const axis of profilesShape[name]) {
      payload.profiles[name].axes[axis] = readAxisParams(name, axis);
    }
  }
  try {
    const data = await api("PUT", "/api/profiles", payload);
    applyProfiles(data);
    const extra = data.warnings && data.warnings.length ? "\nUwaga:\n" + data.warnings.join("\n") : "";
    showMsg($("profiles-msg"), "zapisano profile" + extra, true);
    $("profiles-msg").style.whiteSpace = "pre-line";
  } catch (e) {
    showMsg($("profiles-msg"), e.message);
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
$("btn-reload").onclick = () => loadProfiles().catch((e) => showMsg($("profiles-msg"), e.message));

loadProfiles().catch((e) =>
  showMsg($("profiles-msg"), "nie udało się wczytać profili: " + e.message)
);

pollState();
setInterval(pollState, 1500);
