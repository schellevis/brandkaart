# AGENTS.md

Deze instructies gelden voor de volledige repository.

## Projectdoel

Brandkaart is een Nederlandstalige, statische webkaart voor Europese
natuurbrandinformatie. Het product houdt verschillende informatietypen bewust
uit elkaar: satellietdetecties, bevestigde incidenten, brandgevaar, officiële
waarschuwingen en lokale maatregelen. Actualiteit, onzekerheid en bronuitval
moeten zichtbaar blijven; een ontbrekend resultaat mag nooit als bewijs van
veiligheid worden gepresenteerd.

De code en tests zijn de technische bron van waarheid. Houd dit bestand
zelfstandig bruikbaar en maak het niet afhankelijk van tijdelijke plannen,
reviews of gedateerde statusdocumenten.

## Begin altijd zo

1. Lees `git status --short` voordat je iets wijzigt.
2. Behoud bestaande en niet-gerelateerde wijzigingen; de worktree kan bewust
   vuil zijn.
3. Lees de relevante implementatie en tests voordat je een gedrag aanpast.
4. Houd de wijziging klein en doelgericht. Voer geen brede formattering of
   opportunistische refactor uit.
5. Gebruik geen destructieve Git-opdrachten, geschiedenisherschrijving of
   force-push
   zonder een expliciete opdracht van de gebruiker.

## Repository-indeling

- `pipeline/adapters/`: ophalen en normaliseren van externe brondata.
- `pipeline/common.py`: HTTP, tijdhulpen, foutredactie en `SourceResult`.
- `pipeline/schema.py`: recordmodel, verplichte velden en veld-allowlist.
- `pipeline/run.py`: orkestratie van adapters en volledige pipeline-run.
- `pipeline/artifact.py`: manifest, laagbestanden, fallback, staging en
  gecontroleerde artefactvervanging.
- `pipeline/checks.py`: controles op PII, secrets en artefactinhoud.
- `pipeline/restore.py`: ophalen van een eerder artefact voor fallback.
- `pipeline/geometry.py`, `pipeline/galicia_geometry.py` en
  `pipeline/meteoalarm_geometry.py`: vereenvoudiging en geometriekoppeling.
- `pipeline/raster.py`: omzetting van GeoTIFF/SLD naar compacte web-PNG's.
- `pipeline/places.py`: lokale plaatsnamenindex.
- `web/`: productiefrontend in HTML, CSS en vanilla JavaScript.
- `tests/`: netwerkloze Python- en JavaScript-regressietests.
- `assets/`: statische invoerassets voor pipeline en frontend.
- `.github/workflows/build.yml`: test-, build- en deployworkflow.
- `main.py`: ongebruikt scaffold; gebruik `python -m pipeline.run` als
  pipeline-entrypoint.
- `prototype/`: losstaande dummy-interface; niet de productiefrontend.
- `public/`: gegenereerde, genegeerde output. Bewerk of commit deze map niet.

## Kerninvarianten van de pipeline

- Bouw genormaliseerde records altijd met `schema.make_record(...)`. Voeg geen
  velden buiten `ALLOWED_FIELDS` toe en vul alle verplichte velden.
- Houd `source_attrs` klein, gestructureerd en adapterspecifiek. Neem geen ruwe
  payloads, contactgegevens of onbegrensde vrije tekst over.
- Een adapter retourneert een `SourceResult`. Een fout in een bron blijft bij
  die bron en mag andere bronnen niet laten uitvallen.
- Behandel een onvolledige, onleesbare of onverwachte bronrespons niet als een
  geldige lege meting. Laat de bron expliciet falen zodat fallback kan werken.
- Gebruik tijdzonebewuste datetimes en de hulpen uit `pipeline.common` voor
  UTC-normalisatie. Vergelijk geen naïeve en tijdzonebewuste datetimes.
- Niet-vertrouwde XML wordt uitsluitend met `defusedxml` geparsed.
- Credentials komen alleen uit de omgeving. Neem ze nooit op in code,
  fixtures, URLs in logs of foutmeldingen; laat foutpaden door `redact()` lopen.
- GeoJSON-coördinaten zijn `[lon, lat]`. CAP-polygonen komen als `lat,lon`
  binnen en moeten gevalideerd en omgedraaid worden.
- Houd gzip-output deterministisch (`mtime=0`) waar gelijke invoer gelijke
  uitvoer hoort te geven.
- Schrijf gepubliceerde data niet rechtstreeks. Laat `artifact.build()` eerst
  in staging schrijven, de volledige inhoud controleren en pas daarna de
  bestaande output vervangen.
- Behoud de zichtbare statussemantiek: onder andere `ok`, `ok_stale`,
  `stale_reused`, `failed` en `skipped_no_key` hebben verschillend gedrag.

## Adapters en nieuwe lagen

`pipeline.run.ADAPTERS` bevat de reguliere productieadapters. MeteoAlarm wordt
apart per land georkestreerd. Modules die niet in de runner zijn opgenomen,
worden niet stilzwijgend geactiveerd.

