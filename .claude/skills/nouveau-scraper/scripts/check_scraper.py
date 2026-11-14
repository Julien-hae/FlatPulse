"""Check that an agency's scraper is wired everywhere a scraper has to be.

    python .claude/skills/nouveau-scraper/scripts/check_scraper.py SLUG

A new agency touches a class, a test, fixtures, the live audit and three documents:
one of them forgotten does not turn any test red. This looks at each, and at what
the tests cannot see (a request escaping the limiter, a fixture over 100 Ko, a rate
still « à mesurer »). ✘ blocks the story, ⚠ is to be said in the summary.

It checks the wiring, not the scraper: the suite, ruff and mypy still have to pass.
"""

import argparse
import importlib
import pkgutil
import re
import sys
from pathlib import Path

ROOT = next(
    parent
    for parent in Path(__file__).resolve().parents
    if (parent / "pyproject.toml").exists()
)
# `tests` is a package of the repository, not an installed one: a script run by its
# path only sees it once the root is on the path, hence the imports below it.
sys.path.insert(0, str(ROOT))

from tests.contract.test_scraper_contract import ScraperContractMixin  # noqa: E402
from tests.integration import test_live_sources  # noqa: E402

import flatpulse.scrapers.sources  # noqa: E402
from flatpulse.scrapers.base import (  # noqa: E402
    CatalogueScraper,
    FicheScraper,
    HttpScraper,
)

FIXTURES = ROOT / "tests" / "fixtures"
# docs/architecture.md §8: a fixture holds named cases and stays under 100 Ko.
MAX_FIXTURE_BYTES = 100_000
# What the base classes own: a source redefining one of them leaves the contract.
OWNED_BY_BASE = ("fetch_listings", "run", "_get", "_build_or_skip")
FORBIDDEN_IN_SOURCE = {
    r"\bprint\(": "print() laissé",
    r"\b(?:TODO|FIXME)\b": "TODO ou FIXME laissé",
    r"\b(?:bs4|BeautifulSoup)\b": "beautifulsoup4 : parsel uniquement",
    r"\bclient\.(?:get|post|request)\(|\bhttpx\.(?:get|post)\(": (
        "requête hors de self._get() : elle échappe au RateLimiter"
    ),
    r"\b(?:asyncio|time)\.sleep\(": "pause écrite à la main : le débit est au limiteur",
}
FORBIDDEN_IN_TEST = {r"\bpytest\b": "pytest : unittest uniquement"}
# A template the site left unfilled, as in « /location/%property_canton%/… ».
_UNFILLED = re.compile(r"%[a-z]{3,}(?:_[a-z]+)*%")
# What a spike leaves open, and a scraper in service must have settled.
_OPEN = re.compile(r"à (?:mesurer|confirmer)")


class Report:
    """The lines of the check, and whether one of them blocks."""

    def __init__(self) -> None:
        """Start with nothing blocking."""
        self.blocked = False

    def check(self, ok: bool, what: str, otherwise: str = "") -> bool:
        """Print `what` as done, or as blocking with what to do; return `ok`."""
        if ok:
            print(f"✔ {what}")
        else:
            self.blocked = True
            print(f"✘ {what}" + (f" — {otherwise}" if otherwise else ""))
        return ok

    def warn(self, ok: bool, what: str, otherwise: str) -> None:
        """Print `what` as done, or as something to say in the summary."""
        print(f"✔ {what}" if ok else f"⚠ {what} — {otherwise}")


def main() -> None:
    """Check the agency of the slug given; exit 1 if something blocks."""
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("slug")
    slug: str = parser.parse_args().slug
    report = Report()
    scraper = _scraper_of(slug)
    if not report.check(
        scraper is not None,
        f"une classe de scrapers/sources/ porte slug = {slug!r}",
        "aucune : la classe manque, ou son slug diffère de celui du spike",
    ):
        raise SystemExit(1)
    assert scraper is not None  # noqa: S101 - narrowed for mypy, checked just above
    module = scraper.__module__.rsplit(".", 1)[-1]
    _check_class(report, scraper, module)
    fixture_name = _check_test(report, scraper, module)
    _check_fixtures(report, module, fixture_name)
    _check_registry(report, scraper, slug)
    _check_docs(report, slug, fixture_name)
    print(
        "\nReste à faire tourner : python -m unittest discover tests/ · "
        "ruff format . && ruff check . · mypy src/"
    )
    if report.blocked:
        raise SystemExit(1)


def _scraper_of(slug: str) -> type[HttpScraper] | None:
    """The scraper class of `scrapers/sources/` whose slug is `slug`."""
    package = flatpulse.scrapers.sources
    for info in pkgutil.iter_modules(package.__path__, f"{package.__name__}."):
        module = importlib.import_module(info.name)
        for value in vars(module).values():
            if (
                isinstance(value, type)
                and issubclass(value, HttpScraper)
                and value.__module__ == info.name
                and getattr(value, "slug", None) == slug
            ):
                return value
    return None


def _check_class(report: Report, scraper: type[HttpScraper], module: str) -> None:
    """The class takes one of the two shapes and leaves the base its part."""
    name = scraper.__name__
    report.check(
        issubclass(scraper, (CatalogueScraper, FicheScraper)),
        f"{name} est un CatalogueScraper ou un FicheScraper",
        "une source n'hérite pas de HttpScraper directement",
    )
    redefined = [method for method in OWNED_BY_BASE if method in vars(scraper)]
    report.check(
        not redefined,
        f"{name} ne redéfinit rien de ce que la base porte",
        f"redéfini : {', '.join(redefined)}",
    )
    report.check(
        str(getattr(scraper, "base_url", "")).startswith(("http://", "https://")),
        f"{name}.base_url est une URL http(s)",
    )
    source = ROOT / "src" / "flatpulse" / "scrapers" / "sources" / f"{module}.py"
    _check_text(report, source, FORBIDDEN_IN_SOURCE)


