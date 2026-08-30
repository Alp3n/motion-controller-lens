"""Wspólne ustawienia testów.

Konfiguracja osi i profili musi wskazywać na pliki tymczasowe, zanim
zaimportuje się aplikacja — inaczej testy czytałyby (i nadpisywały)
konfigurację maszyny.
"""

import os
import tempfile

_tmp = tempfile.mkdtemp(prefix="cfg-test-")

os.environ.setdefault("AXES_CONFIG", os.path.join(_tmp, "axes.json"))
os.environ.setdefault("PROFILES_CONFIG", os.path.join(_tmp, "profiles.json"))
os.environ.setdefault("CYCLE_CONFIG", os.path.join(_tmp, "cycle.json"))
os.environ.setdefault("SMART_CONFIG", os.path.join(_tmp, "smart.json"))
