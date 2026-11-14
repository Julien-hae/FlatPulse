"""Freeze one HTML page as a test fixture: lighter, dated, its contacts flagged.

    python .claude/skills/nouveau-scraper/scripts/trim_fixture.py SOURCE OUTPUT

SOURCE is the URL of the page (requested once, as a scraper would) or a file saved
earlier, then given with `--url`. What a scraper never reads is removed: scripts,
styles, SVG and `srcset`. The scripts holding data (`application/json`,
`application/ld+json`, `__NEXT_DATA__`) are kept, since a scraper may read them.

E-mail addresses become `gerance@example.com`. Names and phone numbers are only
listed: replacing them takes a human eye, a pattern would also hit prices and ids.
The listing itself is left untouched: a fixture is a real case, not a rewritten one.
"""

import argparse
import datetime
import re
from pathlib import Path

import httpx
from parsel import Selector

# docs/architecture.md §8: a fixture holds named cases and stays under 100 Ko.
MAX_FIXTURE_BYTES = 100_000
ANONYMOUS_EMAIL = "gerance@example.com"
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
_PHONE = re.compile(r"(?:\+41|0041|\b0)[\s./]?\d{2}(?:[\s./]?\d{2,3}){3}\b")
_DROPPED = (
    "script:not([type='application/json']):not([type='application/ld+json'])"
    ":not(#__NEXT_DATA__), style, svg"
)


def main() -> None:
    """Trim SOURCE into OUTPUT and say what is left to do by hand."""
    args = _arguments()
    if args.output.exists() and not args.force:
        raise SystemExit(
            f"{args.output} existe : une fixture est figée, --force pour la refaire"
        )
    if args.source.startswith(("http://", "https://")):
        url = args.source
        response = httpx.get(url, timeout=30, follow_redirects=True)
        response.raise_for_status()
        html = response.text
    elif args.url:
        url = args.url
        html = Path(args.source).read_text(encoding="utf-8")
    else:
        raise SystemExit("--url est requis pour un fichier : l'en-tête cite la page")
    trimmed = trim(html, url, args.date)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(trimmed, encoding="utf-8")
    _report(args.output, len(html.encode()), trimmed)


def _arguments() -> argparse.Namespace:
    """The command line: the page, where to freeze it, when it was read."""
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("source", help="URL de la page, ou fichier déjà enregistré")
    parser.add_argument("output", type=Path, help="tests/fixtures/<slug>/<id>.html")
    parser.add_argument("--url", help="URL de la page, quand SOURCE est un fichier")
    parser.add_argument(
        "--date",
        default=f"{datetime.datetime.now(tz=datetime.UTC):%d.%m.%Y}",
        help="date du relevé, JJ.MM.AAAA (défaut : aujourd'hui)",
    )
    parser.add_argument("--force", action="store_true", help="écraser OUTPUT")
    return parser.parse_args()


def trim(html: str, url: str, date: str) -> str:
    """`html` without what no scraper reads, headed by where and when it was read."""
    page = Selector(text=html)
    for node in page.css(_DROPPED):
        node.drop()
    for node in page.xpath("//*[@srcset]"):
        del node.root.attrib["srcset"]
    body = _EMAIL.sub(ANONYMOUS_EMAIL, page.get())
    header = (
        f"<!-- page relevée sur {url} le {date}, contact anonymisé "
        "(scripts, styles, SVG et srcset retirés) -->"
    )
    # Inside <head> when there is one, as in the fixtures already frozen.
    headed = body.replace("<head>", f"<head>\n{header}", 1)
    return f"<!doctype html>\n{headed if headed != body else header + body}\n"


def _report(output: Path, original_bytes: int, trimmed: str) -> None:
    """Print the weight won and what still names a person."""
    size = len(trimmed.encode())
    print(f"{output} : {original_bytes / 1000:.0f} Ko → {size / 1000:.0f} Ko")
    if size > MAX_FIXTURE_BYTES:
        print(
            "✘ plus de 100 Ko : retirer à la main ce que le scraper ne lit pas "
            "(menus, pied de page, annonces similaires) — jamais l'annonce"
        )
    phones = sorted(set(_PHONE.findall(trimmed)))
    if phones:
        print(f"À anonymiser à la main, téléphones : {', '.join(phones)}")
    print(
        "À relire : le nom du gérant ou du contact (→ « Contact anonymisé »), "
        "puis vérifier que l'en-tête dit vrai."
    )


if __name__ == "__main__":
    main()
