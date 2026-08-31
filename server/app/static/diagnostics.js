/* Ekran diagnostyczny (temat G, tylko admin): stan maszyny, praca ręczna /
   półautomatyczna / automatyczna, przegląd konfiguracji i dziennik zmian.
   Wszystko z jednego wywołania /api/diagnostics + statusu na żywo. */

const $ = (id) => document.getElementById(id);

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

function td(...cells) {
  const tr = document.createElement("tr");
  tr.innerHTML = cells.map((c) => `<td>${c}</td>`).join("");
  return tr;
}

function kv(tbody, label, value) {
  tbody.appendChild(td(`<span class="muted">${label}</span>`, `<b>${value}</b>`));
}

function mm(v) {
  return Number(v).toFixed(3).replace(/\.?0+$/, "");
}

function tak(v) {
  return v ? "tak" : "nie";
}

// --- status na żywo -------------------------------------------------------

function applyStatus(st) {
  const badge = $("state");
  badge.textContent = st.state;
  badge.className = "state-badge state-" + st.state;
  $("enable-dot").className = "enable-dot" + (st.safety_enable ? " on" : "");
  $("enable-text").textContent =
    "sygnał zezwolenia: " + (st.safety_enable ? "AKTYWNY" : "BRAK");
  // pusty komunikat musi też zdjąć klasę, inaczej zostaje pusty czerwony pas
  const alarm = $("alarm");
  if (st.alarm_message) {
    alarm.textContent = "ALARM: " + st.alarm_message;
    alarm.className = "msg err";
  } else {
    alarm.textContent = "";
    alarm.className = "msg";
  }

  const tbody = $("machine-kv");
  tbody.innerHTML = "";
  kv(tbody, "Pozycja", `X ${mm(st.position.x)}  Y ${mm(st.position.y)}  Z ${mm(st.position.z)} mm`);
  kv(tbody, "Wrzeciono", st.spindle_on ? "ZAŁ" : "WYŁ");
  kv(tbody, "Profil aktywny", st.active_profile || "—");
  kv(tbody, "Program", st.program_number ? `${st.program_number} ${st.program_name}` : "—");
  kv(tbody, "Operacja", st.current_op ? `${st.current_op} / ${st.total_ops}` : "—");
  kv(tbody, "Krok cyklu", st.cycle_step ? `${st.cycle_step} / ${st.total_cycle_steps}` : "—");
  kv(tbody, "Tryb automatyczny", tak(st.cycle_loop));
  kv(tbody, "Osie zluzowane", (st.released_axes || []).join(", ").toUpperCase() || "—");
  kv(
    tbody,
    "Wyjścia",
    Object.entries(st.outputs || {})
      .map(([k, v]) => `${k}=${v ? "ZAŁ" : "wył"}`)
      .join("  ") || "—"
  );
}

// --- jednorazowy zrzut diagnostyczny --------------------------------------

