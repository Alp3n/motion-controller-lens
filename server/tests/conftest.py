"""Wspólne ustawienia testów.

Konfiguracja osi, profili, cyklu i wrzeciona musi wskazywać na pliki
tymczasowe, zanim zaimportuje się aplikacja — inaczej testy czytałyby
(i nadpisywały) konfigurację maszyny.
"""

import os
import tempfile

_tmp = tempfile.mkdtemp(prefix="cfg-test-")

os.environ.setdefault("AXES_CONFIG", os.path.join(_tmp, "axes.json"))
os.environ.setdefault("PROFILES_CONFIG", os.path.join(_tmp, "profiles.json"))
os.environ.setdefault("CYCLE_CONFIG", os.path.join(_tmp, "cycle.json"))
os.environ.setdefault("SPINDLE_CONFIG", os.path.join(_tmp, "spindle.json"))
os.environ.setdefault("OUTPUTS_CONFIG", os.path.join(_tmp, "wyjscia.json"))
# Konta: plik celowo NIE istnieje — większość testów sprawdza API bez logowania.
# Warstwę ról testuje test_role.py, który przeładowuje aplikację z własnym plikiem.
os.environ.setdefault("USERS_CONFIG", os.path.join(_tmp, "users.json"))
os.environ.setdefault("AUDIT_LOG", os.path.join(_tmp, "dziennik-zmian.jsonl"))

os.environ.setdefault("SMART_CONFIG", os.path.join(_tmp, "smart.json"))
