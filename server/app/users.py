"""Konta użytkowników, role i sesje panelu.

Decyzja (potwierdzona przez Ciebie): **osobne konta**, nie wspólne PIN-y na rolę.
Notatki proponowały PIN-y `123321`/`456`/`789` — wspólny kod nie pozwala ustalić,
kto zmienił parametry siły i prędkości, a te akurat wpływają na bezpieczeństwo.
Osobne konto daje przypisanie zmiany do osoby (patrz `app/audit.py`).

Trzy role, zgodnie z `zbyszek/NOTATKI_FUNKCJONALNE.md` §9:

    operator  — panel operatora (start/stop, JOG, bazowanie)
    technolog — powyższe + edytor programów technologa
    admin     — powyższe + konfiguracja maszyny i ekran diagnostyczny

Role są **narastające**: technolog może wszystko, co operator, admin — wszystko.

## Czego ta warstwa NIE daje — bez zmiękczania

- **To nie jest funkcja bezpieczeństwa maszyny.** Zatrzymanie awaryjne realizuje
  niezależny obwód sprzętowy (E-stop, Global Stop). Logowanie ogranicza dostęp do
  ekranów, nic więcej.
- **Panel chodzi po zwykłym HTTP.** Hasło i ciasteczko sesji idą przez sieć
  otwartym tekstem — kto ma dostęp do tej samej sieci, może je podejrzeć.
  Sensowne dopiero za odseparowaną siecią maszynową albo po postawieniu HTTPS.
- **Sesje żyją w pamięci procesu.** Restart serwera wylogowuje wszystkich. To
  świadomy wybór: nie ma sekretu do przechowywania i do wycieku.
- **API dla MES zostaje bez logowania** — wywołuje je system, nie człowiek.
  To dziura, która istniała wcześniej i nie zmienia się w tej zmianie; opisana
  w `docs/zmiany/role-i-logowanie.md` jako zadanie otwarte.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import re
import secrets
import time
from dataclasses import dataclass
from pathlib import Path

ROLE_OPERATOR = "operator"
ROLE_TECHNOLOG = "technolog"
ROLE_ADMIN = "admin"

# kolejność ma znaczenie: rola daje uprawnienia swoje i wszystkich wcześniejszych
ROLES = (ROLE_OPERATOR, ROLE_TECHNOLOG, ROLE_ADMIN)

LOGIN_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{1,31}$")

# PBKDF2-HMAC-SHA256; liczba iteracji wg zaleceń OWASP (2023) dla tej funkcji.
# Zapisujemy ją w haśle, więc podniesienie jej później nie unieważnia kont —
# stare hasła dalej się weryfikują swoją liczbą iteracji.
HASH_ITERATIONS = 600_000
_HASH_PREFIX = "pbkdf2_sha256"

MIN_PASSWORD_LEN = 8

# Blokada po nieudanych próbach — na panelu dotykowym nikt nie wpisuje hasła
# dziesięć razy pod rząd, a to podnosi koszt zgadywania.
MAX_FAILED = 5
LOCKOUT_SECONDS = 300


class UserError(Exception):
    """Błąd kont użytkowników — komunikat po polsku."""


def role_allows(role: str, required: str) -> bool:
    """Czy `role` wystarcza tam, gdzie wymagane jest `required`."""
    if role not in ROLES or required not in ROLES:
        return False
    return ROLES.index(role) >= ROLES.index(required)


# --- hasła -----------------------------------------------------------------


def hash_password(password: str, *, iterations: int = HASH_ITERATIONS) -> str:
    if len(password) < MIN_PASSWORD_LEN:
        raise UserError(f"hasło musi mieć co najmniej {MIN_PASSWORD_LEN} znaków")
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return "$".join(
        [
            _HASH_PREFIX,
            str(iterations),
            base64.b64encode(salt).decode(),
            base64.b64encode(digest).decode(),
        ]
    )


def verify_password(password: str, stored: str) -> bool:
    """Porównanie odporne na pomiar czasu; zły format hasła = odmowa, nie wyjątek."""
    try:
        prefix, iterations, salt_b64, digest_b64 = stored.split("$")
        if prefix != _HASH_PREFIX:
            return False
        salt = base64.b64decode(salt_b64)
        expected = base64.b64decode(digest_b64)
    except (ValueError, TypeError):
        return False
    actual = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, int(iterations)
    )
    return hmac.compare_digest(actual, expected)


# --- konta -----------------------------------------------------------------


@dataclass
class User:
    login: str
    name: str
    role: str
    password_hash: str

    def to_dict(self) -> dict:
        return {
            "login": self.login,
            "name": self.name,
            "role": self.role,
            "password_hash": self.password_hash,
        }

    def public(self) -> dict:
        """Bez skrótu hasła — to trafia do przeglądarki."""
        return {"login": self.login, "name": self.name, "role": self.role}

    @classmethod
    def from_dict(cls, data: dict) -> User:
        if not isinstance(data, dict):
            raise UserError("oczekiwano obiektu z kontem użytkownika")
        missing = [k for k in ("login", "role", "password_hash") if k not in data]
        if missing:
            raise UserError("konto: brak pól: " + ", ".join(missing))
        login = str(data["login"]).strip().lower()
        if not LOGIN_RE.match(login):
            raise UserError(
                f"nieprawidłowy login '{login}' — 2–32 znaki: małe litery, cyfry, "
                "kropka, myślnik, podkreślenie"
            )
        role = str(data["role"]).strip().lower()
        if role not in ROLES:
            raise UserError(
                f"konto {login}: nieznana rola '{role}' — dozwolone: " + ", ".join(ROLES)
            )
        password_hash = str(data["password_hash"])
        if not password_hash.startswith(_HASH_PREFIX + "$"):
            raise UserError(
                f"konto {login}: hasło musi być skrótem PBKDF2 — nie zapisuj hasła "
                "jawnie w pliku, użyj tools/konta.py"
            )
        return cls(
            login=login,
            name=str(data.get("name", "")).strip() or login,
            role=role,
            password_hash=password_hash,
        )


def parse_users(data) -> dict[str, User]:
    if isinstance(data, dict):
        data = data.get("users", [])
    if not isinstance(data, list):
        raise UserError("oczekiwano listy kont w polu 'users'")
    users: dict[str, User] = {}
    for entry in data:
        user = User.from_dict(entry)
        if user.login in users:
            raise UserError(f"konto {user.login} występuje dwa razy")
        users[user.login] = user
    if users and not any(u.role == ROLE_ADMIN for u in users.values()):
        raise UserError(
            "plik kont nie zawiera żadnego administratora — bez niego nie da się "
            "wejść do konfiguracji maszyny"
        )
    return users


def load(path: Path) -> dict[str, User]:
    """Wczytuje konta; brak pliku = pusty słownik (logowanie wyłączone).

    Błędny plik zatrzymuje serwer zamiast po cichu wyłączać logowanie — inaczej
    literówka w JSON-ie otwierałaby konfigurację maszyny dla każdego.
    """
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise UserError(f"nie można odczytać pliku kont {path}: {exc}")
    return parse_users(raw)


def save(path: Path, users: dict[str, User]) -> None:
    """Zapis atomowy, z prawami tylko dla właściciela — plik zawiera skróty haseł."""
    payload = {"users": [u.to_dict() for u in users.values()]}
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    tmp.chmod(0o600)
    tmp.replace(path)


# --- sesje -----------------------------------------------------------------


COOKIE_NAME = "sesja"


class Sessions:
    """Sesje w pamięci procesu: token -> login, z czasem ważności.

    Restart serwera kasuje wszystkie sesje — patrz docstring modułu.
    """

    def __init__(self, ttl_seconds: float) -> None:
        self.ttl = ttl_seconds
        self._tokens: dict[str, tuple[str, float]] = {}
        # login -> (liczba nieudanych prób, moment ostatniej)
        self._failed: dict[str, tuple[int, float]] = {}

    # --- logowanie ---

    def locked_for(self, login: str, now: float | None = None) -> float:
        """Ile sekund konto jest jeszcze zablokowane (0 = nie jest)."""
        now = time.monotonic() if now is None else now
        count, last = self._failed.get(login, (0, 0.0))
        if count < MAX_FAILED:
            return 0.0
        remaining = LOCKOUT_SECONDS - (now - last)
        return max(0.0, remaining)

    def note_failure(self, login: str, now: float | None = None) -> None:
        now = time.monotonic() if now is None else now
        count, last = self._failed.get(login, (0, 0.0))
        # blokada wygasła — licznik startuje od nowa
        if count >= MAX_FAILED and now - last >= LOCKOUT_SECONDS:
            count = 0
        self._failed[login] = (count + 1, now)

    def note_success(self, login: str) -> None:
        self._failed.pop(login, None)

    # --- tokeny ---

    def create(self, login: str, now: float | None = None) -> str:
        now = time.monotonic() if now is None else now
        token = secrets.token_urlsafe(32)
        self._tokens[token] = (login, now + self.ttl)
        return token

    def login_for(self, token: str | None, now: float | None = None) -> str | None:
        """Login przypisany do tokenu; odświeża ważność (sesja przesuwna).

        Panel przy maszynie stoi otwarty całą zmianę — sesja liczona od
        ostatniego użycia, nie od zalogowania, oszczędza operatorowi
        wylogowania w środku pracy.
        """
        if not token:
            return None
        now = time.monotonic() if now is None else now
        entry = self._tokens.get(token)
        if entry is None:
            return None
        login, expires = entry
        if now >= expires:
            del self._tokens[token]
            return None
        self._tokens[token] = (login, now + self.ttl)
        return login

    def drop(self, token: str | None) -> None:
        if token:
            self._tokens.pop(token, None)

    def drop_user(self, login: str) -> None:
        """Wylogowuje wszystkie sesje konta — po zmianie hasła albo roli."""
        for token in [t for t, (l, _) in self._tokens.items() if l == login]:
            del self._tokens[token]

    def active_count(self) -> int:
        now = time.monotonic()
        return sum(1 for _, expires in self._tokens.values() if now < expires)
