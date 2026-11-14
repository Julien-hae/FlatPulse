"""Polite first look at an agency's site: robots.txt, then the pages given.

    python .claude/skills/nouveau-scraper/scripts/recon.py URL [URL ...]

One request to robots.txt, then one per URL, `--delay` seconds apart (the site's
Crawl-delay when it is longer). A URL robots.txt disallows is never requested, and a
robots.txt answered 401 or 403 stops the run: the site does not want robots.

The report holds what an entry of docs/spike-agencies.md needs: the pace, the weight
of a poll, the validators of a conditional GET, where the listings live (JSON,
hydrated state, HTML cards) and whether two pages are really two pages.
"""

import argparse
import hashlib
import json
import math
import re
import time
from collections import Counter
from collections.abc import Iterator
from http import HTTPStatus
from urllib.parse import urljoin, urlsplit
from urllib.robotparser import RobotFileParser

import httpx
from parsel import Selector

# The longest Crawl-delay met in the park (Comptoir, CPEG): the pace before knowing.
DEFAULT_DELAY_S = 10.0
# The scrapers send httpx's default User-Agent: robots.txt is read as they would.
ROBOTS_AGENT = "python-httpx"
TIMEOUT_S = 30.0
MAX_DEPTH = 8
MAX_SHOWN = 8
_PAGE_LINK = re.compile(r"(?:[?&/]|^)(?:page|p|paged|offset|start)[=/-]\d+", re.I)
# The innermost classed blocks holding a link and a price: the cards of a catalogue.
_CARD = (
    "(self::article or self::li or self::div or self::a) and @class"
    " and (self::a/@href or .//a/@href) and contains(., 'CHF')"
)


def main() -> None:
    """Read robots.txt, then each URL, and print the report."""
    args = _arguments()
    origin = "{0.scheme}://{0.netloc}".format(urlsplit(args.urls[0]))
    started = time.monotonic()
    with httpx.Client(timeout=TIMEOUT_S, follow_redirects=True) as client:
        robots = _read_robots(client, origin)
        delay = max(args.delay, _crawl_delay(robots) or 0.0)
        pages: list[httpx.Response] = []
        for url in args.urls:
            if not robots.can_fetch(ROBOTS_AGENT, url):
                print(f"\n## {url}\n- robots.txt l'interdit : non demandée")
                continue
            time.sleep(delay)
            response = client.get(url)
            pages.append(response)
            _report_page(response)
            if args.conditional:
                time.sleep(delay)
                _report_conditional(client, response)
    _report_pagination(pages)
    requests = 1 + len(pages) * (2 if args.conditional else 1)
    print(f"\n{requests} requêtes en {time.monotonic() - started:.0f} s")


def _arguments() -> argparse.Namespace:
    """The command line: the URLs, the pace, the conditional GET probe."""
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("urls", nargs="+", metavar="URL")
    parser.add_argument(
        "--delay",
        type=float,
        default=DEFAULT_DELAY_S,
        help="secondes entre deux requêtes (défaut : %(default)s)",
    )
    parser.add_argument(
        "--conditional",
        action="store_true",
        help="redemander chaque page avec If-None-Match / If-Modified-Since",
    )
    return parser.parse_args()


def _read_robots(client: httpx.Client, origin: str) -> RobotFileParser:
    """The rules of `origin`, printed; a refused robots.txt ends the run."""
    response = client.get(urljoin(origin, "/robots.txt"))
    print(f"## robots.txt ({origin})\n- HTTP {response.status_code}")
    robots = RobotFileParser()
    if response.status_code in (HTTPStatus.UNAUTHORIZED, HTTPStatus.FORBIDDEN):
        raise SystemExit(
            "- robots.txt refusé : protection anti-robot. S'arrêter là, la régie "
            "est à écarter ou à trancher (cf. Grange dans docs/spike-agencies.md)."
        )
    if response.status_code != HTTPStatus.OK:
        print("- pas de robots.txt : aucune règle publiée")
        robots.parse([])
        return robots
    robots.parse(response.text.splitlines())
    crawl_delay = _crawl_delay(robots)
    if crawl_delay:
        rpm = math.floor(60 / crawl_delay)
        print(f"- Crawl-delay: {crawl_delay:g} → rate_limit_rpm = {rpm}")
    else:
        print("- pas de Crawl-delay : le débit est à mesurer, pas à supposer")
    for sitemap in robots.site_maps() or []:
        print(f"- Sitemap : {sitemap}")
    return robots


