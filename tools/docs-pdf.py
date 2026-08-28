#!/usr/bin/env python3
"""Składa PDF-y z dokumentacji Markdown (docs/**.md).

Bez zewnętrznych bibliotek: własny, wąski konwerter Markdown -> HTML pokrywający
to, czego używa dokumentacja tego repozytorium (nagłówki, listy, tabele, bloki
kodu, cytaty, odnośniki, pogrubienia), a potem LibreOffice w trybie wsadowym
robi z HTML-a PDF.

Użycie:
    tools/docs-pdf.py                # docs/ -> docs/pdf/
    tools/docs-pdf.py --keep-html    # zostawia pliki pośrednie HTML
"""

from __future__ import annotations

import argparse
import html
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"
OUT = DOCS / "pdf"

CSS = """
@page { size: A4; margin: 18mm 16mm; }
body { font-family: "Liberation Sans", Arial, sans-serif; font-size: 10.5pt;
       line-height: 1.45; color: #14181d; }
h1 { font-size: 20pt; margin: 0 0 4mm; border-bottom: 2px solid #3aa0ff;
     padding-bottom: 2mm; }
h2 { font-size: 14pt; margin: 7mm 0 2mm; color: #17456e; }
h3 { font-size: 12pt; margin: 5mm 0 2mm; color: #17456e; }
h4 { font-size: 11pt; margin: 4mm 0 2mm; }
p, li { margin: 0 0 2.2mm; }
ul, ol { margin: 0 0 3mm; padding-left: 7mm; }
code { font-family: "Liberation Mono", monospace; font-size: 9.5pt;
       background: #eef1f5; }
pre { font-family: "Liberation Mono", monospace; font-size: 9pt;
      background: #eef1f5; border-left: 3px solid #b6c2d0;
      padding: 2.5mm 3mm; margin: 0 0 3mm; white-space: pre-wrap; }
blockquote { margin: 0 0 3mm; padding: 0 0 0 4mm; border-left: 3px solid #b6c2d0;
             color: #45525f; }
table { border-collapse: collapse; margin: 0 0 4mm; width: 100%; }
th, td { border: 1px solid #b6c2d0; padding: 1.5mm 2mm; text-align: left;
         vertical-align: top; font-size: 9.5pt; }
th { background: #e6ecf3; }
a { color: #17456e; }
hr { border: 0; border-top: 1px solid #b6c2d0; margin: 4mm 0; }
.meta { color: #6b7783; font-size: 8.5pt; margin: 0 0 6mm; }
"""

INLINE_CODE = re.compile(r"`([^`]+)`")
BOLD = re.compile(r"\*\*(.+?)\*\*")
ITALIC = re.compile(r"(?<![\*\w])\*([^*\n]+)\*(?!\*)")
STRIKE = re.compile(r"~~(.+?)~~")
LINK = re.compile(r"\[([^\]]*)\]\(([^)]+)\)")


def inline(text: str) -> str:
    """Formatowanie w linii. Kod chronimy przed resztą reguł podmianką."""
    guarded: list[str] = []

    def keep_code(m: re.Match) -> str:
        guarded.append(html.escape(m.group(1)))
        return f"\x00{len(guarded) - 1}\x00"

    text = INLINE_CODE.sub(keep_code, text)
    text = html.escape(text)
    text = LINK.sub(lambda m: f'<a href="{m.group(2)}">{m.group(1)}</a>', text)
    text = BOLD.sub(r"<b>\1</b>", text)
    text = ITALIC.sub(r"<i>\1</i>", text)
    text = STRIKE.sub(r"<s>\1</s>", text)
    return re.sub(r"\x00(\d+)\x00", lambda m: f"<code>{guarded[int(m.group(1))]}</code>", text)


def split_row(line: str) -> list[str]:
    cells = line.strip().strip("|").split("|")
    return [c.strip() for c in cells]


def is_separator(line: str) -> bool:
    """Linia oddzielająca nagłówek tabeli: |---|:--:|"""
    return bool(re.fullmatch(r"\s*\|?[\s:|-]+\|[\s:|-]*", line)) and "-" in line


