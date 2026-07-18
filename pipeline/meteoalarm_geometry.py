"""Geometrie voor MeteoAlarm-waarschuwingen: CAP-polygoonconversie en join.

CAP-polygonen staan als 'lat,lon'-paren (spatiegescheiden); GeoJSON wil
'lon,lat'. Zonecode-joins gebruiken statische assets (zie Phase 0).
"""

from __future__ import annotations

import gzip
import json
from pathlib import Path

from .common import http_get
from .geometry import simplify_geometry

# --- Bronnen voor de statische zone-assets (Phase 0) --------------------------
# EMMA_ID-zonepolygonen: MeteoAlarm awareness areas, herverpakt in het
# MIT-gelicentieerde pakket NiklasJordan/meteoalarm (CRS84 = WGS84 lon,lat).
EMMA_SOURCE_URL = (
    "https://raw.githubusercontent.com/NiklasJordan/meteoalarm/main/"
    "src/meteoalarm/assets/geocodes.json"
)
EMMA_ATTRIBUTION = "MeteoAlarm awareness areas via NiklasJordan/meteoalarm (MIT)"
# CH gebruikt inline CAP-polygonen; FR gebruikt NUTS3 in de feed. De overige
# landen keyen op EMMA_ID.
EMMA_COUNTRIES = ("NL", "BE", "LU", "DE", "AT", "IT", "FR")
EMMA_TOLERANCE = 0.008

# NUTS-geometrie: Eurostat GISCO. De MeteoAlarm-feeds gebruiken de NUTS 2013
# vintage (geverifieerd: FR713/FR826 bestaan alleen in 2013). 20M-resolutie,
# EPSG:4326.
NUTS_VINTAGE = "2013"
NUTS_SOURCE_URL = (
    "https://gisco-services.ec.europa.eu/distribution/v2/nuts/geojson/"
    f"NUTS_RG_20M_{NUTS_VINTAGE}_4326.geojson"
)
NUTS_ATTRIBUTION = "© EuroGeographics for the administrative boundaries (Eurostat GISCO, NUTS 2013)"
NUTS_COUNTRIES = ("NL", "BE", "LU", "DE", "AT", "IT", "FR")
NUTS_TOLERANCE = 0.008

ASSETS_DIR = Path(__file__).resolve().parent.parent / "assets"
EMMA_ASSET_PATH = ASSETS_DIR / "meteoalarm-zones.simplified.geojson.gz"
NUTS_ASSET_PATH = ASSETS_DIR / f"nuts-{NUTS_VINTAGE}.simplified.geojson.gz"


def convert_cap_polygon(text: str) -> list[list[float]] | None:
    ring: list[list[float]] = []
    for pair in text.split():
        parts = pair.split(",")
        if len(parts) != 2:
            return None
        try:
            lat, lon = float(parts[0]), float(parts[1])
        except ValueError:
            return None
        if not (-90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0):
            return None
        ring.append([lon, lat])
    unique = {tuple(p) for p in ring}
    if len(unique) < 3:
        return None
    if ring[0] != ring[-1]:
        ring.append(ring[0])
    return ring


def polygons_to_geometry(polygons: list[str]) -> dict | None:
    rings = [r for r in (convert_cap_polygon(p) for p in polygons) if r is not None]
    if not rings:
        return None
    if len(rings) == 1:
        return {"type": "Polygon", "coordinates": [rings[0]]}
    return {"type": "MultiPolygon", "coordinates": [[r] for r in rings]}


def load_zone_asset(path: str | Path, key: str) -> dict[str, dict]:
    data = json.loads(gzip.decompress(Path(path).read_bytes()).decode("utf-8"))
    result: dict[str, dict] = {}
    for feature in data["features"]:
        code = feature["properties"].get(key)
        if code:
            result[code] = feature["geometry"]
    return result