def _crawl_delay(robots: RobotFileParser) -> float | None:
    """The Crawl-delay robots.txt asks of the scrapers, None without one."""
    delay = robots.crawl_delay(ROBOTS_AGENT)
    return float(delay) if delay else None


def _report_page(response: httpx.Response) -> None:
    """Print what one answer tells: status, weight, validators, content."""
    print(f"\n## {response.request.url}")
    if response.url != response.request.url:
        print(f"- redirigée vers {response.url}")
    elapsed = response.elapsed.total_seconds()
    print(f"- HTTP {response.status_code} en {elapsed:.1f} s")
    print(
        f"- poids : {len(response.content) / 1000:.0f} Ko"
        f" ({response.headers.get('content-type', 'type inconnu')})"
    )
    for header in ("etag", "last-modified", "cache-control", "server", "cf-mitigated"):
        if header in response.headers:
            print(f"- {header}: {response.headers[header]}")
    if response.is_error:
        return
    try:
        payload = json.loads(response.text)
    except ValueError:
        _report_html(Selector(text=response.text), str(response.url))
    else:
        print("- contenu : JSON")
        _report_lists(payload)


def _report_conditional(client: httpx.Client, first: httpx.Response) -> None:
    """Ask the page again with its validators: a 304 spares the weight of a poll."""
    validators = {
        name: first.headers[header]
        for name, header in (
            ("If-None-Match", "etag"),
            ("If-Modified-Since", "last-modified"),
        )
        if header in first.headers
    }
    if not validators:
        print("- GET conditionnel : ni ETag ni Last-Modified, impossible")
        return
    again = client.get(first.request.url, headers=validators)
    honoured = again.status_code == HTTPStatus.NOT_MODIFIED
    verdict = "honoré (304)" if honoured else f"ignoré (HTTP {again.status_code})"
    print(f"- GET conditionnel avec {', '.join(validators)} : {verdict}")


def _report_html(page: Selector, url: str) -> None:
    """Print where an HTML page keeps its listings, and how it paginates."""
    print("- contenu : HTML")
    in_text = len(page.xpath("//text()[contains(., 'CHF')][not(ancestor::script)]"))
    in_scripts = len(page.xpath("//script/text()[contains(., 'CHF')]"))
    print(f"- « CHF » : {in_text} fois dans le texte, {in_scripts} script(s)")
    if not in_text:
        print(
            "  → aucun prix dans le DOM : les annonces viennent d'un JSON embarqué "
            "ou d'un endpoint appelé en JavaScript (onglet réseau du navigateur)"
        )
    for script in page.css("script[type='application/json'], script#__NEXT_DATA__"):
        text = script.xpath("string()").get("")
        name = script.attrib.get("id") or script.attrib.get("data-drupal-selector")
        print(
            f"- JSON embarqué, script {name or 'sans id'} : {len(text) / 1000:.0f} Ko"
        )
        try:
            _report_lists(json.loads(text))
        except ValueError:
            print("  (illisible)")
    types = Counter(re.findall(r'"@type"\s*:\s*"([^"]+)"', _ld_json(page)))
    if types:
        print(f"- JSON-LD : {dict(types)}")
    for feed in page.css("link[rel=alternate][type*=xml]::attr(href)").getall():
        print(f"- flux : {urljoin(url, feed)}")
    if page.css("link[rel='https://api.w.org/']"):
        print("- WordPress : /wp-json/ existe, y chercher une route immobilière")
    cards = Counter(
        f"{card.root.tag}.{'.'.join(card.attrib['class'].split())}"
        for card in page.xpath(f"//*[{_CARD}][not(.//*[{_CARD}])]")
    )
    repeated = [(card, count) for card, count in cards.most_common(3) if count > 1]
    for signature, count in repeated:
        print(f"- bloc répété avec lien et prix : {signature}, {count} fois")
    if not repeated:
        print("- aucun bloc répété avec lien et prix : pas de cartes reconnues")
    links = sorted(
        {href for href in _hrefs(page, url) if _PAGE_LINK.search(href.split("#")[0])}
    )
    print(f"- liens de pagination : {links[:MAX_SHOWN] or 'aucun'}")
    if page.css("link[rel=next]"):
        print(f"- link rel=next : {page.css('link[rel=next]::attr(href)').get()}")


