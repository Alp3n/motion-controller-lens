/* Ekran I/O Modbus (/io-modbus) — temat L.
 * Podgląd na żywo (odpytywanie /api/io-modbus co 1s, dane z pętli w tle
 * serwera, nie odczyt na żądanie) + edycja etykiet kanałów i watchdogu
 * (PUT /api/io-modbus) + ręczne przełączanie wyjść (POST
 * /api/machine/io-modbus/write). Wzorem zuzycie.js: fetch, nie WebSocket.
 */

const $ = (id) => document.getElementById(id);

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

function showCfgMsg(text, ok = false) {
  const el = $("cfg-msg");
  el.textContent = text;
  el.className = "msg " + (ok ? "ok" : "err");
}

function dot(on) {
  return `<span class="enable-dot${on ? " on" : ""}"></span>`;
}

// --- status na żywo ---------------------------------------------------------

function renderDi(di) {
  const names = Object.keys(di).sort();
  $("di-tabela").innerHTML = names
    .map((n) => {
      const c = di[n];
      return `<tr><td>${n}</td><td>${c.label || "—"}</td>
        <td>${dot(!!c.value)} ${c.value ? "1" : "0"}</td></tr>`;
    })
    .join("");
}

function renderAi(ai) {
  const names = Object.keys(ai).sort();
  $("ai-tabela").innerHTML = names
    .map((n) => {
      const c = ai[n];
      return `<tr><td>${n}</td><td>${c.label || "—"}</td><td>${c.value}</td></tr>`;
    })
    .join("");
}

async function toggleDo(name, current) {
  try {
    await api("POST", "/api/machine/io-modbus/write", { channel: name, on: !current });
  } catch (e) {
    showCfgMsg(e.message);
  }
}

function renderDo(doVals) {
  const names = Object.keys(doVals).sort();
  $("do-tabela").innerHTML = names
    .map((n) => {
      const c = doVals[n];
      return `<tr data-ch="${n}" data-val="${c.value ? 1 : 0}">
        <td>${n}</td><td>${c.label || "—"}</td>
        <td>${dot(!!c.value)} ${c.value ? "1" : "0"}</td>
        <td><button class="small" data-toggle="${n}">przełącz</button></td></tr>`;
    })
    .join("");
  $("do-tabela").querySelectorAll("[data-toggle]").forEach((btn) => {
    btn.onclick = () => {
      const tr = btn.closest("tr");
      toggleDo(tr.dataset.ch, tr.dataset.val === "1");
    };
  });
}

function renderWatchdog(wd) {
  const el = $("watchdog-status");
  if (!wd || !wd.enabled) {
    el.className = "msg";
    el.style.display = "block";
    el.textContent = "Watchdog wyłączony (włącz w sekcji konfiguracji poniżej, jeśli potrzebny).";
    return;
  }
  el.className = "msg " + (wd.ok ? "ok" : "err");
  el.style.display = "block";
  el.textContent =
    `Impuls (${wd.pulse_channel}): wiek ${wd.age_s ?? "—"}s ` +
    (wd.ok ? "— OK" : "— ZASTAŁY (brak zmiany dłużej niż próg)") +
    ` · osłona (${wd.guard_channel}): ${wd.guard_value ? "1" : "0"}`;
}

async function pollStatus() {
  try {
    const res = await api("GET", "/api/io-modbus");
    $("port-warn").style.display = "none";
    renderDi(res.status.di || {});
    renderDo(res.status.do || {});
    renderAi(res.status.ai || {});
    renderWatchdog(res.status.watchdog);
  } catch (e) {
    $("port-warn").style.display = "";
    $("port-warn").textContent = "Nie udało się pobrać stanu I/O: " + e.message;
  }
}

// --- konfiguracja (etykiety + watchdog) -------------------------------------

let cfg = null;

function renderCfgGroup(id, group) {
  const names = Object.keys(group).sort();
  $(id).innerHTML = names
    .map(
      (n) => `<tr><td>${n}</td><td>
        <input data-ch="${n}" value="${(group[n].label || "").replace(/"/g, "&quot;")}" style="width:100%">
      </td></tr>`
    )
    .join("");
}

function fillChannelSelect(sel, names, current) {
  sel.innerHTML = names.map((n) => `<option value="${n}">${n}</option>`).join("");
  sel.value = current;
}

function renderCfg() {
  renderCfgGroup("cfg-do", cfg.do);
  renderCfgGroup("cfg-di", cfg.di);
  renderCfgGroup("cfg-ai", cfg.ai);
  const diNames = Object.keys(cfg.di).sort();
  fillChannelSelect($("cfg-wd-pulse"), diNames, cfg.watchdog.pulse_channel);
  fillChannelSelect($("cfg-wd-guard"), diNames, cfg.watchdog.guard_channel);
  $("cfg-wd-enabled").checked = !!cfg.watchdog.enabled;
  $("cfg-wd-interval").value = cfg.watchdog.interval_s;
  $("cfg-wd-stale").value = cfg.watchdog.stale_after_s;
}

function readGroupFromForm(id, group) {
  const result = {};
  $(id)
    .querySelectorAll("input[data-ch]")
    .forEach((inp) => {
      result[inp.dataset.ch] = { label: inp.value.trim() };
    });
  return result;
}

async function zapiszCfg() {
  const body = {
    do: readGroupFromForm("cfg-do"),
    di: readGroupFromForm("cfg-di"),
    ai: readGroupFromForm("cfg-ai"),
    watchdog: {
      enabled: $("cfg-wd-enabled").checked,
      pulse_channel: $("cfg-wd-pulse").value,
      guard_channel: $("cfg-wd-guard").value,
      interval_s: Number($("cfg-wd-interval").value),
      stale_after_s: Number($("cfg-wd-stale").value),
    },
  };
  try {
    const res = await api("PUT", "/api/io-modbus", body);
    cfg = res.config;
    renderCfg();
    showCfgMsg("Zapisano.", true);
  } catch (e) {
    showCfgMsg(e.message);
  }
}

$("btn-zapisz-cfg").onclick = zapiszCfg;

async function loadCfgOnce() {
  try {
    const res = await api("GET", "/api/io-modbus");
    cfg = res.config;
    renderCfg();
  } catch (e) {
    showCfgMsg("Nie udało się wczytać konfiguracji: " + e.message);
  }
}

loadCfgOnce();
pollStatus();
setInterval(pollStatus, 1000);
