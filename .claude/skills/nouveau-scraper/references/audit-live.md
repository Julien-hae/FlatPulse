# Enregistrer la source et l'auditer en direct

Les tests prouvent que le scraper lit bien dix cas choisis. L'audit en direct dit ce
qu'il extrait **de toute l'offre** : annonces rejetées, libellés inconnus, champs jamais
remplis. Une régie n'est pas en service tant qu'il n'a pas tourné.

## Où une source s'enregistre

Il n'y a pas encore de registre unique. Aujourd'hui, la source s'ajoute dans
`tests/integration/test_live_sources.py` :

- `SCRAPER_CLASSES` : la classe ;
- `RATE_LIMITS_RPM` : son `slug` et le débit **du spike** — pas une valeur ronde. Mettre
  à jour le commentaire au-dessus s'il cite la raison d'un débit (Crawl-delay) ;
- `MIN_FILL_RATE` : ses seuils, après le premier run (plus bas).

Si `sql/sources.sql` existe (story #147, le seed de la table `sources`), y ajouter la
ligne de la régie — `slug`, nom, `base_url`, `scraper_class`, `poll_interval_s`,
`rate_limit_rpm` — avec les mêmes valeurs : le pipeline ne connaît que ce seed, et
`RATE_LIMITS_RPM` doit rester aligné sur lui. `scripts/check_scraper.py` vérifie les
deux endroits.

## Lancer l'audit sur la seule régie

L'audit complet interroge toutes les régies pendant plus d'une heure. Pour une source
nouvelle, c'est du trafic que les autres n'ont pas demandé :

```bash
FLATPULSE_LIVE=1 python .claude/skills/nouveau-scraper/scripts/audit_source.py <slug> \
    2> live-<slug>-requetes.log | tee live-<slug>-rapport.log
```

Le script lit le débit dans `RATE_LIMITS_RPM` (d'où l'enregistrement d'abord), télécharge
l'annuaire swisstopo, fait un poll complet, et imprime : volume, canton inconnu,
annonces ignorées, répartition par type et canton, taux de remplissage par type et
champ, puis l'entrée `MIN_FILL_RATE` proposée. Le rapport sort sur stdout ; chaque
requête et chaque WARNING du scraper vont sur stderr. Les deux fichiers sont en `.log`,
que git ignore : ce qui se garde va dans `docs/live-audit.md`.

Durée d'un `FicheScraper` : `(index + fiches) × 60 / rpm`. À 6 rpm, 150 fiches font
25 minutes : le lancer en arrière-plan et ne pas le relancer pour voir. **Un run, pas
une boucle** — c'est le site de la régie.

Si le réseau de la session n'atteint pas la régie ou swisstopo, l'audit n'a pas eu
lieu : l'écrire dans le résumé et laisser `MIN_FILL_RATE` sans la source. Ne rien
estimer.

## Lire le résultat

Dans cet ordre, parce que chaque ligne peut renvoyer à l'étape 4 du skill :

1. **Annonces ignorées comme invalides** — doit être 0. Chaque message nomme le champ et
   l'URL. Ouvrir la fiche : c'est un cas que la fixture n'avait pas (titre vide, loyer à
   `CHF 0.-`, URL relative). Le figer, écrire son test rouge, corriger, relancer une fois.
2. **WARNING du fichier des requêtes** : `Unknown property type label`, `Unknown canton name`,
   `Unknown postal code`, lignes hors grammaire. Même traitement ; un libellé nouveau
   s'ajoute à `utils.py` avec son test.
3. **Annonces sans `property_type`, canton inconnu** : zéro attendu si la source publie
   de quoi les établir.
4. **Taux de remplissage.** Un taux bas n'est pas un bug tant qu'il n'est pas vérifié
   sur le site (règle de `docs/live-audit.md`) :
   - la donnée est publiée et le scraper la manque → cas de fixture, test, correction ;
   - la régie ne la publie pas → le noter dans le run et dans l'entrée du spike
     (« non publié »), sans issue ;
   - sans objet pour le type (pièces d'un parking, surface d'une place) → rien à faire.
5. **Volume** : le comparer à celui du spike. Un écart net (la moitié des fiches) veut
   dire une pagination incomplète ou un index partiel.

## Poser les seuils

Coller l'entrée proposée dans `MIN_FILL_RATE`. La règle, écrite au-dessus du
dictionnaire, est celle que le script applique : la mesure du run moins 10 points,
arrondie à 5 % en dessous, pour les types d'au moins 20 annonces et les taux qui
restent au-dessus de 0. Un champ sans seuil (non publié, sans objet) reste dans le
rapport.

Un seuil qu'on écarte de la proposition se justifie en commentaire, comme un
`# type: ignore`. Mettre à jour le commentaire de date au-dessus de `MIN_FILL_RATE` s'il
ne couvre plus toutes les sources (« Fill rates of the run of … »).

## Consigner le run

Dans `docs/live-audit.md`, une section en tête, sur le modèle des précédentes :

```markdown
## Run du JJ.MM.AAAA, HH:MM UTC — <slug> seul (première mise en service)

- Code : branche / story #N
- Durée : … s à … rpm
- Résultat : 0 annonce ignorée | N ignorées (causes ci-dessous)
- Volume : N annonces, dont G à Genève ; canton inconnu : 0

### <Régie> — répartition et taux de remplissage

| Type | GE | VD | … | Total |
|---|---:|---:|---:|---:|

| Type | n | `price_chf` | `surface_m2` | `nb_rooms` | `postal_code` | `images` |
|---|---:|---:|---:|---:|---:|---:|

### Constats vérifiés sur le site

| Constat | Cause | Suite |
|---|---|---|

### Taux bas, non investigués
```

Reporter aussi dans l'entrée du spike le volume du jour et le débit confirmé (ou
abaissé) par ce premier poll complet.

## Après la mise en service

L'audit complet (`FLATPULSE_LIVE=1 python -m unittest -v
tests.integration.test_live_sources`) inclut désormais la régie et fera échouer un run
si elle passe sous ses seuils, perd un type ou rejette une annonce. C'est le filet qui
dira qu'elle a changé son site.