def _check_text(report: Report, path: Path, forbidden: dict[str, str]) -> None:
    """None of the `forbidden` patterns is in the file at `path`."""
    text = path.read_text(encoding="utf-8")
    found = [why for pattern, why in forbidden.items() if re.search(pattern, text)]
    report.check(
        not found, f"{path.relative_to(ROOT)} : rien d'interdit", " ; ".join(found)
    )


def _check_test(report: Report, scraper: type[HttpScraper], module: str) -> str | None:
    """The scraper has its test class on the contract; return its fixture name."""
    path = ROOT / "tests" / "unit" / f"test_{module}.py"
    if not report.check(path.exists(), f"{path.relative_to(ROOT)} existe"):
        return None
    _check_text(report, path, FORBIDDEN_IN_TEST)
    tests = importlib.import_module(f"tests.unit.test_{module}")
    case = next(
        (
            value
            for value in vars(tests).values()
            if isinstance(value, type)
            and issubclass(value, ScraperContractMixin)
            and getattr(value, "scraper_class", None) is scraper
        ),
        None,
    )
    if not report.check(
        case is not None,
        "une classe de test hérite de ScraperContractMixin pour ce scraper",
        "sans elle, les 5 contrats ne tournent pas",
    ):
        return None
    cases = [name for name in vars(case) if name.startswith(f"test_{module}_")]
    report.check(
        bool(cases),
        f"{len(cases)} cas nommés test_{module}_*",
        "les contrats seuls ne disent rien des valeurs extraites",
    )
    return getattr(case, "fixture_name", None)


def _check_fixtures(report: Report, module: str, fixture_name: str | None) -> None:
    """The fixtures exist, stay light and hold no broken URL."""
    if fixture_name is None:
        return
    fixture = FIXTURES / fixture_name
    if not report.check(fixture.exists(), f"tests/fixtures/{fixture_name} existe"):
        return
    folder = FIXTURES / module
    files = [fixture, *(sorted(folder.iterdir()) if folder.is_dir() else [])]
    heavy = [file.name for file in files if file.stat().st_size > MAX_FIXTURE_BYTES]
    report.check(
        not heavy,
        f"{len(files)} fixture(s), chacune sous 100 Ko",
        f"trop lourdes : {', '.join(heavy)}",
    )
    unfilled = sorted(
        {
            match
            for file in files
            for match in _UNFILLED.findall(file.read_text(encoding="utf-8"))
        }
    )
    report.check(
        not unfilled,
        "aucun gabarit non rempli dans les fixtures",
        f"{', '.join(unfilled)} : une annonce à l'URL cassée n'est pas un cas de test",
    )


def _check_registry(report: Report, scraper: type[HttpScraper], slug: str) -> None:
    """The source is known to the live audit and, once it exists, to the seed."""
    live = "tests/integration/test_live_sources.py"
    report.check(
        scraper in getattr(test_live_sources, "SCRAPER_CLASSES", ()),
        f"{scraper.__name__} est dans SCRAPER_CLASSES ({live})",
        "sans cela, l'audit en direct ne l'interroge jamais",
    )
    report.check(
        slug in getattr(test_live_sources, "RATE_LIMITS_RPM", {}),
        f"{slug} a son débit dans RATE_LIMITS_RPM",
        "y mettre le débit du spike",
    )
    report.warn(
        slug in getattr(test_live_sources, "MIN_FILL_RATE", {}),
        f"{slug} a ses seuils dans MIN_FILL_RATE",
        "ils se posent après le premier audit en direct (scripts/audit_source.py)",
    )
    seed = ROOT / "sql" / "sources.sql"
    if seed.exists():
        report.check(
            f"'{slug}'" in seed.read_text(encoding="utf-8"),
            f"{slug} est dans sql/sources.sql",
            "le pipeline ne connaît que les sources de ce seed",
        )


def _check_docs(report: Report, slug: str, fixture_name: str | None) -> None:
    """The spike entry is complete and the architecture table lists the source."""
    spike = (ROOT / "docs" / "spike-agencies.md").read_text(encoding="utf-8")
    entry = re.search(
        rf"^## [^\n]*\(`{re.escape(slug)}`\)\n(.*?)(?=^##? |\Z)", spike, re.M | re.S
    )
    if report.check(
        entry is not None,
        f"docs/spike-agencies.md a une entrée (`{slug}`)",
        "c'est la référence de la source",
    ):
        assert entry is not None  # noqa: S101 - narrowed for mypy, checked just above
        section = entry[1]
        for label, risk in (
            ("Débit", "un débit supposé, c'est un ban possible"),
            ("Pagination", "une pagination supposée perd ou double des annonces"),
        ):
            line = re.search(rf"^- {label} : (.*)$", section, re.M)
            report.check(
                line is not None and not _OPEN.search(line[1]),
                f"« {label} » de l'entrée est établi",
                f"absent, « à mesurer » ou « à confirmer » : {risk}",
            )
        report.check("### Pièges" in section, "l'entrée a sa section Pièges")
        if fixture_name:
            report.check(
                fixture_name in section,
                f"l'entrée cite sa fixture {fixture_name}",
                "ligne « Fixture : » à mettre à jour",
            )
    architecture = (ROOT / "docs" / "architecture.md").read_text(encoding="utf-8")
    report.check(
        f"| `{slug}` |" in architecture,
        f"docs/architecture.md §6 liste `{slug}`",
        "ligne du tableau des sources à ajouter ou à mettre à jour",
    )


if __name__ == "__main__":
    main()
