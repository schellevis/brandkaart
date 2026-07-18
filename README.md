# Brandkaart Europa

Concept voor een publieksgerichte kaart met natuurbranddetecties, brandgevaar, officiële waarschuwingen en lokale maatregelen in Europa. De eerste regionale verdieping richt zich op Frankrijk en Spanje.

De productieversie is volledig statisch: GitHub Actions haalt de brondata elk uur op, bouwt een gecontroleerd artefact zonder secrets of PII en publiceert dit via GitHub Pages.

- [Klikbare dummy-mockup](prototype/README.md)

De mockup starten:

```bash
uv run python -m http.server 8000 -d prototype
```

Open daarna `http://localhost:8000`.

> De prototypekaart bevat uitsluitend fictieve incidenten en waarschuwingen. Er zijn nog geen live databronnen aangesloten.

## Dataprototype

`pipeline/` bevat het handmatig uitvoerbare dataprototype dat dezelfde stappen gebruikt als de GitHub Action die elk uur draait: bronnen ophalen, normaliseren via een veld-allowlist, valideren (PII, secrets, versheid, plausibiliteit) en een statisch artefact met `manifest.json` schrijven naar `public/data/`.

```bash
uv run python -m pipeline.run   # artefact bouwen
uv run pytest                   # tests
```

Bronnen: NASA FIRMS (vereist `FIRMS_MAP_KEY` als omgevingsvariabele, anders overgeslagen), Météo des forêts, AEMET-waarschuwingen, AEMET-brandgevaar en CEMS Rapid Mapping. Een falende bron blokkeert de andere bronnen niet; een PII- of secretovertreding blokkeert de volledige publicatie. De gegenereerde data wordt niet gecommit.

## Productiefrontend lokaal testen

De productiefrontend staat in `web/`. Leaflet en markercluster zijn lokaal
gevendord; alleen OpenStreetMap-rastertegels worden tijdens gebruik extern
opgehaald.

```bash
uv run python -m pipeline.run --output public/data
cp -a web/. public/
cp assets/places.eu.json.gz public/data/places.eu.json.gz
uv run python -m http.server 8000 -d public
```

Open `http://localhost:8000`. De `.gz`-data wordt client-side met
`DecompressionStream` uitgepakt, omdat GitHub Pages geen `Content-Encoding:
gzip` meestuurt. De pipeline waarschuwt als het totale artefact groter wordt
dan de afgesproken grens van 5 MB.
