# FlatPulse 🏠⚡

> Alertes immobilières en temps réel pour le marché suisse — Plus rapide que les portails, plus intelligent que Comparis, 10x moins cher que MieterPlus.

[![CI](https://github.com/Julien-hae/FlatPulse/actions/workflows/ci.yml/badge.svg)](https://github.com/Julien-hae/FlatPulse/actions/workflows/ci.yml)
[![Security](https://github.com/Julien-hae/FlatPulse/actions/workflows/security.yml/badge.svg)](https://github.com/Julien-hae/FlatPulse/actions/workflows/security.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

---

## Le problème

En Suisse, un bon appartement part en heures. Les locataires paient CHF 30+/mois pour MieterPlus (qui donne accès à 23 annonces sur 863 à Zürich). Comparis agrège les portails, mais lentement et sans filtres intelligents.

## La solution

FlatPulse scrape les agences **directement à la source** (Naef, Burger, Comptoir, etc.) pour détecter les annonces **avant qu'elles n'apparaissent sur les portails**. Un LLM gratuit extrait les données structurées des descriptions (machine à laver, animaux, balcon...), un moteur de matching score chaque annonce, et les notifications arrivent sur Telegram en < 3 minutes.

---

## Architecture

```
[Sites d'agences]                [Utilisateurs]
  Naef, Burger,                    Telegram, Email
  Comptoir, ...                         ↑
       ↓                               |
  ┌─────────┐   ┌───────┐   ┌─────────┐   ┌────────────┐
  │ Scrapers │──→│ Dedup │──→│ LLM     │──→│ Matching   │──→ Notifications
  │ httpx +  │   │ SHA-  │   │ Groq /  │   │ Hard+Soft  │
  │ parsel   │   │ 256   │   │ Gemini  │   │ Score 0-100│
  └─────────┘   └───────┘   └─────────┘   └────────────┘
       ↓                          ↓              ↓
  ┌──────────────────────────────────────────────────────┐
  │       PostgreSQL 16 (+ Redis 7, post-MVP)            │
  └──────────────────────────────────────────────────────┘
       ↓
  ┌──────────────────────────────────────────────────────┐
  │           Prometheus + Grafana (monitoring)          │
  └──────────────────────────────────────────────────────┘
```

## Stack technique

| Composant | Technologie | Pourquoi |
|---|---|---|
| Langage | Python 3.14 | Écosystème scraping mature, async natif |
| Scraping | httpx + parsel | Async HTTP + parsing CSS/XPath rapide (lxml-based) |
| LLM | Groq (Llama 3.3 70B), Gemini Flash | Gratuit, rapide, fallback chain |
| Base de données | PostgreSQL 16 | JSONB pour données flexibles, GIN index |
| Cache | `dict` en mémoire (Redis 7 post-MVP) | Rate limiting, dedup ; KISS d'abord |
| Notifications | python-telegram-bot, aiosmtplib | Telegram temps réel, email fallback |
| Monitoring | Prometheus + Grafana | Métriques, dashboards, alertes |
| Logging | logging (JSON structuré) | Debug en prod |
| Tests | unittest | Bibliothèque standard, contract tests |
| Hosting | Infomaniak VPS Lite | Suisse, ~CHF 7/mois |

## État du projet

Side project en cours de construction. Ce qui existe aujourd'hui : les scrapers de
trois régies (Naef, Burger, Comptoir), le limiteur de débit, la déduplication, le
schéma PostgreSQL et la couche d'accès aux données. L'enrichissement LLM, le
matching, les notifications Telegram et le pipeline qui les relie sont décrits par
les [issues GitHub](https://github.com/Julien-hae/FlatPulse/issues) et pas encore
écrits : rien ne tourne de bout en bout.

## Documentation

| Question | Où |
|---|---|
| Quoi construire, dans quel ordre, avec quels tests | Les issues GitHub |
| Comment le système est architecturé | [`docs/architecture.md`](docs/architecture.md) |
| Comment scraper une régie précise | [`docs/spike-agencies.md`](docs/spike-agencies.md) |
| Ce que les scrapers extraient vraiment | [`docs/live-audit.md`](docs/live-audit.md) |

## Installation

Prérequis : [pyenv](https://github.com/pyenv/pyenv), [Poetry](https://python-poetry.org/docs/#installation)
et, pour la base locale, Docker.

```shell
make          # installe Python 3.14, l'environnement Poetry et les hooks pre-commit
make clean    # supprime l'environnement
```

## Commandes

```shell
python -m unittest discover tests/   # tests
coverage run && coverage xml         # tests + couverture (junittest.xml)
ruff format . && ruff check src/     # format + lint
mypy src/                            # typage strict
```

`pre-commit` enchaîne poetry-check, ruff (format + lint), mypy et les tests à chaque
commit ; la CI rejoue les mêmes étapes.

Les tests de `tests/integration/` qui ont besoin d'un PostgreSQL sont ignorés sans
`FLATPULSE_TEST_DATABASE_URL` (la CI la fournit). L'audit en direct des régies
(`FLATPULSE_LIVE=1`) interroge les vrais sites : voir `docs/architecture.md` §8.

## Base de données locale

```shell
cp .env.example .env        # puis renseigner POSTGRES_PASSWORD et DATABASE_URL
docker compose up -d        # PostgreSQL 16, schéma chargé depuis sql/schema.sql
```

L'application ne lit pas `.env` toute seule : `set -a; . ./.env; set +a` le charge dans
le shell.

## Configuration

Les variables d'environnement, leurs valeurs par défaut et celles qui sont
obligatoires sont décrites dans [`.env.example`](.env.example). La configuration est
validée au démarrage (`flatpulse.config.Config`) : une variable manquante ou invalide
arrête le programme avec un message qui la nomme.

## Licence

[MIT](LICENSE)
