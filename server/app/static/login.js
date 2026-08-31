/* Ekran logowania. Po zalogowaniu wraca tam, skąd przyszło przekierowanie
   (parametr `cel` dokładany przez serwer w app/main.py, `_page`). */

const $ = (id) => document.getElementById(id);

/* Cel przekierowania bierzemy tylko wtedy, gdy jest ścieżką w tym samym
   serwisie — inaczej link z parametrem `cel=//obcy.host` wyprowadzałby
   operatora poza panel zaraz po podaniu hasła. */
function safeTarget() {
  const raw = new URLSearchParams(location.search).get("cel") || "/";
  return /^\/[^/\\]/.test(raw) || raw === "/" ? raw : "/";
}

function showMsg(text, ok = false) {
  const el = $("login-msg");
  el.textContent = text;
  el.className = "msg " + (ok ? "ok" : "err");
}

async function submit(ev) {
  ev.preventDefault();
  const btn = $("btn-login");
  btn.disabled = true;
  try {
    const res = await fetch("/api/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        login: $("f-login").value,
        password: $("f-password").value,
      }),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.detail || res.statusText);
    location.href = safeTarget();
  } catch (e) {
    showMsg(e.message);
    $("f-password").value = "";
    $("f-password").focus();
  } finally {
    btn.disabled = false;
  }
}

$("login-form").addEventListener("submit", submit);

/* Gdy logowanie jest wyłączone (brak pliku kont), formularz nie ma sensu —
   mówimy to wprost zamiast pozwalać wpisywać hasło w próżnię. */
fetch("/api/auth/me")
  .then((r) => r.json())
  .then((data) => {
    if (!data.auth_enabled) {
      showMsg(
        "Na tym serwerze nie założono jeszcze żadnego konta — logowanie jest " +
          "wyłączone i wszystkie ekrany są dostępne bez hasła. " +
          "Konta zakłada się narzędziem tools/konta.py."
      );
      $("btn-login").disabled = true;
    } else if (data.user) {
      showMsg(`Zalogowany jako ${data.user.name} (${data.user.role}).`, true);
    }
  })
  .catch(() => {
    /* brak odpowiedzi nie ma blokować formularza — logowanie i tak sprawdzi serwer */
  });

$("f-login").focus();
