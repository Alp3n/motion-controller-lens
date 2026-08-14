# Program ocinania wlewkow — plytka soczewki 70 mm, obustronna
[NAGLOWEK]
FORMAT;1
PROGRAM;583912004844
NAZWA;Plytka soczewki 70mm - obustronna
MATERIAL;PC
AUTOR;J.Kowalski
DATA;2026-08-14
OBROTY_FREZU;10000
POSUW_ROBOCZY;250
POSUW_DOJAZDU;3000
Z_BEZPIECZNE;12.0

[OPERACJE]
LP;OPERACJA;X;Y;Z;X2;Y2;UWAGI
1;PUNKT;-20.000;42.000;-2.00;;;wlewek naroznik A
2;PUNKT;20.000;42.000;-2.00;;;wlewek naroznik B
3;LINIA;-35.000;0.000;-2.00;-35.000;15.000;wlewek lewy
4;LINIA;35.000;0.000;-2.00;35.000;15.000;wlewek prawy
5;PAUZA;;;;;;obrot plytki na strone B
6;PUNKT;0.000;-42.000;-2.00;;;wlewek dolny strona B
