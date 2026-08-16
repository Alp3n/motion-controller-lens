"""Wspólne ustawienia testów.

Konfiguracja osi musi wskazywać na plik tymczasowy, zanim zaimportuje się
aplikacja — inaczej testy czytałyby (i nadpisywały) konfigurację maszyny.
"""

import os
import tempfile

os.environ.setdefault(
    "AXES_CONFIG", os.path.join(tempfile.mkdtemp(prefix="axes-test-"), "axes.json")
)
