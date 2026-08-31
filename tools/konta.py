#!/usr/bin/env python3
"""Konta użytkowników panelu maszyny — zakładanie, hasła, role.

Konta są celowo poza panelem WWW: gdyby dało się je zakładać z przeglądarki,
przejęta sesja admina wystarczyłaby do założenia sobie kolejnego konta. Tu
trzeba mieć dostęp do komputera maszyny.

    tools/konta.py lista
    tools/konta.py dodaj <login> --rola admin --imie "Jan Kowalski"
    tools/konta.py haslo <login>
    tools/konta.py rola <login> <operator|technolog|admin>
    tools/konta.py usun <login>

Plik kont: config/users.json (albo ścieżka z USERS_CONFIG). Zawiera wyłącznie
skróty haseł — zapomnianego hasła nie da się odzyskać, ustawia się nowe.

UWAGA: dopóki plik kont nie istnieje, serwer działa **bez logowania** i wszystkie
ekrany są dostępne bez hasła. Pierwsze `dodaj` włącza logowanie — po nim trzeba
się zalogować, żeby wejść na jakikolwiek ekran. Zrób to świadomie, przy maszynie.
"""

from __future__ import annotations

import argparse
import getpass
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "server"))

from app import users  # noqa: E402


def _path(args) -> Path:
    if args.plik:
        return Path(args.plik).resolve()
    return Path(os.environ.get("USERS_CONFIG", ROOT / "config" / "users.json")).resolve()


def _load(path: Path) -> dict[str, users.User]:
    try:
        return users.load(path)
    except users.UserError as exc:
        sys.exit(f"BŁĄD: {exc}")


def _ask_password(login: str) -> str:
    """Hasło pytane dwa razy, nigdy z argumentu wiersza poleceń.

    Hasło w argumencie trafia do historii powłoki i do listy procesów — każdy
    zalogowany na tę maszynę mógłby je zobaczyć.
    """
    while True:
        first = getpass.getpass(f"Hasło dla {login}: ")
        if len(first) < users.MIN_PASSWORD_LEN:
            print(f"  hasło musi mieć co najmniej {users.MIN_PASSWORD_LEN} znaków")
            continue
        if first != getpass.getpass("Powtórz hasło: "):
            print("  hasła się różnią")
            continue
        return first


def cmd_lista(args) -> None:
    path = _path(args)
    accounts = _load(path)
    if not accounts:
        print(f"Brak pliku kont ({path}) — LOGOWANIE JEST WYŁĄCZONE.")
        print("Wszystkie ekrany panelu są dostępne bez hasła.")
        return
    print(f"Plik: {path}")
    width = max(len(login) for login in accounts)
    for user in sorted(accounts.values(), key=lambda u: (u.role, u.login)):
        print(f"  {user.login:<{width}}  {user.role:<9}  {user.name}")


def cmd_dodaj(args) -> None:
    path = _path(args)
    accounts = _load(path)
    login = args.login.strip().lower()
    if login in accounts:
        sys.exit(f"BŁĄD: konto {login} już istnieje — hasło zmienia `konta.py haslo`")
    first_account = not accounts
    password = _ask_password(login)
    try:
        user = users.User.from_dict(
            {
                "login": login,
                "name": args.imie or login,
                "role": args.rola,
                "password_hash": users.hash_password(password),
            }
        )
    except users.UserError as exc:
        sys.exit(f"BŁĄD: {exc}")
    accounts[login] = user
    try:
        users.parse_users([u.to_dict() for u in accounts.values()])
    except users.UserError as exc:
        sys.exit(f"BŁĄD: {exc}")
    users.save(path, accounts)
    print(f"Dodano konto {login} ({user.role}).")
    if first_account:
        print()
        print("To było pierwsze konto — OD TERAZ PANEL WYMAGA LOGOWANIA.")
        print("Zrestartuj serwer maszyny, żeby wczytał plik kont.")


def cmd_haslo(args) -> None:
    path = _path(args)
    accounts = _load(path)
    login = args.login.strip().lower()
    if login not in accounts:
        sys.exit(f"BŁĄD: nie ma konta {login}")
    accounts[login].password_hash = users.hash_password(_ask_password(login))
    users.save(path, accounts)
    print(f"Zmieniono hasło konta {login}.")
    print("Zrestartuj serwer maszyny — bez tego działa dalej stare hasło,")
    print("a otwarte sesje tego konta zostają zalogowane.")


def cmd_rola(args) -> None:
    path = _path(args)
    accounts = _load(path)
    login = args.login.strip().lower()
    if login not in accounts:
        sys.exit(f"BŁĄD: nie ma konta {login}")
    if args.nowa not in users.ROLES:
        sys.exit("BŁĄD: rola musi być jedną z: " + ", ".join(users.ROLES))
    poprzednia = accounts[login].role
    accounts[login].role = args.nowa
    try:
        users.parse_users([u.to_dict() for u in accounts.values()])
    except users.UserError as exc:
        sys.exit(f"BŁĄD: {exc}")
    users.save(path, accounts)
    print(f"Konto {login}: rola {poprzednia} -> {args.nowa}.")
    print("Zrestartuj serwer maszyny, żeby zmiana zadziałała.")


def cmd_usun(args) -> None:
    path = _path(args)
    accounts = _load(path)
    login = args.login.strip().lower()
    if login not in accounts:
        sys.exit(f"BŁĄD: nie ma konta {login}")
    removed = accounts.pop(login)
    if accounts:
        try:
            users.parse_users([u.to_dict() for u in accounts.values()])
        except users.UserError as exc:
            sys.exit(f"BŁĄD: {exc}")
        users.save(path, accounts)
        print(f"Usunięto konto {login} ({removed.role}).")
    else:
        # pusty plik kont = logowanie wyłączone; lepiej powiedzieć to wprost
        sys.exit(
            f"BŁĄD: {login} to ostatnie konto. Usunięcie go wyłączyłoby logowanie "
            f"dla całego panelu. Jeśli o to chodzi, skasuj plik {path} ręcznie."
        )
    print("Zrestartuj serwer maszyny, żeby zamknąć otwarte sesje tego konta.")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Konta użytkowników panelu maszyny",
        epilog="Plik kont zawiera tylko skróty haseł — zapomnianego nie da się odzyskać.",
    )
    parser.add_argument("--plik", help="ścieżka do pliku kont (domyślnie config/users.json)")
    sub = parser.add_subparsers(dest="komenda", required=True)

    p = sub.add_parser("lista", help="wypisz konta")
    p.set_defaults(func=cmd_lista)

    p = sub.add_parser("dodaj", help="załóż konto")
    p.add_argument("login")
    p.add_argument("--rola", default=users.ROLE_OPERATOR, choices=list(users.ROLES))
    p.add_argument("--imie", default="", help="imię i nazwisko do pokazania w panelu")
    p.set_defaults(func=cmd_dodaj)

    p = sub.add_parser("haslo", help="ustaw nowe hasło")
    p.add_argument("login")
    p.set_defaults(func=cmd_haslo)

    p = sub.add_parser("rola", help="zmień rolę konta")
    p.add_argument("login")
    p.add_argument("nowa", choices=list(users.ROLES))
    p.set_defaults(func=cmd_rola)

    p = sub.add_parser("usun", help="usuń konto")
    p.add_argument("login")
    p.set_defaults(func=cmd_usun)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