function applyDiagnostics(d) {
  const gaps = $("safety-gaps");
  gaps.innerHTML = "";
  for (const item of d.safety.brak) {
    const li = document.createElement("li");
    li.textContent = item;
    gaps.appendChild(li);
  }

  const warnBox = $("config-warnings");
  warnBox.innerHTML = "";
  const all = []
    .concat(d.config.axes_warnings || [])
    .concat(d.config.homing.warnings || [])
    .concat(d.config.profile_warnings || [])
    .concat(d.config.cycle_warnings || [])
    .concat(d.config.spindle.warnings || []);
  if (all.length) {
    const p = document.createElement("p");
    showMsg(p, "Uwagi do konfiguracji:\n• " + all.join("\n• "));
    warnBox.appendChild(p);
  }

  const axesBody = $("cfg-axes");
  axesBody.innerHTML = "";
  for (const [name, cfg] of Object.entries(d.config.axes)) {
    axesBody.appendChild(
      td(
        `<b>${name.toUpperCase()}</b>`,
        `${mm(cfg.soft_min)} … ${mm(cfg.soft_max)}`,
        mm(cfg.mm_per_rev),
        mm(cfg.vel_jog)
      )
    );
  }

  const homingBody = $("cfg-homing");
  homingBody.innerHTML = "";
  for (const [name, cfg] of Object.entries(d.config.homing.axes)) {
    homingBody.appendChild(
      td(
        `<b>${name.toUpperCase()}</b>`,
        cfg.home_order || "<span class='muted'>nie bazuj</span>",
        cfg.home_mode,
        mm(cfg.home_torque),
        mm(cfg.home_offset)
      )
    );
  }

  const profBody = $("cfg-profiles");
  profBody.innerHTML = "";
  for (const [name, prof] of Object.entries(d.config.profiles)) {
    const axesNames = Object.keys(prof.axes || prof).join(", ").toUpperCase();
    profBody.appendChild(
      td(
        `<b>${name}</b>`,
        axesNames,
        name === d.config.active_profile ? "✓" : ""
      )
    );
  }

  const sp = $("cfg-spindle");
  sp.innerHTML = "";
  kv(sp, "Rusza z maszyną", tak(d.config.spindle.spindle.start_with_machine));
  kv(sp, "Załącz na starcie programu", tak(d.config.spindle.spindle.start_with_program));
  kv(sp, "Wyłącz po programie", tak(d.config.spindle.spindle.stop_after_program));
  kv(sp, "Obroty domyślne", d.config.spindle.spindle.default_rpm + " (informacyjne)");

  const steps = (d.config.cycle.steps || []).length;
  $("cfg-cycle").textContent = steps
    ? `${steps} kroków: ` +
      d.config.cycle.steps.map((s) => `${s.lp}. ${s.kind}`).join(", ")
    : "cykl nie jest zdefiniowany";

  const usersBody = $("users-rows");
  usersBody.innerHTML = "";
  for (const u of d.auth.users) {
    usersBody.appendChild(td(`<b>${u.login}</b>`, u.name, u.role));
  }
  $("auth-summary").textContent = d.auth.enabled
    ? `Logowanie włączone. Kont: ${d.auth.users.length}, aktywnych sesji: ` +
      `${d.auth.active_sessions}. Plik: ${d.auth.file}`
    : `LOGOWANIE WYŁĄCZONE — nie ma pliku kont (${d.auth.file}). ` +
      "Wszystkie ekrany są dostępne bez hasła.";

  const auditBody = $("audit-rows");
  auditBody.innerHTML = "";
  for (const e of d.audit.entries) {
    auditBody.appendChild(
      td(e.czas, e.login, e.rola, e.akcja, e.szczegoly || "")
    );
  }
  $("audit-summary").textContent = d.audit.exists
    ? `Plik: ${d.audit.file} — ostatnie ${d.audit.entries.length} wpisów.`
    : `Dziennik jeszcze nie istnieje (${d.audit.file}) — powstanie przy pierwszej ` +
      "zapisanej zmianie konfiguracji.";
}

// --- akcje ----------------------------------------------------------------

const act = (url, body) => () =>
  api("POST", url, body)
    .then(() => showMsg($("ctrl-msg"), "wysłano", true))
    .catch((e) => showMsg($("ctrl-msg"), e.message));

$("btn-home").onclick = act("/api/machine/home");
$("btn-cycle").onclick = act("/api/machine/cycle/start", { loop: false });
$("btn-loop").onclick = act("/api/machine/cycle/start", { loop: true });
$("btn-stop").onclick = act("/api/machine/stop");

// --- odświeżanie ----------------------------------------------------------

function pollStatus() {
  api("GET", "/api/status").then(applyStatus).catch(() => {});
}

function loadDiagnostics() {
  api("GET", "/api/diagnostics")
    .then(applyDiagnostics)
    .catch((e) => showMsg($("ctrl-msg"), "nie udało się wczytać diagnostyki: " + e.message));
}

pollStatus();
loadDiagnostics();
setInterval(pollStatus, 1000);
/* Konfiguracja i dziennik zmieniają się rzadko — rzadszy odczyt niż status,
   ale wystarczająco często, żeby ekran nie kłamał po zmianie na innej karcie. */
setInterval(loadDiagnostics, 15000);