def convert(md: str) -> str:
    lines = md.split("\n")
    out: list[str] = []
    # stos otwartych list: [(wcięcie, znacznik)]
    stack: list[tuple[int, str]] = []
    para: list[str] = []
    # Treść bieżącego punktu listy zbieramy w postaci surowej i składamy
    # dopiero na końcu punktu: inaczej pogrubienie przełamane między liniami
    # (**czyta\n z serwa**) zostawało w tekście jako gwiazdki.
    item: list[str] = []
    blank = False
    i = 0

    def flush_item() -> None:
        if item:
            out.append("<li>" + inline(" ".join(item)) + "</li>")
            item.clear()

    def close_lists(to_indent: int = -1) -> None:
        flush_item()
        while stack and stack[-1][0] > to_indent:
            out.append(f"</{stack.pop()[1]}>")

    def flush_para() -> None:
        if para:
            out.append("<p>" + inline(" ".join(para)) + "</p>")
            para.clear()

    while i < len(lines):
        raw = lines[i]
        line = raw.rstrip()
        stripped = line.strip()

        # blok kodu
        if stripped.startswith("```"):
            flush_para()
            close_lists()
            i += 1
            code = []
            while i < len(lines) and not lines[i].strip().startswith("```"):
                code.append(lines[i])
                i += 1
            i += 1
            out.append("<pre>" + html.escape("\n".join(code)) + "</pre>")
            continue

        # pusta linia kończy akapit i punkt listy, ale nie samą listę
        # (listy bywają rozstrzelone pustymi liniami)
        if not stripped:
            flush_para()
            flush_item()
            blank = True
            i += 1
            continue

        # nagłówek
        m = re.match(r"(#{1,6})\s+(.*)", stripped)
        if m:
            flush_para()
            close_lists()
            level = len(m.group(1))
            out.append(f"<h{level}>{inline(m.group(2))}</h{level}>")
            i += 1
            continue

        # linia pozioma
        if re.fullmatch(r"(-{3,}|\*{3,}|_{3,})", stripped):
            flush_para()
            close_lists()
            out.append("<hr>")
            i += 1
            continue

        # tabela: wiersz z '|' i linia oddzielająca pod nim
        if "|" in stripped and i + 1 < len(lines) and is_separator(lines[i + 1]):
            flush_para()
            close_lists()
            header = split_row(stripped)
            i += 2
            rows = []
            while i < len(lines) and "|" in lines[i] and lines[i].strip():
                rows.append(split_row(lines[i]))
                i += 1
            out.append("<table><tr>" + "".join(f"<th>{inline(c)}</th>" for c in header) + "</tr>")
            for row in rows:
                out.append("<tr>" + "".join(f"<td>{inline(c)}</td>" for c in row) + "</tr>")
            out.append("</table>")
            continue

        # cytat
        if stripped.startswith(">"):
            flush_para()
            close_lists()
            quote = []
            while i < len(lines) and lines[i].strip().startswith(">"):
                quote.append(lines[i].strip().lstrip(">").strip())
                i += 1
            out.append("<blockquote>" + inline(" ".join(quote)) + "</blockquote>")
            continue

        # element listy
        m = re.match(r"(\s*)([-*+]|\d+[.)])\s+(.*)", line)
        if m:
            flush_para()
            indent = len(m.group(1))
            tag = "ul" if m.group(2) in "-*+" else "ol"
            content = m.group(3)
            # pole wyboru z listy zadań
            content = re.sub(r"^\[[ xX]\]\s*", lambda t: "☑ " if "x" in t.group(0).lower() else "☐ ", content)

            flush_item()
            while stack and stack[-1][0] > indent:
                out.append(f"</{stack.pop()[1]}>")
            if not stack or stack[-1][0] < indent:
                out.append(f"<{tag}>")
                stack.append((indent, tag))
            item.append(content)
            blank = False
            i += 1
            continue

        # zwykły tekst — kontynuacja punktu listy albo nowy akapit
        if stack and not blank:
            item.append(stripped)
            i += 1
            continue
        if stack:
            close_lists()
        blank = False
        para.append(stripped)
        i += 1

    flush_para()
    close_lists()
    return "\n".join(out)


def build_html(md_path: Path) -> str:
    title = md_path.stem
    rel = md_path.relative_to(ROOT)
    body = convert(md_path.read_text(encoding="utf-8"))
    return (
        "<!DOCTYPE html>\n<html lang=\"pl\"><head><meta charset=\"utf-8\">"
        f"<title>{html.escape(title)}</title><style>{CSS}</style></head><body>\n"
        f"{body}\n<p class=\"meta\">Źródło: {html.escape(str(rel))} — "
        "maszyna do odcinania wlewków płytek optyki</p>\n</body></html>\n"
    )


def main() -> int:
    ap = argparse.ArgumentParser(description="PDF-y z dokumentacji Markdown")
    ap.add_argument("--keep-html", action="store_true", help="zostaw pliki HTML")
    ap.add_argument("--out", default=str(OUT), help="katalog wynikowy")
    args = ap.parse_args()

    soffice = shutil.which("soffice") or shutil.which("libreoffice")
    if not soffice:
        print("BŁĄD: brak LibreOffice (soffice) — nie ma czym złożyć PDF-a", file=sys.stderr)
        return 1

    out_dir = Path(args.out).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    sources = sorted(p for p in DOCS.rglob("*.md") if out_dir not in p.parents)
    if not sources:
        print("brak plików .md w docs/", file=sys.stderr)
        return 1

    work = Path(tempfile.mkdtemp(prefix="docs-pdf-"))
    made = []
    for md in sources:
        # docs/zmiany/x.md -> zmiany-x.pdf (płaski katalog wyjściowy)
        name = "-".join(md.relative_to(DOCS).with_suffix("").parts)
        html_path = work / f"{name}.html"
        html_path.write_text(build_html(md), encoding="utf-8")

        res = subprocess.run(
            [soffice, "--headless", "--convert-to", "pdf:writer_web_pdf_Export",
             "--outdir", str(out_dir), str(html_path)],
            capture_output=True, text=True,
        )
        pdf = out_dir / f"{name}.pdf"
        if res.returncode != 0 or not pdf.exists():
            print(f"BŁĄD przy {md}: {res.stdout.strip()} {res.stderr.strip()}", file=sys.stderr)
            return 1
        made.append(pdf)
        print(f"  {md.relative_to(ROOT)}  ->  {pdf.relative_to(ROOT)}")

    if args.keep_html:
        for f in work.glob("*.html"):
            shutil.copy(f, out_dir)
    shutil.rmtree(work, ignore_errors=True)
    print(f"\nGotowe: {len(made)} plików PDF w {out_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
