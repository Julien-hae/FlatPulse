# La story de la régie

`CLAUDE.md` le pose : on lit la story avant d'implémenter, et ce qui n'est pas dans une
story ne se code pas. Une régie sans story n'est donc pas prête — mais la story se
rédige vite quand l'entrée du spike est complète, puisqu'elle en est la traduction en
critères et en tests.

## La story existe

La lire en entier : description, critères d'acceptation, tests (setup, action,
assertion, pourquoi), points d'attention, « Par où commencer ». Lire aussi ses
commentaires et les stories qu'elle cite en dépendance.

Deux lectures à faire avec recul :

- Une story peut précéder un changement du socle. Les stories d'avant #155 nomment
  `_fiche_urls`, `_get_html`, `_parse_or_skip` : lire `fiche_urls`,
  `CatalogueScraper.fetch_listings`, `_build_or_skip`. Celles d'avant #114 parlent de
  `listing: dict` : lire `Listing`. `docs/architecture.md` §11 tient la liste.
- Sur ce qui touche le site de la régie, le spike fait foi contre la story (URL, format
  JSON ou HTML, sélecteurs). Sur le périmètre, les signatures et les tests, c'est la
  story. Tout écart se signale, et se note en §11 s'il n'y est pas.

## La story manque

Rédiger un brouillon dans le format ci-dessous, à partir de l'entrée du spike, et le
montrer à l'utilisateur. **Créer l'issue est un geste visible de l'extérieur : il se
fait avec son accord**, pas d'office. Une fois créée, l'issue est la référence ; le
brouillon ne se garde pas dans le dépôt.

Titre : `[S<n>] Scraper <Régie>`, `<n>` étant le numéro qui suit la dernière story
`[S…]`. Labels des stories de scraping existantes : `story`, `scraping`, une priorité,
une phase (demander laquelle).

```markdown
## 🎯 Objectif
Que les annonces de <Régie> entrent dans FlatPulse : une phrase, côté utilisateur.

## 📋 Description
Constat sur le site au JJ.MM.AAAA (`docs/spike-agencies.md`, section `<slug>`) :
- Accès : …
- Volume : N fiches, dont G à Genève ; types de biens présents
- Forme : `CatalogueScraper` | `FicheScraper`, donc X requêtes par poll, soit ≈ Y min à Z rpm

| Champ | Où sur le site | Exemple brut |
|---|---|---|
| `price_chf` | … | `CHF 1’850/mois (+ CHF 175 charges)` |

## 🔍 Approche
- Classe `<Régie>Scraper` dans `scrapers/sources/<slug>.py`
- Ce qui se réutilise de `utils.py` ; ce qu'il faut y ajouter (format ou libellé nouveau), avec son test
- Les décisions : identifiant retenu, loyer charges comprises ou non, ce qui reste à `None` parce que non publié

## 🔧 Technologies
- `httpx`, `parsel` — aucune nouvelle dépendance

## 🔗 Dépendances
- **Bloqué par** : … (story du socle si la régie en demande une)
- **Débloque** : …

## ✅ Critères d'acceptation
- [ ] `fetch_listings()` rend toute l'offre de la source, étiquetée (`property_type`, `canton`, `postal_code`), sans rien écarter
- [ ] Prix sur demande → `price_chf is None`
- [ ] (un critère par piège du spike)
- [ ] Zéro modification de `base.py` ni des autres scrapers
- [ ] Fixtures de cas nommés, chacune sous 100 Ko, URLs valides
- [ ] Source enregistrée dans l'audit en direct, premier run consigné dans `docs/live-audit.md`
- [ ] `docs/spike-agencies.md` et `docs/architecture.md` §6 à jour

## 🧪 Tests (unittest)
Fixtures : `tests/fixtures/<slug>_cases.<ext>` (+ `tests/fixtures/<slug>/`).

### `test_<slug>_full_apartment`
| | |
|---|---|
| **Setup** | Annonce `<id>` de la fixture (appartement genevois complet). |
| **Action** | `fetch_listings()` |
| **Assertion** | `price_chf == 185000`, `nb_rooms == 3.5`, `city == "Genève"`, … |
| **Pourquoi** | Le cas nominal, champ par champ : un sélecteur qui dérive casse ici. |

### `test_<slug>_price_on_request_is_none`
…

+ 5 tests hérités de `ScraperContractMixin`.

## ⚠️ Points d'attention
- Durée d'un poll si elle dépasse 3 min ; pièges du spike qui ne sont pas des tests

## 📐 Effort : S (< 2h) | M (2-4h) | L

## 🚀 Par où commencer
1. Figer la fixture → 2. premier test rouge → 3. …
```

Les valeurs des assertions viennent des annonces réelles choisies pour la fixture : la
story et la fixture s'écrivent donc ensemble. Un test par piège du spike, pas plus —
« au cas où » n'est pas un cas.

Exemples de villes et d'annonces : genevois (Carouge, Plainpalais, Eaux-Vives), jamais
Zürich.

## Ce qui ne tient pas dans cette story

Si la régie demande une troisième forme de scraper, une requête que `_get()` ne sait pas
faire ou un champ que `Listing` n'a pas (voir l'étape 2 du skill), ce n'est pas un
paragraphe de plus dans la story du scraper : c'est une story du socle, à rédiger à
part et à lister en « Bloqué par ». Un commit, une story.
