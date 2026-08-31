# Role, logowanie i dziennik zmian

Temat E planu rozwoju. **Decyzja (Twoja): osobne konta, nie wspólne PIN-y.**
Notatki proponowały kody `123321`/`456`/`789` na rolę — wspólny kod nie pozwala
ustalić, kto zmienił parametry siły i prędkości, a te wpływają na bezpieczeństwo.
Osobne konto plus dziennik zmian daje przypisanie zmiany do osoby.

Odblokowało to też ekran diagnostyczny z tematu G (`/diagnostics`, tylko admin).

## Dostęp wg roli

| Ekran | operator | technolog | admin |
| --- | :-: | :-: | :-: |
| Panel operatora `/` | ✓ | ✓ | ✓ |
| Edytor technologa `/editor` | | ✓ | ✓ |
| `/axes`, `/homing`, `/profiles`, `/cycle` | | | ✓ |
| Ekran diagnostyczny `/diagnostics` | | | ✓ |

Role są narastające: technolog może wszystko, co operator; admin — wszystko.

**Bez logowania (świadomie) działają:** `GET /api/status`, WebSocket statusu,
`POST /api/machine/stop` i ekran logowania. Powód STOP-u niżej.

## Pliki

- `server/app/users.py` — nowy: konta, hasła (PBKDF2-HMAC-SHA256, 600 000
  iteracji, losowa sól), role, sesje w pamięci, blokada po nieudanych próbach
- `server/app/audit.py` — nowy: dziennik zmian w formacie JSON Lines
- `server/app/config.py` — `USERS_FILE`, `AUDIT_FILE`, `SESSION_TTL`
- `server/app/main.py` — `/api/auth/{me,login,logout}`, zależności `require_role`,
  gating wszystkich ekranów i endpointów, wpisy do dziennika, `/api/diagnostics`
- `server/app/static/login.html`, `login.js`, `brak-dostepu.html` — nowe ekrany
- `server/app/static/sesja.js` — nowy: pasek „kto zalogowany + Wyloguj"
  w nagłówku każdego ekranu, ukrywanie odnośników poza rolą
- `server/app/static/diagnostics.html`, `diagnostics.js` — nowy ekran (temat G)
- `server/app/static/style.css` — pasek sesji, ekran logowania, tabele diagnostyki
- `tools/konta.py` — nowe narzędzie: `lista`, `dodaj`, `haslo`, `rola`, `usun`
- `server/tests/test_role.py` — 46 testów; `conftest.py` — pliki kont i dziennika
  w katalogu tymczasowym
- `.gitignore` — `config/users.json` i `config/dziennik-zmian.jsonl` poza gitem

## Zakładanie kont

```bash
tools/konta.py dodaj zbyszek --rola admin --imie "Zbigniew Walukiewicz"
tools/konta.py dodaj ania    --rola technolog --imie "Anna Nowak"
tools/konta.py dodaj oper1   --rola operator  --imie "Zmiana A"
```

Hasło narzędzie pyta interaktywnie (nigdy z argumentu — argument trafia do
historii powłoki i do listy procesów). Po zmianach trzeba **zrestartować serwer**:
plik kont wczytuje się przy starcie.

## Uwagi — bez zmiękczania

- **Dopóki nie ma pliku kont, logowanie jest wyłączone** i wszystkie ekrany są
  dostępne bez hasła. To celowe: maszyna, która dziś pracuje bez logowania, nie
  może po aktualizacji serwera zostać zablokowana przed operatorem. **Pierwsze
  `konta.py dodaj` włącza logowanie na całym panelu** — zrób to przy maszynie,
  nie zdalnie. Panel i ekran diagnostyczny wypisują wprost, gdy logowania nie ma.
- **To nie jest funkcja bezpieczeństwa maszyny.** Zatrzymanie awaryjne realizuje
  wyłącznie niezależny obwód sprzętowy (E-stop, Global Stop). Logowanie ogranicza
  dostęp do ekranów i nic poza tym.
- **`POST /api/machine/stop` celowo nie wymaga logowania.** Wygasła sesja nie może
  odebrać operatorowi możliwości zatrzymania maszyny z panelu. To świadomy wybór,
  nie przeoczenie — pilnuje go test.
- **Panel chodzi po zwykłym HTTP.** Hasło i ciasteczko sesji idą przez sieć
  otwartym tekstem; kto ma dostęp do tej samej sieci, może je podejrzeć. Ma sens
  dopiero w odseparowanej sieci maszynowej albo po postawieniu HTTPS. Ekran
  logowania mówi to wprost.
- **API dla MES (`POST /api/mes/select-order`) zostaje bez logowania.** Wywołuje
  je system, nie człowiek — dołożenie tam hasła zerwałoby integrację. To istniejąca
  wcześniej dziura, której ta zmiana **nie zamyka**; do zrobienia osobno (token dla
  MES albo ograniczenie na poziomie sieci). Dopisane do planu rozwoju jako otwarte.
- **Sesje żyją w pamięci procesu** — restart serwera wylogowuje wszystkich.
  Świadomy wybór: nie ma sekretu do przechowywania i do wycieku. Ważność liczona
  od ostatniego użycia (domyślnie 12 h, `SESSION_TTL`), bo panel stoi otwarty całą
  zmianę.
- **Dziennik zmian nie jest odporny na manipulację.** Plik leży na tym samym
  komputerze — kto ma dostęp systemowy, może go zmienić. To zapis „kto ostatnio
  ruszał parametry", nie rejestr audytowy w sensie formalnym. Błąd zapisu dziennika
  celowo **nie** przerywa operacji maszyny: brak miejsca na dysku nie może
  zatrzymać produkcji przez dziennik.
- **Kont nie da się zakładać z panelu.** Przejęta sesja admina nie może sobie
  założyć kolejnego konta ani podnieść roli — trzeba mieć dostęp do komputera.
- **Ukrywanie odnośników w nagłówku to wygoda, nie zabezpieczenie.** Dostępu
  pilnuje serwer przy każdym żądaniu; ukryty link tylko oszczędza klikania
  w ekran „brak uprawnień".
- Przegląd obwodu bezpieczeństwa z osobą uprawnioną (CE, PN-EN ISO 13849-1)
  **dalej jest do zrobienia** — ta zmiana go nie zastępuje ani nie przybliża.
