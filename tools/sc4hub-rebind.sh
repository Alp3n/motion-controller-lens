#!/bin/bash
# Przypina SC4-Hub do sterownika Exar (cdc_xr_usb_serial), odpinając go od cdc_acm.
#
# Po każdej ponownej enumeracji huba (reset zasilania, przewtyknięcie kabla)
# cdc_acm przejmuje urządzenie i sFoundation przestaje je widzieć. Ten skrypt
# przywraca właściwe przypięcie. Wymaga roota.
#
# Użycie:  sudo ./sc4hub-rebind.sh
set -euo pipefail

VIDPID=v2890p0213          # Teknic ClearPath 4-axis Comm Hub (2890:0213)
XR=/sys/bus/usb/drivers/cdc_xr_usb_serial
ACM=/sys/bus/usb/drivers/cdc_acm

if [[ ${EUID:-0} -ne 0 ]]; then
    echo "Uruchom jako root: sudo $0" >&2
    exit 1
fi

# Moduł Exar musi być załadowany, inaczej nie ma do czego przypinać.
if [[ ! -d "$XR" ]]; then
    modprobe xr_usb_serial_common 2>/dev/null || true
fi
if [[ ! -d "$XR" ]]; then
    echo "Brak sterownika cdc_xr_usb_serial. Zainstaluj go skryptem Teknica:" >&2
    echo "  vendor/teknic/Linux_Software/Teknic_SC4Hub_USB_Driver/ExarKernelDriver/Install_DRV_SCRIPT.sh" >&2
    exit 1
fi

found=0
for modalias in /sys/bus/usb/devices/*/modalias; do
    grep -q "$VIDPID" "$modalias" 2>/dev/null || continue
    iface=$(basename "$(dirname "$modalias")")
    # interesują nas wyłącznie interfejsy (mają dwukropek: 2-1.2:1.0)
    [[ "$iface" == *:* ]] || continue
    found=1

    if [[ -e "$ACM/$iface" ]]; then
        echo -n "$iface" > "$ACM/unbind"
        echo "odpięto $iface od cdc_acm"
    fi
    if [[ ! -e "$XR/$iface" ]]; then
        echo -n "$iface" > "$XR/bind"
        echo "przypięto $iface do cdc_xr_usb_serial"
    else
        echo "$iface już na cdc_xr_usb_serial"
    fi
done

if [[ $found -eq 0 ]]; then
    echo "Nie znaleziono SC4-Hub (2890:0213). Sprawdź kabel USB i zasilanie 24 V huba." >&2
    exit 1
fi

echo "--- porty ---"
ls -l /dev/ttyXRUSB* 2>/dev/null || echo "UWAGA: brak /dev/ttyXRUSB* — przypięcie nie zadziałało"
