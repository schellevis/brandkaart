# Gevendorde kaartassets

## Europese plaatsnamen

`places.eu.json.gz` is een subset van GeoNames `cities5000`, gefilterd op
lon -25..45 en lat 27..72 en aflopend gesorteerd op inwonertal. Zoeken blijft
hierdoor volledig lokaal. Opnieuw bouwen: `uv run python -m pipeline.places`.

Attributie: **Plaatsnamen: GeoNames (geonames.org), CC BY 4.0**.

## Galicische gemeentegrenzen

`galicia-municipios.simplified.geojson.gz` bevat exact 313 vereenvoudigde
gemeentepolygonen met uitsluitend `municipality_code` en `name`. Bron is de
officiële laag “Concellos (Febreiro 2026)”, laag 16 van de Xunta-service
`LimitesAdministrativos/LimitesAdministrativos`, opgevraagd als GeoJSON in
EPSG:4326. Dataset: Instituto de Estudos do Territorio, Xunta de Galicia;
licentie **CC BY-SA 4.0**. Attributie: “Fonte: Instituto de Estudos do
Territorio, Xunta de Galicia — CC BY-SA 4.0”.

Opnieuw bouwen: `uv run python -m pipeline.galicia_geometry`. De geometrie
wordt met 0,002° tolerantie vereenvoudigd en op drie decimalen afgerond. Het
huidige asset is circa 60 KiB gzip.

## Certificaatketen Xunta Medio Rural

`certs/globalsign-rsa-ov-ssl-ca-2018.pem` is de officiële GlobalSign
tussencertificaat-CA uit de AIA-verwijzing van `mediorural.xunta.gal`
(SHA-256 `B6:76:FF:A3:17:9E:88:12:09:3A:1B:5E:AF:EE:87:6A:E7:A6:AA:F2:31:07:8D:AD:1B:FB:21:CD:28:93:76:4A`, geldig tot 21 november 2028).
De server leverde deze tussenschakel tijdens ontwikkeling niet mee. De IRDI-
adapter voegt hem toe aan de normale systeem-CA's; certificaat- en
hostnameverificatie blijven verplicht. Er wordt nergens `verify=False`, `-k`
of een generieke uitschakeling van TLS-verificatie gebruikt.

## assets/departements.simplified.geojson.gz

Vereenvoudigde polygonen van de Franse departementen (métropole + Corsica),
gebruikt om de Météo des forêts-gevaarrecords (die zonder geometrie
binnenkomen, alleen `source_attrs.num_dep`) te koppelen aan een kaartvorm.

## Herkomst

