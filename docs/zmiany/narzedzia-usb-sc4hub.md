# Narzędzia do przypinania SC4-Hub (USB)

Po każdej ponownej enumeracji huba (włączenie 24 V, przewtyknięcie kabla)
sterownik `cdc_acm` przejmuje urządzenie i sFoundation przestaje je widzieć.
Skrypt instalacyjny Teknica przepina je tylko **jednorazowo**, więc dołożono
własne narzędzia.

## Pliki

- `tools/sc4hub-rebind.sh` — odpina oba interfejsy huba (`2890:0213`) od
  `cdc_acm` i przypina do `cdc_xr_usb_serial`; ładuje moduł, jeśli trzeba.
  Wymaga roota, trwa sekundę (nie przebudowuje modułu).
- `tools/99-teknic-sc4hub.rules` — reguła udev wywołująca powyższy skrypt
  automatycznie, gdy `cdc_acm` przypnie się do huba. Instalacja opisana
  w nagłówku pliku.
- `.gitignore` — dodano `vendor/` (SDK Teknica pobierane ze strony producenta).

## Uwagi

- Reguła udev **nie jest jeszcze zainstalowana ani zweryfikowana** — do
  sprawdzenia przez przewtyknięcie huba.
- Alternatywa na dedykowanym komputerze maszyny: czarna lista `cdc_acm`
  w modprobe. Prostsza i bez wyścigów, ale wyłącza inne urządzenia CDC-ACM
  (Arduino, modemy USB), więc nie nadaje się na stację roboczą.
