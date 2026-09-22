---
name: nouveau-scraper
description: Ajouter le scraper d'une nouvelle régie immobilière à FlatPulse, en TDD, depuis le spike jusqu'à la fermeture de l'issue. À utiliser quand on implémente une story [S*] de scraper (Naef, Burger, Comptoir, Rosset, Bory…), quand on ajoute une source au parc, ou quand un scraper existant casse parce que la régie a changé son site.
---

# Ajouter un scraper de régie

Une régie = une classe. Ajouter une source ne doit modifier **aucun** fichier existant
hors enregistrement de la source (Open/Closed).

## 1. Lire avant d'écrire

Deux documents, dans cet ordre, et il faut vraiment les ouvrir :

1. **La story GitHub** (`[S3]`, `[S4]`, `[S5]`…) — elle porte les critères
   d'acceptation et la spec des tests attendus (setup, action, assertion).
2. **L'entrée de la régie dans `docs/spike-agencies.md`** — URL d'accès exacte,
   pagination, mapping des champs ou sélecteurs CSS, débit autorisé, canal de repli, et
   surtout la section **Pièges**. Ces pièges sont observés sur le site réel, pas
   supposés. Les ignorer produit des données fausses silencieusement.

Si la story et le spike se contredisent (ça arrive : la story #43 décrit Naef en HTML
alors que c'est un endpoint JSON), **le spike gagne** — il est plus récent et mesuré.
Signaler l'écart plutôt que de coder au hasard.

## 2. La fixture d'abord

Le test tape sur une fixture figée, jamais sur le réseau.

- Elle existe probablement déjà : `tests/fixtures/<slug>_*.html` ou `.json` ont été
  capturées pendant le spike.
- Sinon, capturer la réponse réelle une fois, l'anonymiser si besoin, et la committer.
- Une fixture doit contenir **plusieurs annonces**, dont au moins un cas tordu du spike
  (prix sur demande, surface en fourchette, ligne « + charges »…).

## 3. Le test, rouge

```python
class TestNaefScraper(ScraperContractMixin, unittest.TestCase):
    def setUp(self) -> None:
        self.scraper = NaefScraper(...)
        self.fixture = load_fixture("naef_location.json")
```

Hériter de `ScraperContractMixin` apporte gratuitement les 4 invariants communs : retour
`list`, champs requis non vides (`external_url` commence par `http`), `fingerprint` hex
de 64 caractères, idempotence sur le même HTML.

S'y ajoutent les tests propres à la régie, tirés de la story : au minimum un
`test_parse_<slug>_fixture`, plus un test par piège du spike qu'on peut exprimer
(format de prix particulier, pièces en `3½`, annonce sans prix…).

Lancer, vérifier que c'est **rouge pour la bonne raison** (pas un `ImportError`), puis
seulement implémenter.

## 4. Implémenter

Fichier : `src/flatpulse/scrapers/sources/<slug>.py`. Une sous-classe de `HttpScraper`
qui implémente `fetch_listings() -> list[dict]`. On n'override jamais `run()` : le rate
limiting y est déjà câblé.

Règles qui ne se négocient pas :

- **Réutiliser `utils.parse_swiss_price` et `utils.parse_rooms`.** Ne jamais réécrire un
  parsing de prix ou de pièces dans un scraper (DRY). Si un format n'est pas couvert, on
  étend `utils.py` **et** son test, on ne contourne pas.
- **Les montants sont en centimes** : `CHF 1'850.–` → `185000`.
- **Champ absent → `None`, jamais `0`, jamais une exception.** Un prix sur demande à `0`
  traverse les hard filters et déclenche des notifications absurdes.
- **Filtrer le bruit** : les listings mélangent logements, commerces, parkings, et
  parfois location et vente, tous cantons confondus. Les paramètres de filtre de la
  source sont parfois ignorés côté serveur — filtrer côté scraper.
- **MVP = Genève.** Écarter ce qui est hors canton.
- **`external_id` stable** : la clé de dedup est `source_slug:external_id`. Choisir un
  identifiant qui ne bouge pas entre deux polls et qui distingue vraiment deux fiches —
  attention aux régies dont les annonces partagent le même chemin d'URL et ne diffèrent
  que par la query string.
- Typage complet, docstrings sur tout ce qui est public (`mypy --strict` tourne).

Enregistrer la source dans `sources` avec le `slug`, le `scraper_class`, et le
`rate_limit_rpm` / `poll_interval_s` **mesurés dans le spike** — pas une valeur au
hasard. Un ban, c'est une source perdue.

## 5. Vert, puis vérifier

```bash
python -m unittest discover tests/
ruff format . && ruff check src/
mypy src/
```

## 6. Clore proprement

Definition of Done (issue #81) : suite verte, lint propre, aucun `print()`, `TODO`,
`FIXME` ou `pass` temporaire, docstrings et types en place.

Un commit atomique : `feat(scraping): implement NaefScraper with JSON payload parsing`.

Puis fermer l'issue avec un résumé de ce qui a été fait. Et si le site s'est révélé
différent de ce que décrivait le spike, **mettre `docs/spike-agencies.md` à jour dans le
même commit** — c'est la référence du prochain scraper.
