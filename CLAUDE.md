# FlatPulse

Alertes immobilières temps réel pour le marché suisse. On scrape les sites des régies
directement (avant les portails), un LLM gratuit enrichit les annonces, un moteur de
matching les score, les alertes partent sur Telegram en < 3 min.

Side project, ~5 h/semaine, hébergé sur un VPS Infomaniak à ~CHF 7/mois. Le seuil de
rentabilité est d'un client. Toute solution qui coûte cher en temps ou en argent est
hors sujet.

**Le MVP couvre le canton de Genève uniquement.** Les régies scrapées sont romandes ;
une extension alémanique demanderait son propre spike. Utiliser des villes genevoises
dans les exemples et les fixtures, pas Zürich.

## Où est la vérité

| Question | Fichier |
|---|---|
| Quoi construire, dans quel ordre, avec quels tests | **Les issues GitHub** (#41-#81) |
| Comment le système est architecturé | `docs/architecture.md` |
| Comment scraper une régie précise | `docs/spike-agencies.md` |
| Ce qui compte comme « terminé » | Issue #81 (Definition of Done) |

**Avant d'implémenter quoi que ce soit, lire la story GitHub correspondante.** Chaque
story porte ses critères d'acceptation et la spec de ses tests (setup, action,
assertion, justification). Ne pas réinventer ce qui y est déjà décidé. Les écarts connus
entre stories, spike et code sont listés en §11 de `docs/architecture.md`.

## Stack et commandes

Python 3.14, Poetry. `make` installe l'environnement et les hooks pre-commit.

```bash
python -m unittest discover tests/   # tests
coverage run && coverage xml         # tests + couverture (junittest.xml)
ruff format . && ruff check src/     # format + lint
mypy src/                            # typage strict
```

`pre-commit` enchaîne poetry-check, ruff (format + lint), mypy et les tests.

Les tests sont rangés par ce dont ils ont besoin pour tourner : `tests/unit/` (rapide,
tout mocké), `tests/contract/` (les invariants que tout scraper doit respecter),
`tests/integration/` (a besoin d'un vrai PostgreSQL ou du réseau), `tests/fixtures/`
(données figées). Pas de dossier `regression/` : un test né d'un bug est un test
unitaire, il va dans `unit/` à côté du code qu'il couvre.

## Règles non négociables

- **`parsel`, jamais `beautifulsoup4`.** `unittest`, jamais `pytest`. `psycopg` en SQL
  direct, jamais d'ORM SQLAlchemy.
- **TDD** : le test est écrit et échoue avant le code. Les stories donnent les tests.
- **YAGNI** : si ce n'est pas dans une story, ça ne se code pas. Pas de « au cas où ».
- **DRY** : le parsing suisse vit dans `utils.py` (`parse_swiss_price`, `parse_rooms`),
  jamais recopié dans un scraper.
- **Open/Closed** : une nouvelle régie = une nouvelle classe dans `scrapers/sources/`,
  zéro modification de l'existant.
- **Fail-fast** : config validée au démarrage, erreurs explicites, pas de `None`
  silencieux.
- **KISS** : dict en mémoire avant Redis, SQL en clair, pas de framework web.

## Definition of Done (#81)

Tests écrits en premier et verts · `ruff check src/` propre · aucun `print()`, `TODO`,
`FIXME` ou `pass` temporaire laissé · docstrings sur tout ce qui est public · signatures
typées · un commit atomique par story (`feat(scraping): implement NaefScraper…`) · issue
fermée avec un résumé.

## Pièges du domaine

- **Les montants sont en centimes.** `price_chf`, `min_price`, `max_price` :
  `CHF 1'850.–` → `185000`. Diviser par 100 pour l'affichage.
- **Prix sur demande → `None`, jamais `0`.** Un `0` passe les hard filters de prix et
  déclenche des notifications absurdes.
- **Formats suisses** : `3½` = `3.5`, `Studio` = `1.0`, apostrophe comme séparateur de
  milliers, tiret cadratin autant que tiret simple, annonces en FR **et** en DE.
- **Champ absent → `None`, jamais une exception.** Un scraper ne crashe pas sur une
  annonce incomplète.
- **Fingerprint** : `SHA-256(external_url + title + str(price_chf))`. Dedup sur
  `source_slug:external_id`. Attention aux régies dont les fiches ne diffèrent que par
  la query string — une dedup qui tronque `?ref=` fait disparaître des annonces.
- **Rate limit par source**, valeurs mesurées dans `docs/spike-agencies.md`. Un ban =
  une source perdue. Et `If-None-Match` sur les pages lourdes (Moser Vernet : 2,9 Mo par
  poll).
- **Le pipeline ne tombe jamais** à cause d'un maillon : LLM en erreur → `{}`, source
  down → les autres continuent, user qui bloque le bot → `False`.

## Points d'attention en review

- **Secrets** : aucune clé (Groq, Gemini, `TELEGRAM_BOT_TOKEN`, `DATABASE_URL`) en clair.
  Variables d'environnement uniquement.
- **Scraping éthique** : respecter le débit documenté pour la régie, pas un rythme
  arbitraire.
- **Nouveau scraper** = fixture figée dans `tests/fixtures/` + test dédié + les 4
  contrats de `ScraperContractMixin`, et mise à jour de `docs/spike-agencies.md` si la
  source a changé de comportement.
- **`mypy --strict`** : pas de `Any` non justifié, pas d'ignore sans commentaire.
- **Périmètre** : une story = un commit. Signaler si un changement déborde de la story
  plutôt que d'élargir le diff.
