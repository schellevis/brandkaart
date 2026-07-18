"""Departementsgrenzen van Frankrijk: vereenvoudigen, opslaan en koppelen.

Bron: dataset "Archives de la Météo des forêts" op data.gouv.fr
(Licence Ouverte 2.0), resource "departements.geojson". Zie
assets/README.md voor de exacte bron-URL en licentievermelding.

De Météo des forêts-gevaarrecords (pipeline/adapters/meteo_forets.py)
komen zonder geometrie binnen; ze bevatten alleen source_attrs.num_dep
("01".."95", "2A", "2B"). Dit module levert de departementspolygonen als
compact, gevendord statisch bestand (assets/departements.simplified.geojson.gz)
en de logica om ze aan de records te koppelen.

Vereenvoudiging gebeurt met een pure-Python Douglas-Peucker-implementatie
(geen shapely of andere geo-bibliotheken), zodat het asset reproduceerbaar
is met alleen de standaardbibliotheek.
"""

from __future__ import annotations

import gzip
import json
import math
from pathlib import Path

from .common import http_get

DATASET_API = "https://www.data.gouv.fr/api/1/datasets/archives-de-la-meteo-des-forets/"
ATTRIBUTION = "Source : Météo-France / data.gouv.fr — Licence Ouverte 2.0"

# Vereenvoudigingstolerantie in graden (WGS84). Gekozen na experimenteren:
# houdt departementsvormen herkenbaar op een landelijke kaart en brengt het
# gz-bestand ruim onder de 300 kB-grens (zie assets/README.md).
DEFAULT_TOLERANCE = 0.003
MIN_RING_POINTS = 4
COORD_DECIMALS = 3

ASSET_PATH = Path(__file__).resolve().parent.parent / "assets" / "departements.simplified.geojson.gz"


def _perpendicular_distance(point: list[float], start: list[float], end: list[float]) -> float:
    """Loodrechte afstand van `point` tot de lijn `start`-`end`."""
    (x, y), (x1, y1), (x2, y2) = point, start, end
    dx, dy = x2 - x1, y2 - y1
    if dx == 0 and dy == 0:
        return math.hypot(x - x1, y - y1)
    t = ((x - x1) * dx + (y - y1) * dy) / (dx * dx + dy * dy)
    proj_x, proj_y = x1 + t * dx, y1 + t * dy
    return math.hypot(x - proj_x, y - proj_y)


def _douglas_peucker(points: list[list[float]], tolerance: float) -> list[list[float]]:
    """Klassieke Douglas-Peucker-lijnvereenvoudiging, recursief."""
    if len(points) < 3:
        return list(points)
    max_distance = 0.0
    max_index = 0
    for i in range(1, len(points) - 1):
        distance = _perpendicular_distance(points[i], points[0], points[-1])
        if distance > max_distance:
            max_distance = distance
            max_index = i
    if max_distance > tolerance:
        left = _douglas_peucker(points[: max_index + 1], tolerance)
        right = _douglas_peucker(points[max_index:], tolerance)
        return left[:-1] + right
    return [points[0], points[-1]]


def _simplify_ring(ring: list[list[float]], tolerance: float) -> list[list[float]] | None:
    """Vereenvoudig één ring (buiten- of gatring van een polygon).

    De ring blijft gesloten (eerste punt == laatste punt) en behoudt
    minimaal MIN_RING_POINTS punten; is dat na vereenvoudiging niet
    haalbaar, dan vervalt de ring (None).
    """
    simplified = _douglas_peucker(ring, tolerance)
    rounded = [[round(x, COORD_DECIMALS), round(y, COORD_DECIMALS)] for x, y in simplified]
    if rounded[0] != rounded[-1]:
        rounded.append(rounded[0])
    if len(rounded) < MIN_RING_POINTS:
        return None
    return rounded


def simplify_geometry(geometry: dict, tolerance: float) -> dict:
    """Vereenvoudig een Polygon- of MultiPolygon-geometrie.

    Elke ring wordt onafhankelijk vereenvoudigd met Douglas-Peucker en
    coördinaten worden afgerond op 3 decimalen (~honderd meter, ruim
    voldoende voor een landelijke overzichtskaart). Ringen die na
    vereenvoudiging ontaarden (minder dan 4 punten) vervallen; een
    polygon zonder overgebleven buitenring vervalt geheel.
    """
    geometry_type = geometry.get("type")
    if geometry_type == "Polygon":
        rings = _simplify_polygon_rings(geometry["coordinates"], tolerance)
        if not rings:
            return {"type": "Polygon", "coordinates": []}
        return {"type": "Polygon", "coordinates": rings}
    if geometry_type == "MultiPolygon":
        polygons = []
        for polygon in geometry["coordinates"]:
            rings = _simplify_polygon_rings(polygon, tolerance)
            if rings:
                polygons.append(rings)
        return {"type": "MultiPolygon", "coordinates": polygons}
    raise ValueError(f"onbekend of niet-ondersteund geometrietype: {geometry_type}")


