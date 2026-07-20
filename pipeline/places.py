"""Bouw de lokale Europese plaatsnamenindex uit GeoNames cities5000."""
from __future__ import annotations
import argparse, csv, gzip, io, json, urllib.request, zipfile
from datetime import datetime, timezone
from pathlib import Path

URL = "https://download.geonames.org/export/dump/cities5000.zip"
ATTRIBUTION = "Plaatsnamen: GeoNames (geonames.org), CC BY 4.0"
BOUNDS = (-25.0, 27.0, 45.0, 72.0)

# Landen waarvoor plaatsnamen worden opgenomen: de EU-27, het Verenigd
# Koninkrijk en Zwitserland. De bounding box hierboven houdt daarnaast
# overzeese gebieden (bijv. Guadeloupe, Réunion, Canarische Azoren) buiten de
# Europese scope. Beide filters worden gecombineerd toegepast.
COUNTRIES = frozenset({
    "AT", "BE", "BG", "HR", "CY", "CZ", "DK", "EE", "FI", "FR", "DE", "GR",
    "HU", "IE", "IT", "LV", "LT", "LU", "MT", "NL", "PL", "PT", "RO", "SK",
    "SI", "ES", "SE",  # EU-27
    "GB",  # Verenigd Koninkrijk
    "CH",  # Zwitserland
})

def parse_cities(text: str) -> list[list]:
    places = []
    for row in csv.reader(io.StringIO(text), delimiter="\t"):
        if len(row) < 15: continue
        try: lat, lon, population = float(row[4]), float(row[5]), int(row[14] or 0)
        except ValueError: continue
        west, south, east, north = BOUNDS
        if row[8] in COUNTRIES and west <= lon <= east and south <= lat <= north:
            places.append([row[1], row[8], lat, lon, population])
    places.sort(key=lambda p: (-p[4], p[0].casefold(), p[1]))
    return places

def build_payload(zip_bytes: bytes, generated: str | None = None) -> dict:
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as archive:
        name = next(name for name in archive.namelist() if name.endswith(".txt"))
        places = parse_cities(archive.read(name).decode("utf-8"))
    return {"attribution": ATTRIBUTION, "generated": generated or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "places": places}

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument("--output", type=Path, default=Path("assets/places.eu.json.gz")); args = parser.parse_args(argv)
    request = urllib.request.Request(URL, headers={"User-Agent": "Brandkaart/0.1"})
    with urllib.request.urlopen(request, timeout=120) as response: payload = build_payload(response.read())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode()
    with args.output.open("wb") as output:
        with gzip.GzipFile(filename="", mode="wb", fileobj=output, mtime=0) as handle: handle.write(encoded)
    print(f"{len(payload['places'])} plaatsen geschreven naar {args.output}"); return 0

if __name__ == "__main__": raise SystemExit(main())
