# FlatPulse — Architecture technique v3

> Alertes immobilières temps réel pour le marché suisse.
> Infomaniak · LLM gratuit · unittest · KISS / YAGNI / SOLID
>
> **Mis à jour le 22.09.2026.** Remplace `flatpulse-architecture-v2.md` (qui parlait
> encore d'« ImmoRadar », de BeautifulSoup et d'un parc d'agences obsolète).
>
> **Sources de vérité** — ce document décrit l'intention d'ensemble. En cas de conflit :
> 1. Les **stories GitHub** (#41-#81) font foi pour le périmètre, les signatures et les tests.
> 2. `docs/spike-agencies.md` fait foi pour tout ce qui touche une régie précise.
> 3. Ce document fait foi pour la vue d'ensemble et les décisions transverses.

---

## 1. Ce que fait le système

```
[Sites de régies]                                        [Utilisateurs]
 Naef, Burger, Comptoir …                              Telegram · Email
        │                                                      ▲
        ▼                                                      │
   ┌─────────┐   ┌───────┐   ┌──────────┐   ┌──────────┐   ┌────────────┐
   │ Scrape  │──▶│ Dedup │──▶│  Enrich  │──▶│  Match   │──▶│  Notify    │
   │ httpx + │   │ SHA-  │   │ Groq /   │   │ hard +   │   │ Telegram / │
   │ parsel  │   │ 256   │   │ Gemini   │   │ soft     │   │ email      │
   └─────────┘   └───────┘   └──────────┘   └──────────┘   └────────────┘
        │                          │              │               │
        └──────────────────────────┴──────────────┴───────────────┘
                                   ▼
                    PostgreSQL 16 (+ Redis 7, post-MVP)
                    Prometheus + Grafana (observabilité)
```

L'avantage concurrentiel tient en une phrase : **on va chercher l'annonce sur le site de
la régie, pas sur un portail.** Les régies publient chez elles d'abord et syndiquent vers
Homegate/ImmoScout avec 15 min à plusieurs heures de retard. On ne scrape donc aucun
portail — ni pour des raisons techniques (anti-bot agressif) ni juridiques (CGU), et
parce que Comparis occupe déjà ce terrain.

---

## 2. Stack

| Couche | Techno | Note |
|---|---|---|
| Langage | Python 3.14 (`pyproject.toml` : `~3.14`) | asyncio partout |
| HTTP | `httpx` (async) | HTTP/2, client partagé par scraper |
| Parsing HTML | `parsel` (CSS + XPath, lxml) | **jamais BeautifulSoup** |
| Navigateur headless | — | **Aucune régie n'en a besoin** (cf. spike) |
| LLM | `openai` SDK → Groq (Llama 3.3 70B) puis Gemini Flash | free tier, coût 0 CHF |
| DB | PostgreSQL 16 via `psycopg` 3 (async + pool) | **pas d'ORM**, SQL direct dans `db.py` |
| Cache / rate limit | `dict` en mémoire pour le MVP, Redis 7 ensuite | KISS d'abord |
| Migrations | Alembic (#78, avant la prod) | `sql/schema.sql` reste la référence |
| Notifications | `python-telegram-bot`, `aiosmtplib` | Telegram = canal principal |
| Observabilité | `prometheus_client` + Grafana, logs JSON stdlib | |
| Tests | `unittest` + `coverage` | **jamais pytest** |
| Lint / types | `ruff` (format + lint), `mypy --strict` | via `pre-commit` |
| Hébergement | Infomaniak VPS Lite (2 vCPU, 4 GB) | ~CHF 7/mois tout compris |

Interdits explicites, hérités des instructions projet : `beautifulsoup4`, `pytest`,
SQLAlchemy ORM.

---

## 3. Principes de développement

- **SOLID** — une source = une classe de scraper. Ajouter une régie ne modifie aucun
  fichier existant (Open/Closed).
- **DRY** — le parsing des formats suisses vit dans `utils.py`, jamais recopié dans un
  scraper.
- **KISS** — pas d'ORM, pas de framework web, pas de query builder. SQL en clair.
- **YAGNI** — si ce n'est pas dans une story, ça ne se code pas.
- **TDD** — le test échoue (rouge) avant que le code existe. Chaque story liste ses tests
  avec setup, action, assertion et justification.
- **Fail-fast** — la config est validée au démarrage ; un `None` silencieux est un bug.

La **Definition of Done** de chaque story est l'issue #81 : tests d'abord, suite verte
(`python -m unittest discover tests/`), `ruff check src/` propre, zéro `TODO`/`print()`
laissé derrière, docstrings et types sur tout ce qui est public, un commit atomique par
story au format `type(scope): description`, issue fermée avec un résumé.

---

## 4. Modèle de données

Cinq tables, définies dans `sql/schema.sql` (#62) : `sources`, `listings`, `users`,
`search_profiles`, `notifications`.

```sql
CREATE TABLE sources (
    id              SERIAL PRIMARY KEY,
    name            VARCHAR(100) NOT NULL,
    slug            VARCHAR(50) UNIQUE NOT NULL,
    base_url        TEXT NOT NULL,
    scraper_class   VARCHAR(100) NOT NULL,
    poll_interval_s INT NOT NULL DEFAULT 120,
    rate_limit_rpm  INT NOT NULL DEFAULT 10,
    is_active       BOOLEAN DEFAULT TRUE,
    config          JSONB DEFAULT '{}',
    last_scraped_at TIMESTAMPTZ,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE listings (
    id              SERIAL PRIMARY KEY,
    source_id       INT NOT NULL REFERENCES sources(id),
    external_id     VARCHAR(255) NOT NULL,
    external_url    TEXT NOT NULL,
    fingerprint     VARCHAR(64) NOT NULL,

    title           TEXT NOT NULL,
    description     TEXT,
    price_chf       INT,               -- EN CENTIMES (cf. §4.1)
    nb_rooms        DECIMAL(3,1),
    surface_m2      INT,
    floor           INT,
    address         TEXT,
    city            VARCHAR(100),
    canton          VARCHAR(2),
    postal_code     VARCHAR(10),
    listing_type    VARCHAR(10) DEFAULT 'rent',

    enriched        JSONB DEFAULT '{}',
    images          TEXT[] DEFAULT '{}',

    first_seen_at   TIMESTAMPTZ DEFAULT NOW(),
    is_active       BOOLEAN DEFAULT TRUE,

    UNIQUE(source_id, external_id)
);

CREATE INDEX idx_listings_fingerprint ON listings(fingerprint);
CREATE INDEX idx_listings_search ON listings(is_active, city, nb_rooms, price_chf);
CREATE INDEX idx_listings_enriched ON listings USING GIN(enriched);

CREATE TABLE users (
    id          SERIAL PRIMARY KEY,
    email       VARCHAR(255) UNIQUE,
    telegram_id BIGINT UNIQUE,
    lang        VARCHAR(2) DEFAULT 'fr',
    plan        VARCHAR(20) DEFAULT 'free',
    is_active   BOOLEAN DEFAULT TRUE,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE search_profiles (
    id                 SERIAL PRIMARY KEY,
    user_id            INT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name               VARCHAR(100),
    listing_type       VARCHAR(10) DEFAULT 'rent',
    cities             TEXT[],
    cantons            VARCHAR(2)[],
    min_rooms          DECIMAL(3,1),
    max_rooms          DECIMAL(3,1),
    min_price          INT,            -- EN CENTIMES
    max_price          INT,            -- EN CENTIMES
    min_surface        INT,
    required_amenities TEXT[],
    pets_required      BOOLEAN DEFAULT FALSE,
    custom_criteria    TEXT,
    is_active          BOOLEAN DEFAULT TRUE,
    created_at         TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE notifications (
    id          SERIAL PRIMARY KEY,
    user_id     INT NOT NULL REFERENCES users(id),
    listing_id  INT NOT NULL REFERENCES listings(id),
    profile_id  INT NOT NULL REFERENCES search_profiles(id),
    channel     VARCHAR(20) NOT NULL,
    match_score DECIMAL(5,2) NOT NULL,
    sent_at     TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(user_id, listing_id, channel)
);
```

### 4.1 Les montants sont en centimes

`price_chf`, `min_price` et `max_price` stockent des **centimes**, malgré le nom de la
colonne. `CHF 1'850.–/mois` → `185000`. Un budget de 2 500 CHF → `max_price = 250000`.
C'est le contrat posé par `parse_swiss_price()` (#79) et vérifié par les tests de #43 et
#54. Toute valeur affichée à l'utilisateur doit donc être divisée par 100.

### 4.2 Choix de design

- `SERIAL` plutôt qu'`UUID` : plus simple, jointures plus rapides, suffisant à notre
  échelle.
- Pas de table `raw_listings` : le brut part dans les logs si besoin de debug (YAGNI).
- `enriched JSONB` : ajouter un champ extrait par le LLM ne demande pas de migration.
- Pas de table `subscriptions` : le champ `users.plan` suffit jusqu'à Stripe (#68).
- `UNIQUE(source_id, external_id)` : le garde-fou de dedup côté base, doublé du dedup en
  mémoire côté pipeline.
- `UNIQUE(user_id, listing_id, channel)` : un listing n'est jamais notifié deux fois sur
  le même canal.

---

## 5. Architecture objet

Arborescence cible (`src/flatpulse/`) :

```
config.py              Config, validation fail-fast au démarrage
models.py              SourceConfig, MatchResult, ScrapingStats (dataclasses)
utils.py               parse_swiss_price, parse_rooms
db.py                  pool psycopg + helpers CRUD
main.py                orchestration du pipeline
common/
  logging_configuration.py
scrapers/
  base.py              AbstractScraper (ABC), HttpScraper
  rate_limiter.py      TokenBucket / RateLimiter
  dedup.py             DeduplicationService
  adaptive_poller.py   AdaptivePoller
  sources/
    naef.py  burger.py  comptoir.py  …
enrichment/
  enricher.py          LlmProvider, LlmProviderChain, LlmEnricher
  prompts.py           templates d'extraction
matching/
  engine.py            MatchingEngine (+ chargement/refresh des profils)
distribution/
  base.py              Notifier (ABC), Dispatcher
  telegram.py          TelegramNotifier + handlers du bot
  email.py             EmailNotifier
```

### 5.1 Scraping (#41, #42, #46, #47, #48)

**`AbstractScraper`** (ABC) expose `fetch_listings() -> list[dict]` (abstraite) et
`run()` (concrète : rate limit → fetch → retour). On n'override pas `run()`.

**`HttpScraper`** implémente le fetch HTTP + parsing `parsel.Selector`. C'est la seule
implémentation nécessaire : le spike a confirmé qu'aucune des 13 régies analysées ne
requiert un navigateur headless. Les sources « JS-rendered » (Naef, Bory, Rosset,
Bernard Nicod) exposent toutes un endpoint JSON ou un état hydraté qu'on lit directement.

Chaque dict produit porte au minimum `external_id`, `external_url`, `title`, plus
`price_chf`, `nb_rooms`, `surface_m2`, `floor`, `address`, `city`, `description`,
`images` en optionnel — **`None` si absent, jamais d'exception, jamais `0`**.

**Fingerprint** : `SHA-256(external_url + title + str(price_chf))`, 64 caractères hex,
déterministe. Un changement de prix change le fingerprint → détection de baisse de prix.

**`RateLimiter`** : un token bucket par `slug`, capacité = `rate_limit_rpm`, refill de
`RPM/60` token par seconde, basé sur `time.monotonic()`. `acquire()` attend (async),
`can_acquire()` teste sans consommer. Les sources sont indépendantes : saturer `naef` ne
doit jamais bloquer `burger`. Un ban = une source perdue, c'est la protection centrale.

**`DeduplicationService`** : clé `source_slug:external_id`. `is_new()` (fingerprint
jamais vu) et `has_changed()` (même source+id, fingerprint différent). Dict en mémoire
pour le MVP.

**`AdaptivePoller.compute_interval()`** : source active (>5 annonces/h) → intervalle ÷ 2 ;
inactive (0 depuis 6 h) → × 2 ; erreurs consécutives → × 2ⁿ ; nuit et week-end → × 3.
Bornes strictes : **30 s ≤ intervalle ≤ 600 s**.

### 5.2 Enrichissement LLM (#50, #51, #52)

C'est le différenciateur produit : extraire d'une description en texte libre ce qu'aucun
portail ne filtre (machine à laver, animaux, balcon, étage, bruit…).

**`LlmProvider`** encapsule `base_url` / `api_key` / `model` et expose
`complete(prompt) -> str`. Tous les providers sont compatibles SDK `openai`, donc changer
de provider = changer une variable d'environnement.

**`LlmProviderChain`** essaie les providers dans l'ordre et bascule au suivant sur 429,
timeout ou 5xx. Si tous échouent : retourne `"{}"`, log l'erreur, **ne crashe jamais**.
Un listing non enrichi vaut mieux qu'un pipeline à terre.

| Priorité | Provider | Modèle | Free tier |
|---|---|---|---|
| 1 | Groq | Llama 3.3 70B | ~1 000 req/jour, 30 RPM |
| 2 | Gemini Flash | Gemini 2.5 Flash | ~1 500 req/jour |
| 3 | Cerebras (backup de backup) | Llama 3.3 70B | ~1M tokens/jour |

**`LlmEnricher.enrich(title, description, raw_data) -> dict`** construit le prompt,
parse le JSON, valide, et **fusionne en donnant priorité au scraper** : une donnée
structurée extraite du DOM est plus fiable qu'une inférence LLM. Le LLM ne comble que les
trous. Un JSON malformé → `{}` + log, pas d'exception.

Champs extraits : `nb_rooms`, `surface_m2`, `floor`, `has_balcony`,
`has_washing_machine`, `has_dishwasher`, `has_elevator`, `pets_allowed`, `parking`,
`nearby_transport`, `noise_level`, `furnished`, `charges_included`, `charges_chf`,
`confidence_score`. Multilingue FR/DE/IT/EN — les annonces alémaniques sont en allemand.

**Cache** : `SHA-256(description) → résultat`, consulté avant tout appel, TTL 7 jours,
dict en mémoire. À 30 RPM sur Groq, chaque appel évité est de la marge pour les vraies
nouveautés.

### 5.3 Matching (#54, #55)

`MatchingEngine.match(listing, profiles) -> list[MatchResult]`, en deux temps :

1. **Hard filters** (éliminatoires) : ville/canton, prix min/max, nombre de pièces,
   type (rent/buy). Un échec → le profil est ignoré, pas de notification.
2. **Soft scoring** (0-100, pondéré) : amenities matchées **40 %**, prix **30 %**
   (plus bas que le budget = meilleur score), surface **20 %**, fraîcheur **10 %**.

Seuil par défaut 50. Le score doit rester dans `[0, 100]` quelle que soit l'entrée — le
throttling et l'affichage Telegram en dépendent. Objectif de perf : 1 000 profils en
< 100 ms, donc tout se fait en mémoire, zéro requête DB par profil.

Les profils actifs sont chargés au démarrage et rafraîchis toutes les 60 s (jointure avec
`users` pour récupérer le `plan`, nécessaire au throttling). Un profil créé doit produire
des alertes en < 60 s, pas au prochain redémarrage ; un profil supprimé doit disparaître
au refresh suivant.

### 5.4 Distribution (#57, #58, #59, #60)

**`Notifier`** (ABC) : `send(user, listing, score) -> bool`. Une implémentation par canal.

**`TelegramNotifier`** — canal principal : Markdown V2, photo de l'annonce, prix, pièces,
surface, amenities matchées, lien, score. Boutons inline « Voir l'annonce », « Pas
intéressé », « Pause ». Un user qui a bloqué le bot (403) → `False`, jamais une exception
qui casserait la notification des autres.

**Bot Telegram** (#58) : `/start` (inscription), `/profile` (wizard conversationnel
ville → prix → pièces → amenities), `/list`, `/pause`, `/resume`, `/help`. Réponses en FR
par défaut.

**`EmailNotifier`** — canal secondaire, HTML responsive inline, SMTP Infomaniak ou Resend.

**`Dispatcher`** : choisit le canal (Telegram si `telegram_id`, sinon email), vérifie la
dedup `(user_id, listing_id, channel)` avant d'envoyer, applique le throttling par plan
— **free 5/h, standard 20/h, premium 50/h** — et journalise chaque envoi en base.

### 5.5 Pipeline (#64)

Boucle asyncio : pour chaque source, scrape → dedup → puis, par nouveau listing,
enrich → match → dispatch. Arrêt propre sur SIGTERM/SIGINT. **L'erreur d'une source
n'affecte jamais les autres** : un site down ne bloque pas le pipeline. Un doublon
court-circuite avant l'enrichissement, pour ne pas consommer de quota LLM.

---

## 6. Sources — état réel du parc

Relevé du 22.09.2026, détail complet (URL, pagination, sélecteurs, mapping de champs et
pièges) dans **`docs/spike-agencies.md`**. Aucune ne nécessite Playwright.

| Régie | Slug | Statut | Accès | Fiches | Débit |
|---|---|---|---|---|---|
| Naef Immobilier | `naef` | **MVP** | `admin-ajax.php` JSON, tout le parc en 1 GET | 355 (58 GE) | poll 90-120 s |
| Rodolphe Burger SA | `burger` | **MVP** | HTML, `?page=N`, 6/page | 32 (32 GE) | ~4 req/min |
| Comptoir Immobilier | `comptoir` | **MVP** | HTML, `?page=N`, 24/page | 29 (29 GE) | Crawl-delay 10 → **6 rpm** |
| Rosset & Cie | `rosset` | phase 2 | API REST publique JSON | 165 (105 GE) | à mesurer |
| Bory & Cie | `bory` | phase 2 | `__NEXT_DATA__`, curseur Relay | 20/28 | à mesurer |
| Moser Vernet | `moservernet` | phase 2 | HTML, catalogue entier en 1 page (2,9 Mo) | 150 | **GET conditionnel obligatoire** |
| Bernard Nicod | `bernard-nicod` | phase 2 | JSON enveloppant du HTML | 17 | à mesurer |
| Bordier & Schmidhauser | `bordier` | phase 2 | HTML, plugin RealForce | 46 | Cloudflare sans challenge |
| Zimmo | `zimmo` | catalogue | HTML | ≥4 | à mesurer |
| Gerofinance | `gerofinance` | catalogue | HTML | 11 | à mesurer |
| Pilet & Renaud | `pilet-renaud` | à trancher | endpoint AJAX non identifié | — | — |
| CPEG | `cpeg` | à trancher | iframe Blazor + portail_api | — | Crawl-delay 10 |
| Grange & Cie | `grange` | **écartée** | 403 Cloudflare sur empreinte TLS | — | — |

### 6.1 Pièges transverses

Ces cas sont **observés**, pas hypothétiques. Un scraper qui les ignore produit des
données fausses silencieusement.

- **Prix sur demande → `None`, jamais `0`.** Un `0` traverse les hard filters de prix et
  déclenche des notifications absurdes.
- **Formats de prix multiples** : `CHF 3'500.— / mois`, `CHF 2'320.- + charges`,
  `Dès CHF 2'320.- + charges`. Tiret cadratin comme tiret simple. Écarter les lignes
  contenant « charges » casse le format « Dès … + charges ».
- **Surface** absente, en fourchette (`de 85 M2 à 100 M2`) ou préfixée (`ENV. 60 M2`).
- **Le slug ment** : une URL `…35-pieces` pour une annonce affichée « 3.0 pièces ». Le
  texte fait foi, pas l'URL.
- **Dedup et query string** : chez Zimmo toutes les fiches partagent le même chemin, seul
  `?ref=` les distingue. Une dedup générique qui tronque la query string fait disparaître
  des annonces (4 → 1 lors du spike).
- **Pagination fantôme** : `?page=2` peut renvoyer les mêmes cartes (Moser Vernet), et
  l'URL `/page-N/` un shell vide (Naef). Ne jamais paginer par URL sans l'avoir vérifié.
- **Listings hétérogènes** : logements mélangés avec commerces et parkings (Burger),
  location mélangée avec vente et tous cantons (Rosset). Filtrer côté scraper — les
  paramètres de filtre de la source sont parfois ignorés côté serveur.
- **Canton** tantôt en toutes lettres, tantôt en code, parfois absent. La colonne est un
  `VARCHAR(2)` : normaliser.
- **Poids des pages** : Moser Vernet = 2,9 Mo par poll, soit ~2,8 Go/jour à 90 s sans
  `If-None-Match`.

---

## 7. Observabilité

**Métriques** (#76) exposées par `prometheus_client` sur le port 9090, scrapées toutes
les 15 s :

| Composant | Métrique | Type | Labels |
|---|---|---|---|
| Scraper | `flatpulse_scrape_total` | Counter | `source`, `status` |
| | `flatpulse_scrape_duration_seconds` | Histogram | `source` |
| | `flatpulse_listings_new_total` | Counter | `source` |
| | `flatpulse_scrape_last_success` | Gauge | `source` |
| LLM | `flatpulse_enrichment_total` | Counter | `provider`, `status` |
| | `flatpulse_enrichment_duration_seconds` | Histogram | `provider` |
| Matching | `flatpulse_matches_total` / `flatpulse_match_score` | Counter / Histogram | — |
| Distribution | `flatpulse_notifications_total` | Counter | `channel`, `status` |
| Système | `flatpulse_active_users` / `flatpulse_active_profiles` | Gauge | — |

Les erreurs sont comptées explicitement (`status="error"`), sans quoi le dashboard est
aveugle aux pannes.

**Dashboard + alertes** (#77) : santé des scrapers, nouvelles annonces/h, latence LLM
(p50/p95/p99), notifications. Alertes vers Telegram — scraper muet depuis > 1 h, LLM en
erreur > 50 %, échecs de notification > 10 %.

**Logs** (#74) : JSON en prod, texte lisible en dev, pilotés par `LOG_LEVEL` et
`LOG_FORMAT`. Un log par annonce traitée et un par cycle de scraping, traceback complet
sur erreur.

---

## 8. Tests

`unittest` uniquement. Lancement : `python -m unittest discover tests/`, ou
`coverage run` (configuré dans `pyproject.toml` pour produire `junittest.xml`).

Arborescence visée par les stories :

```
tests/
  unit/          test_scrapers, test_rate_limiter, test_dedup, test_enricher,
                 test_matching, test_telegram, test_dispatcher, test_db,
                 test_utils, test_config, test_adaptive
  contract/      test_scraper_contract.py  → ScraperContractMixin
  integration/   test_pipeline.py
  fixtures/      HTML et JSON figés, une par régie
```

**`ScraperContractMixin`** (#48) est hérité par le test de chaque scraper et vérifie
quatre invariants sans duplication : retour `list`, champs requis non vides
(`external_url` commence par `http`), `fingerprint` hex de 64 caractères, idempotence
sur le même HTML.

```python
class TestNaefScraper(ScraperContractMixin, unittest.TestCase):
    def setUp(self):
        self.scraper = NaefScraper(...)
        self.fixture = load_fixture("naef_location.json")
```

Tout nouveau scraper **doit** arriver avec sa fixture figée dans `tests/fixtures/` et son
test dédié, en plus des quatre contrats hérités.

---

## 9. Roadmap

10 sprints, août 2026 → janvier 2027, ~5 h/semaine. Découpage par epic :

| Sprint | Contenu | Stories |
|---|---|---|
| 1 | Fondations scraping + schema + couche DB | #41, #42, #48, #62, #71 |
| 2 | Socle partagé (utils, models, config) | #79, #63 |
| 3 | Scrapers concrets + dedup | #43, #44, #45, #46, #47 |
| 3-4 | Enrichissement LLM | #50, #51, #52 |
| 4 | Matching | #54, #55 |
| 5 | Distribution | #57, #58, #59, #60 |
| 6 | Pipeline end-to-end | #64 |
| 8 | Logging structuré + métriques | #74, #76 |
| 9 | Alembic, Grafana, VPS, privacy LPD | #78, #77, #66, #75 |
| 10 | Beta privée, landing, Stripe | #73, #67, #68 |

Phases produit : **Phase 1 MVP** = 3 scrapers + pipeline + Telegram.
**Phase 2 Monétisation** = régies supplémentaires, Stripe, email, landing.
**Phase 3 Différenciation** = postulation automatisée, filtres temps de trajet, WhatsApp,
PWA, analytics de prix.

---

## 10. Produit

### 10.1 Positionnement

> **« L'anti-MieterPlus »** — Plus rapide que les portails. Plus intelligent que Comparis.
> 10× moins cher.

### 10.2 Filtres

Classiques : ville, canton, NPA, prix, pièces, surface, location/achat.

Intelligents (extraits par LLM — c'est ce que personne d'autre ne fait) : machine à
laver, lave-vaisselle, balcon/terrasse, animaux acceptés, étage, ascenseur, parking,
proximité des transports, meublé, charges incluses, année de rénovation, niveau de bruit,
et surtout **critères en texte libre** matchés par le LLM contre la description.

### 10.3 Plans

| Plan | Prix | Profils | Notifs/jour | Throttle | Canaux | Filtres LLM |
|---|---|---|---|---|---|---|
| Free | 0 CHF | 1 | 5 | 5/h | Telegram | Non |
| Standard | 6.90 CHF/mois | 3 | 50 | 20/h | Telegram + email | Oui |
| Premium | 12.90 CHF/mois | 10 | illimité | 50/h | Tous | Oui + critères custom |

Annulation en un clic, aucun dark pattern.

### 10.4 Coûts

| Poste | CHF/mois |
|---|---|
| VPS Lite Infomaniak | ~5.90 |
| PostgreSQL, Redis (self-hosted) | 0 |
| LLM (free tiers) | 0 |
| Telegram Bot API | 0 |
| Domaine .ch | ~1 |
| Email transactionnel | 0 |
| **Total** | **~7** |

Seuil de rentabilité : **un seul client Standard**.

Conformité : page privacy LPD obligatoire avant le lancement public (#75), données
hébergées en Suisse, suppression via `/delete` dans le bot.

---

## 11. Écarts connus — à trancher

Points où les stories, le spike et le code divergent aujourd'hui. À arbitrer avant
d'implémenter les stories concernées.

1. **Arborescence des tests.** Les stories visent `tests/unit/`, `tests/contract/`,
   `tests/integration/`. Le repo, généré par CookieBlueprint, a `tests/flatpulse/`.
   Décider laquelle gagne et aligner l'autre — les commandes `python -m unittest
   tests.unit.test_x` des stories en dépendent.
2. **Naef : HTML ou JSON ?** La story #43 parle d'une fixture `naef_listing.html` et de
   sélecteurs CSS. Le spike a établi que Naef est un endpoint JSON et la fixture livrée
   est `tests/fixtures/naef_location.json`. La story est à corriger.
3. **URL de Burger.** Story #44 : `burgerimmo.ch`. Spike : `burger-sa.ch`.
4. **Playwright.** L'epic #49 le liste en fallback phase 2. Le spike conclut qu'aucune
   régie n'en a besoin, et que la seule bloquée (Grange) l'est par une empreinte TLS
   qu'un navigateur headless ne résout pas non plus. `BrowserScraper` relève donc de
   YAGNI tant qu'aucune source ne le justifie.
5. **Genève vs Zürich.** Les 13 régies du spike sont romandes (Genève/Vaud), mais les
   exemples de profils dans les stories (#54, #58) utilisent Zürich. Le MVP couvre-t-il
   Genève seulement ? Si oui, aligner les exemples ; sinon, un spike alémanique manque.
6. **Version de Python.** `pyproject.toml` impose `~3.14`, la story #66 installe
   `python3.12` sur le VPS. Aligner sur 3.14.
7. **Dépendances manquantes.** `pyproject.toml` ne déclare aujourd'hui que `numpy`,
   `httpx` et `parsel`. Manquent `psycopg`, `openai`, `python-telegram-bot`,
   `aiosmtplib`, `prometheus-client`, `alembic` — à ajouter par la story qui les
   introduit, pas en bloc (YAGNI). `numpy` est un reliquat du template : à retirer s'il
   ne sert à rien.
8. **Redis.** Prévu dans le docker-compose (#63) et l'infra, mais le MVP fonctionne avec
   des dicts en mémoire (rate limiter, dedup, cache LLM). Ne le brancher que quand le
   multi-worker l'impose.
