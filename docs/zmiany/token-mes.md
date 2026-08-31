# Token dla integracji MES

`POST /api/mes/select-order` wywołuje system MES, nie człowiek — nie pasuje
do sesji/ciasteczka z warstwy ról. Dodany osobny token w nagłówku, opcjonalny:
bez ustawienia `MES_TOKEN` endpoint zostaje otwarty jak dotychczas (temat E,
punkt zostawiony otwarty przy `zmiany/role-i-logowanie.md`).

## Pliki

- `server/app/config.py` — `MES_TOKEN` ze zmiennej środowiskowej (domyślnie
  `None` = wyłączony)
- `server/app/main.py` — `require_mes_token()`, `secrets.compare_digest`
  (porównanie odporne na atak czasowy), dopięte jako zależność do
  `POST /api/mes/select-order`
- `server/tests/test_api.py` — cztery testy: domyślnie otwarty, wymaga
  tokenu gdy ustawiony, odrzuca zły, akceptuje poprawny

## Uwagi

- **Domyślnie nic się nie zmienia.** Dopóki nikt nie ustawi `MES_TOKEN` w
  środowisku usługi, endpoint działa dokładnie jak wcześniej — bez tego MES,
  który dziś nie ma czym się przedstawić, straciłby integrację po aktualizacji.
- Żeby włączyć: dopisać `Environment=MES_TOKEN=<losowy-sekret>` do
  `/etc/systemd/system/motion-controller-lens.service`, `daemon-reload` +
  restart, i skonfigurować MES, żeby wysyłał nagłówek `X-MES-Token: <ten sam
  sekret>`. **Nie zrobione na tej maszynie** — kod jest gotowy i przetestowany,
  ale włączenie wymaga koordynacji z konfiguracją MES (inaczej integracja
  przestanie działać z dnia na dzień) i restartu usługi.
- Chodzi po zwykłym HTTP, jak reszta panelu — token w nagłówku idzie jawnym
  tekstem w sieci. Ma sens dopiero w odseparowanej sieci maszynowej albo po
  HTTPS, tak samo jak zastrzeżenie przy hasłach operatora
  (`zmiany/role-i-logowanie.md`).
- Nie zastępuje ograniczenia na poziomie sieci (firewall/VLAN) — to
  alternatywa albo uzupełnienie, do wyboru zależnie od tego, jak MES jest
  fizycznie podłączony.