def _simplify_polygon_rings(
    rings: list[list[list[float]]], tolerance: float
) -> list[list[list[float]]]:
    """Vereenvoudig de ringen van één polygon (buitenring + eventuele gaten).

    Een polygon zonder (overgebleven) buitenring wordt overgeslagen: de
    buitenring is altijd het eerste element in GeoJSON-polygoncoördinaten.
    """
    if not rings:
        return []
    outer = _simplify_ring(rings[0], tolerance)
    if outer is None:
        return []
    simplified = [outer]
    for hole in rings[1:]:
        simplified_hole = _simplify_ring(hole, tolerance)
        if simplified_hole is not None:
            simplified.append(simplified_hole)
    return simplified


def build_departements_asset(target_path: str | Path, tolerance: float = DEFAULT_TOLERANCE) -> dict:
    """Download de bron-GeoJSON, vereenvoudig en schrijf het asset.

    Bewaart per feature alleen `num_dep` en `nom` als properties (geen
    overige bronvelden). Retourneert een klein rapport met aantallen en
    groottes, zodat de keuze van de tolerantie navolgbaar is.
    """
    source_url = _resolve_source_url()
    raw_source = http_get(source_url)
    source_geojson = json.loads(raw_source.decode("utf-8"))

    features_out = []
    for feature in source_geojson["features"]:
        properties = feature.get("properties", {})
        num_dep = str(properties.get("code") or properties.get("num_dep") or "").strip()
        nom = str(properties.get("nom") or "").strip()
        geometry = simplify_geometry(feature["geometry"], tolerance)
        if not geometry["coordinates"]:
            continue
        features_out.append(
            {
                "type": "Feature",
                "geometry": geometry,
                "properties": {"num_dep": num_dep, "nom": nom},
            }
        )

    target_feature_collection = {"type": "FeatureCollection", "features": features_out}
    encoded = json.dumps(target_feature_collection, separators=(",", ":"), ensure_ascii=False).encode(
        "utf-8"
    )
    compressed = gzip.compress(encoded, mtime=0)

    target_path = Path(target_path)
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_bytes(compressed)

    return {
        "source_url": source_url,
        "tolerance": tolerance,
        "feature_count": len(features_out),
        "bytes_source": len(raw_source),
        "bytes_simplified_json": len(encoded),
        "bytes_gzip": len(compressed),
        "target_path": str(target_path),
    }


def _resolve_source_url() -> str:
    """Vind de departements-GeoJSON-resource in de data.gouv.fr-dataset."""
    from .common import http_get_json

    dataset = http_get_json(DATASET_API)
    candidates = [
        resource
        for resource in dataset.get("resources", [])
        if (resource.get("format") or "").lower() == "geojson"
        and "departement" in (resource.get("title") or "").lower()
    ]
    if not candidates:
        raise ValueError("geen departements-GeoJSON-resource gevonden in de dataset")
    return candidates[0]["url"]


def load_departements(path: str | Path = ASSET_PATH) -> dict[str, dict]:
    """Laad het asset en geef num_dep -> geometry terug."""
    path = Path(path)
    compressed = path.read_bytes()
    data = json.loads(gzip.decompress(compressed).decode("utf-8"))
    result = {}
    for feature in data["features"]:
        num_dep = feature["properties"]["num_dep"]
        result[num_dep] = feature["geometry"]
    return result


def attach_geometry(records: list[dict], departements: dict[str, dict]) -> tuple[int, int]:
    """Zet geometry op records met een bekende source_attrs.num_dep.

    Records worden nooit verwijderd; alleen `geometry` wordt gezet als er
    een departementsgeometrie beschikbaar is. Retourneert (gekoppeld,
    niet-gekoppeld).
    """
    matched = 0
    unmatched = 0
    for record in records:
        num_dep = (record.get("source_attrs") or {}).get("num_dep")
        geometry = departements.get(num_dep) if num_dep is not None else None
        if geometry is not None:
            record["geometry"] = geometry
            matched += 1
        else:
            unmatched += 1
    return matched, unmatched


if __name__ == "__main__":
    report = build_departements_asset(ASSET_PATH)
    print(json.dumps(report, indent=2, ensure_ascii=False))