- Dataset: "Archives de la Météo des forêts" op data.gouv.fr
  (https://www.data.gouv.fr/api/1/datasets/archives-de-la-meteo-des-forets/)
- Resource: `departements.geojson` (format geojson), ontdekt via de
  dataset-API op de resource met titel "departements.geojson".
  Bron-URL op moment van generatie:
  https://static.data.gouv.fr/resources/archive-meteo-des-forets/20251218-123448/departements.geojson
- Uitgever: Météo-France / data.gouv.fr
- Licentie: Licence Ouverte 2.0 (Etalab)
- Attributie: "Source : Météo-France / data.gouv.fr — Licence Ouverte 2.0"
- Properties in de bron: `code` (departementcode, bv. "01", "2A") en
  `nom` (departementnaam). In het asset overgenomen als `num_dep` en `nom`.

## Generatie

Gegenereerd op 15 juli 2026 met:

```
uv run python -m pipeline.geometry
```

Dit voert `pipeline.geometry.build_departements_asset` uit, die de
bron-GeoJSON opnieuw downloadt, vereenvoudigt met een pure-Python
Douglas-Peucker-implementatie (tolerantie 0.003 graden, coördinaten
afgerond op 3 decimalen) en het resultaat als gzip-JSON wegschrijft naar
`assets/departements.simplified.geojson.gz`.

Gekozen tolerantie: **0.003 graden**. Bij deze tolerantie blijven de
departementsvormen (inclusief kustlijnen en Corsica) herkenbaar op een
landelijke overzichtskaart, terwijl het bestand ruim onder de
300 kB-grens blijft.

Groottes bij de laatste generatie:

| | bytes |
|---|---|
| bron-GeoJSON (ongecomprimeerd) | 1.079.714 |
| vereenvoudigde JSON (ongecomprimeerd) | 374.191 |
| vereenvoudigde JSON (gzip) | 112.417 |

Aantal features: 96 (Frankrijk métropolitaine inclusief Corsica als
aparte departementen "2A" en "2B").

Herregenereren (bv. bij een nieuwe bronversie of andere tolerantie) kan
door bovenstaand commando opnieuw te draaien; het bestand wordt dan
overschreven.

## MeteoAlarm-zonegeometrie (EMMA_ID en NUTS)

Twee assets koppelen de MeteoAlarm-waarschuwingen (die zonder polygoon
binnenkomen — zie `pipeline/adapters/meteoalarm_warnings.py`) aan een
kaartvorm. Zwitserland levert inline CAP-polygonen en heeft geen asset nodig.

Beide worden gegenereerd met:

```
uv run python -m pipeline.meteoalarm_geometry
```

Dit draait `build_emma_asset` en `build_nuts_asset`, die de bronnen opnieuw
downloaden, per land filteren, vereenvoudigen met dezelfde pure-Python
Douglas-Peucker (tolerantie **0.008 graden**, coördinaten op 3 decimalen) en
als gzip-JSON wegschrijven. Landen: NL, BE, LU, DE, AT, IT, FR.

### `assets/meteoalarm-zones.simplified.geojson.gz`

- Inhoud: EMMA_ID-zonepolygonen, property uitsluitend `emma_id`.
- Bron: MeteoAlarm awareness areas, herverpakt in het pakket
  `NiklasJordan/meteoalarm`, bestand `src/meteoalarm/assets/geocodes.json`
  (https://raw.githubusercontent.com/NiklasJordan/meteoalarm/main/src/meteoalarm/assets/geocodes.json).
- Bron-CRS: CRS84 (WGS84 lon,lat) — geen herprojectie nodig.
- Licentie: **MIT**. Attributie: "MeteoAlarm awareness areas via
  NiklasJordan/meteoalarm (MIT)".
- Generatie 17 juli 2026: **684 features, 74 KB gzip** (318 KB JSON).
  Dekking per land: DE 410, AT 126, FR 98, IT 20, NL 20, BE 10, LU 2.
  (FR-waarschuwingen keyen in de feed op NUTS3, niet op EMMA_ID; de FR-EMMA-
  zones zijn dus doorgaans ongebruikt maar meegenomen voor volledigheid.)

### `assets/nuts-2013.simplified.geojson.gz`

- Inhoud: NUTS-polygonen (alle niveaus) van de zeven landen, property
  uitsluitend `nuts_code`.
- Bron: Eurostat GISCO, `NUTS_RG_20M_2013_4326.geojson`
  (https://gisco-services.ec.europa.eu/distribution/v2/nuts/geojson/NUTS_RG_20M_2013_4326.geojson).
- **Vintage: NUTS 2013** — empirisch vastgesteld: de live Franse feed gebruikt
  codes als `FR713`/`FR826` die alleen in de 2013-vintage bestaan (in 2016+
  hernummerd). België gebruikt NUTS2 (`BE35`), stabiel over vintages.
- Bron-CRS: EPSG:4326. Licentie: EuroGeographics / Eurostat GISCO.
  Attributie: "© EuroGeographics for the administrative boundaries
  (Eurostat GISCO, NUTS 2013)".
- Generatie 17 juli 2026: **900 features, 58 KB gzip** (431 KB JSON).

Bij een nieuwe brondversie of andere tolerantie: bovenstaand commando opnieuw
draaien. Wijzigt MeteoAlarm ooit van vintage, pas dan `NUTS_VINTAGE` in
`pipeline/meteoalarm_geometry.py` aan en verifieer opnieuw tegen de live codes.
