# JOG dla osi FEETECH (temat L, etap 2 — częściowy)

`POST /api/machine/jog-feetech` + przyciski na panelu głównym — ruch osi
`docisk`/`podajnik` w kierunku **zgodnym/przeciwnym do zegara**
(`DIRECTION_SIGN_CW`, zmierzone fizycznie 2026-09-10), **nie w mm**.
Zrobione świadomie bez montażu do mechanizmu — użytkownik: „robimy serwa
bez montowania na maszynie" (2026-09-11). Przelicznik na mm (i to, czy CW
odpowiada rosnącemu czy malejącemu mm wzdłuż osi) czeka na fizyczne
zamontowanie — osobna kalibracja, nie zrobiona tutaj.

## Pliki

- `server/app/main.py` — `JogFeetechRequest`, `POST
  /api/machine/jog-feetech` (`require_operator`, jak zwykły JOG X/Y/Z),
  `_feetech_jog()` (blokujące, przez `asyncio.to_thread`, wzorem
  `_read_feetech_status`). **Świadomie NIE przez `Machine.jog()`** — osobna
  ścieżka, zero zmian w kodzie sterującym X/Y/Z (decyzja architektoniczna
  z `architektura-wielu-drajwerow-osi.md`: Feetech obok, nie w środku).
- `server/app/config.py` — `FEETECH_JOG_STEP` (kroki enkodera na jedno
  wywołanie, domyślnie 30).
- `server/app/static/index.html`, `app.js` — przyciski „↺ przeciwnie" /
  „↻ zgodnie" w panelu „Osie dodatkowe (FEETECH)", wzorem JOG X/Y/Z
  (przytrzymanie = ruch, jak „martwy człowiek"), ale osobny stan
  (`feetechJogHold`) i wolniejszy takt (250ms, nie 50ms — magistrala
  RS485 z odczytem+zapisem po termios jest wyraźnie wolniejsza niż TCP do
  mostka Teknica). Przyciski budowane RAZ per zestaw osi, nie przy każdej
  aktualizacji statusu z WebSocketu — inaczej przerysowanie co ~200ms
  gubiłoby trzymany przycisk.
- `server/tests/test_feetech_jog.py` — 6 testów (routing, walidacja,
  znak kroku cw/ccw, błędy 404/409), `_feetech_jog` podstawiony fakem.

## Naprawiony błąd współbieżności (zaraz po pierwszym teście fizycznym)

Pierwszy test na sprzęcie: JOG na `podajnik` + odczyt statusu chwilę
później dał `docisk: "brak odpowiedzi z serwa (timeout)"`, mimo że
elektrycznie wszystko było sprawne. Przyczyna: magistrala RS485 jest
**fizycznie jedna, półdupleksowa** — `_feetech_poll_loop` (odczyt co ~1s)
i `/api/machine/jog-feetech` (na żądanie) to dwa NIEZALEŻNE zadania
asyncio, które mogły otworzyć port i nadawać jednocześnie, kolidując na
przewodzie.

**Naprawa:** `_feetech_lock` (`asyncio.Lock()`) obejmuje CAŁĄ transakcję
(otwarcie portu, transfer, zamknięcie) w obu miejscach — pętli
odpytującej i JOG-u. Zweryfikowane: 3 kolejne wywołania JOG + odczyt
statusu zaraz po, bez błędu.

## Uwagi

- **Kierunek CW/CCW, nie „+"/„-"** — celowo, żeby nie sugerować
  nieistniejącej jeszcze kalibracji mm. Przyciski opisane strzałkami
  obrotu (↺/↻), nie znakiem.
- `load` w odczycie statusu podczas ruchu potrafi pokazać wartości > 1000
  (zaobserwowane: 1032, 1052) — **jednostka/skala tego pola wciąż nie jest
  potwierdzona** (patrz zastrzeżenie w `zmiany/protokol-feetech.md`), to
  tylko obserwacja, nie zinterpretowana.
- Zweryfikowane fizycznie na obu serwach, oba kierunki, zgodnie z
  wcześniej zmierzonym `DIRECTION_SIGN_CW` — `docisk` CW zmniejsza
  pozycję, `podajnik` CW zwiększa, dokładnie jak oczekiwano.
- **Serwa dalej nie są zamontowane do mechanizmu** — ten endpoint rusza
  tylko wolnym wałem. Kalibracja mm i realne testy z docisku/podajnikiem
  pod obciążeniem to osobny, przyszły krok.
