# Naprawa: ekran /axes kasował driver=feetech przy zapisie

Zapisanie zwykłej zmiany (np. `vel_jog`) z ekranu `/axes` dla osi `docisk`/
`podajnik` po cichu cofało im `driver` z `feetech` na domyślne `teknic` i
`feetech_id` na `null` — dokładnie ten sam błąd, co już raz się zdarzył dla
pól bazowania, patrz [[predkosci-jog-bazowanie]].

## Przyczyna

`server/app/axes.py`, funkcja `with_current_values()` — pola, których dany
zapis nie przesyła, mają zostać przepisane z bieżącej konfiguracji, ale
lista takich pól (`OPTIONAL_FIELDS`) nie zawierała `driver`/`feetech_id`.
Ekran `/axes` nic nie wie o Feetech i tych pól nie wysyła, więc
`AxisConfig.from_dict()` wstawiał wartości domyślne zamiast zachować to, co
było zapisane.

Odkryte 2026-09-11 nie przez zgłoszenie użytkownika, tylko przez zauważenie
zmiany pliku `config/axes.json` na dysku po użyciu ekranu `/axes` do zmiany
`vel_jog`/`home_order` dla `docisk`/`podajnik`.

## Pliki

- `server/app/axes.py` — `OPTIONAL_FIELDS = ("vel_jog", "driver", "feetech_id") + HOMING_FIELDS`.
- `server/tests/test_axes.py` — `test_with_current_values_zachowuje_driver_i_feetech_id`,
  regresja odtwarzająca dokładnie ten scenariusz.
- `config/axes.json` — ręcznie przywrócone `docisk` (`feetech_id: 1`) i
  `podajnik` (`feetech_id: 2`) do `driver: feetech`; dane popsute przez błąd,
  nie kod, więc naprawa kodu sama tego nie cofnęła.

## Uwagi

To druga tego samego rodzaju usterka w `OPTIONAL_FIELDS` (pierwsza:
`vel_jog`/pola bazowania). Wzorzec do pilnowania na przyszłość: **każde nowe
pole `AxisConfig`, którego nie edytuje ekran `/axes`, musi trafić do
`OPTIONAL_FIELDS`**, inaczej pierwszy zapis z tego ekranu je skasuje.
