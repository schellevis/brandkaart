# Brandkaart klikbare mockup

Deze mockup gebruikt uitsluitend fictieve branden, risicozones, waarschuwingen en maatregelen. Alleen de OpenStreetMap-achtergrond is echt.

Start lokaal vanuit de projectmap:

```bash
uv run python -m http.server 8000 -d prototype
```

Open daarna `http://localhost:8000`.

Probeer onder andere:

- zoeken naar Collioure, Marseille, Valencia, Málaga of Girona;
- kaartlagen aan- en uitzetten;
- klikken op een satellietdetectie;
- wisselen tussen Nu, 24 uur, 48 uur en 7 dagen;
- de responsieve mobiele weergave.

De mockup laadt Leaflet, lettertypen en OpenStreetMap-kaarttegels via internet. Hij bevat nog geen koppelingen met EFFIS, FIRMS, MeteoAlarm, Météo-France of AEMET.