def attach_geometry(
    records: list[dict],
    emma_zones: dict[str, dict],
    nuts_zones: dict[str, dict],
    polygons_by_id: dict[str, list[str]] | None = None,
) -> tuple[list[dict], int]:
    kept: list[dict] = []
    skipped = 0
    for record in records:
        geometry = None
        polygons = (polygons_by_id or {}).get(record["id"], [])
        if polygons:
            geometry = polygons_to_geometry(polygons)
        if geometry is None:
            zone = (record.get("source_attrs") or {}).get("zone", "")
            if zone.startswith("EMMA_ID:"):
                geometry = emma_zones.get(zone.split(":", 1)[1])
            elif zone.startswith("NUTS:"):
                geometry = nuts_zones.get(zone.split(":", 1)[1])
        if geometry is None:
            skipped += 1
            continue
        record["geometry"] = geometry
        kept.append(record)
    return kept, skipped


# --- Assetbouw (Phase 0; reproduceerbaar, alleen stdlib + eigen simplify) -----

def _write_asset(features: list[dict], target_path: str | Path) -> dict:
    """Schrijf een FeatureCollection als gevendord gz en rapporteer groottes."""
    collection = {"type": "FeatureCollection", "features": features}
    encoded = json.dumps(collection, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    compressed = gzip.compress(encoded, mtime=0)
    target_path = Path(target_path)
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_bytes(compressed)
    return {
        "target_path": str(target_path),
        "feature_count": len(features),
        "bytes_simplified_json": len(encoded),
        "bytes_gzip": len(compressed),
    }


def build_emma_asset(
    target_path: str | Path = EMMA_ASSET_PATH,
    countries: tuple[str, ...] = EMMA_COUNTRIES,
    tolerance: float = EMMA_TOLERANCE,
) -> dict:
    """Download de EMMA-zonebron, filter op landen, vereenvoudig en schrijf.

    Properties per feature: alleen `emma_id` (de zonecode). Geometrie is al
    WGS84 (CRS84). Retourneert een rapport met bron, aantallen en groottes.
    """
    data = json.loads(http_get(EMMA_SOURCE_URL).decode("utf-8"))
    features_out: list[dict] = []
    for feature in data["features"]:
        props = feature.get("properties") or {}
        if props.get("type") != "EMMA_ID" or props.get("country") not in countries:
            continue
        geometry = simplify_geometry(feature["geometry"], tolerance)
        if not geometry["coordinates"]:
            continue
        features_out.append(
            {"type": "Feature", "geometry": geometry, "properties": {"emma_id": props["code"]}}
        )
    report = _write_asset(features_out, target_path)
    report.update({"source_url": EMMA_SOURCE_URL, "attribution": EMMA_ATTRIBUTION,
                   "tolerance": tolerance})
    return report


def build_nuts_asset(
    target_path: str | Path = NUTS_ASSET_PATH,
    countries: tuple[str, ...] = NUTS_COUNTRIES,
    tolerance: float = NUTS_TOLERANCE,
) -> dict:
    """Download de Eurostat GISCO NUTS-set (2013), filter op landen, schrijf.

    Alle NUTS-niveaus van de gekozen landen worden bewaard (de feeds gebruiken
    NUTS3 voor FR en NUTS2 voor BE). Properties per feature: alleen `nuts_code`.
    """
    data = json.loads(http_get(NUTS_SOURCE_URL).decode("utf-8"))
    features_out: list[dict] = []
    for feature in data["features"]:
        props = feature.get("properties") or {}
        if props.get("CNTR_CODE") not in countries:
            continue
        geometry = simplify_geometry(feature["geometry"], tolerance)
        if not geometry["coordinates"]:
            continue
        features_out.append(
            {"type": "Feature", "geometry": geometry,
             "properties": {"nuts_code": props["NUTS_ID"]}}
        )
    report = _write_asset(features_out, target_path)
    report.update({"source_url": NUTS_SOURCE_URL, "attribution": NUTS_ATTRIBUTION,
                   "vintage": NUTS_VINTAGE, "tolerance": tolerance})
    return report


if __name__ == "__main__":
    for report in (build_emma_asset(), build_nuts_asset()):
        print(json.dumps(report, indent=2, ensure_ascii=False))
