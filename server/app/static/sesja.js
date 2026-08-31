/* Wspólny pasek sesji w nagłówku — kto jest zalogowany i przycisk wylogowania.
   Dokładany do każdego ekranu panelu, żeby nie powtarzać tego w sześciu
   plikach. Ukrywa też odnośniki do ekranów, do których rola nie ma wstępu:
   to wygoda, nie zabezpieczenie — dostępu pilnuje serwer (app/main.py). */

(function () {
  const ROLES = ["operator", "technolog", "admin"];

  // ścieżka -> minimalna rola; musi odpowiadać trasom w app/main.py
  const WYMAGANA_ROLA = {
    "/": "operator",
    "/editor": "technolog",
    "/axes": "admin",
    "/homing": "admin",
    "/profiles": "admin",
    "/cycle": "admin",
    "/diagnostics": "admin",
  };

  function wystarcza(rola, wymagana) {
    return ROLES.indexOf(rola) >= ROLES.indexOf(wymagana);
  }

  function ukryjNiedostepneLinki(rola) {
    document.querySelectorAll("header a[href]").forEach((a) => {
      const wymagana = WYMAGANA_ROLA[a.getAttribute("href")];
      if (wymagana && !wystarcza(rola, wymagana)) a.remove();
    });
  }

  /* Ekran diagnostyczny (temat G) jest tylko dla admina, więc odnośnika nie ma
     w statycznym HTML — dokładamy go dopiero, gdy wiadomo, kto patrzy. */
  function dodajLinkDiagnostyki(header) {
    if (location.pathname === "/diagnostics") return;
    if (header.querySelector('a[href="/diagnostics"]')) return;
    const a = document.createElement("a");
    a.href = "/diagnostics";
    a.textContent = "Diagnostyka";
    header.appendChild(a);
  }

  function pasek(header, data) {
    const box = document.createElement("div");
    box.className = "user-box";
    if (!data.auth_enabled) {
      box.innerHTML =
        '<span class="who" title="Nie założono żadnego konta — wszystkie ekrany ' +
        'są dostępne bez hasła. Konta zakłada tools/konta.py.">logowanie wyłączone</span>';
      header.appendChild(box);
      return;
    }
    box.innerHTML =
      `<span class="who">${data.user.name}</span>` +
      `<span class="rola">${data.user.role}</span>`;
    const btn = document.createElement("button");
    btn.className = "small";
    btn.textContent = "Wyloguj";
    btn.onclick = () =>
      fetch("/api/auth/logout", { method: "POST" }).then(
        () => (location.href = "/login")
      );
    box.appendChild(btn);
    header.appendChild(box);
  }

  const header = document.querySelector("header");
  if (!header) return;

  fetch("/api/auth/me")
    .then((r) => r.json())
    .then((data) => {
      if (data.auth_enabled && data.user) {
        ukryjNiedostepneLinki(data.user.role);
        if (data.user.role === "admin") dodajLinkDiagnostyki(header);
      } else if (!data.auth_enabled) {
        dodajLinkDiagnostyki(header);
      }
      pasek(header, data);
    })
    .catch(() => {
      /* brak odpowiedzi nie ma psuć ekranu — nagłówek zostaje bez paska sesji */
    });
})();