def _ld_json(page: Selector) -> str:
    """The text of every JSON-LD script of the page."""
    return " ".join(
        page.css("script[type='application/ld+json']").xpath("string()").getall()
    )


def _report_lists(payload: object) -> None:
    """Print each list of objects of a JSON payload: where the listings may be."""
    found = False
    for path, items in _object_lists(payload, "", 0):
        found = True
        keys = ", ".join(list(items[0])[:25])
        print(f"  - `{path or '@'}` : {len(items)} objets — clés : {keys}")
    if not found:
        root = list(payload) if isinstance(payload, dict) else type(payload).__name__
        print(f"  - aucune liste d'objets ; racine : {root}")


def _object_lists(
    value: object, path: str, depth: int
) -> Iterator[tuple[str, list[dict[str, object]]]]:
    """Each non-empty list of objects under `value`, with its JMESPath."""
    if depth > MAX_DEPTH:
        return
    if isinstance(value, dict):
        for key, child in value.items():
            yield from _object_lists(child, f"{path}.{key}".lstrip("."), depth + 1)
    elif isinstance(value, list) and value and isinstance(value[0], dict):
        yield f"{path}[*]", value
        yield from _object_lists(value[0], f"{path}[0]", depth + 1)


def _hrefs(page: Selector, url: str) -> set[str]:
    """Absolute links of the page that stay on its host."""
    host = urlsplit(url).netloc
    links = {urljoin(url, href) for href in page.css("a::attr(href)").getall()}
    return {link for link in links if urlsplit(link).netloc == host}


def _items(response: httpx.Response) -> set[str]:
    """What a page lists: the objects of its longest JSON list, or its links."""
    try:
        payload = json.loads(response.text)
    except ValueError:
        return _hrefs(Selector(text=response.text), str(response.url))
    lists = [items for _, items in _object_lists(payload, "", 0)]
    longest = max(lists, key=len, default=[])
    return {json.dumps(item, sort_keys=True) for item in longest}


def _report_pagination(pages: list[httpx.Response]) -> None:
    """Compare the pages to the first one: a phantom page brings nothing new."""
    if len(pages) < 2:  # noqa: PLR2004 - a comparison takes two pages
        return
    print("\n## Les pages sont-elles différentes ?")
    first, *others = pages
    first_items = _items(first)
    for other in others:
        if _digest(other) == _digest(first):
            verdict = "identique à la première : pagination fantôme"
        else:
            items = _items(other)
            new = len(items - first_items)
            verdict = f"{new} élément(s) absents de la première sur {len(items)}"
            if not new:
                verdict += " : pagination fantôme probable"
        print(f"- {other.request.url} : {verdict}")


def _digest(response: httpx.Response) -> str:
    """SHA-256 of the body of an answer."""
    return hashlib.sha256(response.content).hexdigest()


if __name__ == "__main__":
    main()
