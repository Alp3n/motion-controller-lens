#!/usr/bin/env bash
# Zakłada na pulpicie skrót uruchamiający całe środowisko maszyny.
# Ścieżka do repozytorium jest wpisywana na sztywno w skrót, więc po
# przeniesieniu katalogu trzeba uruchomić ten skrypt ponownie.

set -eu

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PULPIT="$(xdg-user-dir DESKTOP 2>/dev/null || true)"
[ -n "$PULPIT" ] && [ -d "$PULPIT" ] || PULPIT="$HOME/Pulpit"
mkdir -p "$PULPIT"

SKROT="$PULPIT/maszyna-odcinanie.desktop"

cat > "$SKROT" <<EOF
[Desktop Entry]
Type=Application
Version=1.0
Name=Maszyna — odcinanie wlewków
Comment=Uruchamia mostek, serwer maszyny i panel operatora
Exec=$ROOT/tools/uruchom-maszyne.sh
Path=$ROOT
Icon=applications-engineering
Terminal=true
Categories=Utility;
EOF

chmod +x "$SKROT" "$ROOT/tools/uruchom-maszyne.sh"

# GNOME uruchamia skrót dopiero po oznaczeniu go jako zaufany
if command -v gio >/dev/null; then
  gio set "$SKROT" metadata::trusted true 2>/dev/null || true
fi

echo "Skrót gotowy: $SKROT"
echo 'Jeśli pulpit pokazuje go jako „niezaufany plik”, kliknij prawym →'
echo '„Zezwól na uruchamianie” (jednorazowo, wymóg GNOME).'