Bij het toevoegen of wijzigen van een bron controleer je samenhangend:

1. parser en normalisatie in de adapter;
2. het `SourceResult`-contract en foutgedrag;
3. schema-allowlist en beperkte `source_attrs`;
4. `artifact.LAYER_FILES`, manifestvelden en eventuele extra bestanden;
5. frontendnaam, loader, laag en statusweergave;
6. netwerkloze fixtures, parsertests, foutpaden en offline end-to-end-test.

Behoud bronspecifieke volledigheidscontroles. Een wijziging die meer records
toelaat, moet ook aantonen waarom corrupte of gedeeltelijke data niet als
succes wordt gezien.

## Frontend

- De productiefrontend gebruikt vanilla JavaScript en heeft geen bundler.
- Zet zuivere, DOM-onafhankelijke logica waar mogelijk in
  `web/app-helpers.js`. Houd de browser-global/CommonJS-wrapper intact zodat
  dezelfde functies met Node getest kunnen worden.
- Escape dynamische tekst met de bestaande HTML-helper. Laat dynamische links
  alleen via `safeUrl()` toe en gebruik bij nieuwe externe tabs
  `rel="noopener"`.
- Wis Leaflet-lagen voordat ze opnieuw gevuld worden; voorkom duplicaten na
  herladen of wisselen van dag/periode.
- Laad eerst `manifest.json` en daarna uitsluitend de daarin aanwezige
  laagbestanden. Behandel ontbrekende lagen defensief.
- Houd de Nederlandstalige interface, toetsenbordbediening, focusstijlen,
  labels en `aria`-attributen intact.
- Gebruik niet alleen kleur om informatietype, ernst of status over te brengen.
- Browserlocatie en plaatszoeken blijven client-side, tenzij een expliciete
  productwijziging inclusief tests iets anders vereist.

## Test- en kwaliteitsworkflow

Vereisten: Python 3.14+, `uv` en Node.js (de pytest-suite start ook een
`node --test`-run).

```bash
uv sync --frozen
uv run ruff check .
uv run pytest -q
node --test tests/frontend_helpers.test.js
```

Gebruik tijdens ontwikkeling eerst een gerichte test, bijvoorbeeld:

```bash
uv run pytest -q tests/test_artifact.py
uv run pytest -q tests/test_meteoalarm_warnings.py
uv run pytest -q tests/test_frontend.py
```

Testregels:

- Unit- en integratietests zijn netwerkloos. Monkeypatch de HTTP-functie van de
  betreffende adapter en gebruik minimale synthetische fixtures.
- Voeg bij een bug eerst of tegelijk een regressietest toe die het zichtbare
  gedrag of contract vastlegt.
- Test zowel succes als bronuitval, onvolledige respons, ongeldige geometrie,
  tijdzonegrenzen en fallback wanneer die voor de wijziging relevant zijn.
- Gebruik geen echte credentials, persoonlijke gegevens of onbewerkte live
  payloads in fixtures.
- Als dependencies veranderen, werk `uv.lock` mee bij en controleer daarna met
  `uv sync --frozen`.

De volledige pipeline gebruikt live netwerkbronnen en is geen vervanging voor
de netwerkloze suite. Draai haar alleen wanneer dat voor de taak nodig is:

```bash
uv run python -m pipeline.run --output public/data
cp -a web/. public/
cp assets/places.eu.json.gz public/data/places.eu.json.gz
uv run python -m http.server 8000 -d public
```

Herbouw statische assets alleen doelgericht via hun generator:

```bash
uv run python -m pipeline.geometry
uv run python -m pipeline.meteoalarm_geometry
uv run python -m pipeline.galicia_geometry
uv run python -m pipeline.places
```

## Stijl

- Volg de lokale stijl van het bestand. Een deel van de vroege adapters is
  bewust compact; formatteer die niet repo-breed als onderdeel van een fix.
- Ruff negeert daarom momenteel `E401`, `E701` en `E702`; introduceer niet
  onnodig meer uitzonderingen.
- Wijzig `web/vendor/` alleen bij een expliciete dependency-update.
- Gebruik duidelijke namen en type hints voor nieuwe publieke Python-functies.
- Schrijf opmerkingen voor niet-obvious redenen en invarianten, niet als
  vertaling van de volgende coderegel.
- Houd uitvoer reproduceerbaar en sortering expliciet wanneer volgorde deel van
  een artefact of testverwachting is.

## Klaarcriteria

Een wijziging is pas klaar wanneer:

- de relevante gerichte tests slagen;
- bij gedeelde pipeline-, schema-, artefact- of frontendwijzigingen de volledige
  pytest-suite slaagt;
- `uv run ruff check .` geen nieuwe problemen meldt;
- `git diff` alleen bedoelde wijzigingen toont;
- `public/`, caches en lokale uitvoer niet gestaged zijn;
- foutmeldingen, fixtures en artefacten geen credentials of PII bevatten;
- de overdracht kort vermeldt wat veranderde en welke controles zijn gedraaid.
