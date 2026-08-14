/* Panel operatora — status przez WebSocket, sterowanie przez REST API. */

const $ = (id) => document.getElementById(id);

let currentProgram = null; // ostatnio załadowany program (operacje do tabeli)
let simMode = false;

function fmt(v) {
  return v === null || v === undefined ? "" : Number(v).toFixed(3);
}

function showMsg(el, text, ok = false) {
  el.textContent = text;
  el.className = "msg " + (ok ? "ok" : "err");
  setTimeout(() => (el.className = "msg"), 6000);
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

// --- status na żywo -------------------------------------------------------

function applyStatus(st) {
  const stateEl = $("state");
  stateEl.textContent = st.state;
  stateEl.className = "state-badge state-" + st.state;

  $("enable-dot").className = "enable-dot" + (st.safety_enable ? " on" : "");
  $("enable-text").textContent =
    "sygnał zezwolenia: " + (st.safety_enable ? "AKTYWNY" : "BRAK — ruch zablokowany");

  const alarm = $("alarm");
  if (st.alarm_message) {
    alarm.textContent = "ALARM: " + st.alarm_message;
    alarm.className = "msg err";
  } else {
    alarm.className = "msg";
  }

  $("order").textContent = st.order_id || "—";
  $("prog-number").textContent = st.program_number || "—";
  $("prog-name").textContent = st.program_name || "—";
  $("pos-x").textContent = fmt(st.position.x);
  $("pos-y").textContent = fmt(st.position.y);
  $("pos-z").textContent = fmt(st.position.z);
  $("spindle").textContent = st.spindle_on ? "ZAŁ" : "WYŁ";

  document.querySelectorAll("#ops tr").forEach((tr) => {
    const lp = Number(tr.dataset.lp);
    tr.className =
      st.current_op === lp ? "current" : st.current_op && lp < st.current_op ? "done" : "";
  });
  $("progress").textContent = st.current_op
    ? `operacja ${st.current_op} z ${st.total_ops}`
    : "";

  const startBtn = $("btn-start");
  startBtn.textContent = st.state === "PAUSED" ? "WZNÓW" : "START";

  if (st.program_number && (!currentProgram || currentProgram.number !== st.program_number)) {
    loadProgramTable(st.program_number);
  }
}

function connectWs() {
  const ws = new WebSocket(
    (location.protocol === "https:" ? "wss://" : "ws://") + location.host + "/ws/status"
  );
  ws.onmessage = (ev) => applyStatus(JSON.parse(ev.data));
  ws.onclose = () => setTimeout(connectWs, 1000);
}

async function loadProgramTable(number) {
  try {
    const data = await api("GET", `/api/programs/${number}`);
    if (!data.parsed) return;
    currentProgram = data.parsed;
    const tbody = $("ops");
    tbody.innerHTML = "";
    for (const op of currentProgram.operations) {
      const tr = document.createElement("tr");
      tr.dataset.lp = op.lp;
      tr.innerHTML =
        `<td>${op.lp}</td><td>${op.op_type}</td>` +
        `<td>${fmt(op.x)}</td><td>${fmt(op.y)}</td><td>${fmt(op.z)}</td>` +
        `<td>${fmt(op.x2)}</td><td>${fmt(op.y2)}</td><td></td>`;
      tr.lastElementChild.textContent = op.note || "";
      tbody.appendChild(tr);
    }
  } catch (e) {
    /* tabela pozostaje pusta; błąd pokaże się przy próbie startu */
  }
}

// --- sterowanie -----------------------------------------------------------

$("btn-start").onclick = () =>
  api("POST", "/api/machine/start").catch((e) => showMsg($("ctrl-msg"), e.message));
$("btn-stop").onclick = () =>
  api("POST", "/api/machine/stop").catch((e) => showMsg($("ctrl-msg"), e.message));
$("btn-home").onclick = () =>
  api("POST", "/api/machine/home").catch((e) => showMsg($("ctrl-msg"), e.message));
$("btn-reset").onclick = () =>
  api("POST", "/api/machine/reset").catch((e) => showMsg($("ctrl-msg"), e.message));

document.querySelectorAll(".jog").forEach((btn) => {
  btn.onclick = () => {
    const distance = Number($("jog-step").value) * Number(btn.dataset.dir);
    api("POST", "/api/machine/jog", { axis: btn.dataset.axis, distance }).catch((e) =>
      showMsg($("ctrl-msg"), e.message)
    );
  };
});

$("btn-mes").onclick = async () => {
  const order = $("mes-order").value.trim();
  const program = $("mes-program").value.trim();
  if (!/^\d{12}$/.test(program)) {
    showMsg($("mes-msg"), "numer programu musi mieć dokładnie 12 cyfr");
    return;
  }
  try {
    const data = await api("POST", "/api/mes/select-order", {
      order_id: order || "TEST",
      program_number: program,
    });
    currentProgram = null; // wymuś przeładowanie tabeli operacji
    showMsg($("mes-msg"), `załadowano program: ${data.program.name}`, true);
  } catch (e) {
    showMsg($("mes-msg"), e.message);
  }
};

// przełącznik zezwolenia dostępny tylko w symulacji
$("sim-enable").onchange = (ev) =>
  api("POST", "/api/sim/safety-enable", { enabled: ev.target.checked }).catch(() => {});

api("POST", "/api/sim/safety-enable", { enabled: true })
  .then(() => {
    simMode = true;
    $("sim-enable-row").style.display = "block";
    $("sim-enable").checked = true;
  })
  .catch(() => {});

connectWs();
