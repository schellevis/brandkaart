"""Pan-Europees brandgevaar via de officiële EFFIS WMS-laag.

EFFIS publiceert de geharmoniseerde Fire Weather Index (FWI) als standaard
WMS. We nemen D+0 t/m D+2 als transparante PNG plus compacte metadata op.
Alle verwachte dagen moeten leesbaar zijn; een gedeeltelijke respons is een
bronfout zodat artefactfallback de vorige complete set kan hergebruiken.
"""

from __future__ import annotations

import json
import math
import struct
from datetime import datetime, time, timedelta, timezone
from urllib.parse import urlencode

from ..common import SourceResult, http_get, iso, utcnow
from ..schema import make_record

WMS_URL = "https://maps.effis.emergency.copernicus.eu/effis"
PAGE_URL = "https://forest-fire.emergency.copernicus.eu/about-effis/technical-background/fire-danger-forecast"
ATTRIBUTION = "© European Union, Copernicus Emergency Management Service (EFFIS)"
LAYER = "mf010.fwi"
BBOX = {"west": -25.0, "south": 25.0, "east": 50.0, "north": 72.0}
EARTH_RADIUS_M = 6_378_137.0
PROJECTED_BBOX = {
    "west": EARTH_RADIUS_M * math.radians(BBOX["west"]),
    "south": EARTH_RADIUS_M * math.log(math.tan(math.pi / 4 + math.radians(BBOX["south"]) / 2)),
    "east": EARTH_RADIUS_M * math.radians(BBOX["east"]),
    "north": EARTH_RADIUS_M * math.log(math.tan(math.pi / 4 + math.radians(BBOX["north"]) / 2)),
}
WIDTH = 1200
HEIGHT = 752
MAX_DAY_OFFSET = 2

# Officiële kleuren uit de actuele mf010.fwi-WMS-stijl. De volgorde volgt de
# zes geharmoniseerde EFFIS-klassen uit de technische documentatie.
CLASSES = {
    1: {"color": "#9cffc0", "label": "laag"},
    2: {"color": "#cde24e", "label": "matig"},
    3: {"color": "#e6ac00", "label": "hoog"},
    4: {"color": "#d97010", "label": "zeer hoog"},
    5: {"color": "#ad060e", "label": "extreem"},
    6: {"color": "#3a0015", "label": "zeer extreem"},
}


def fetch() -> SourceResult:
    result = SourceResult(
        source="effis_danger", attribution=ATTRIBUTION, source_url=PAGE_URL
    )
    now = utcnow()
    fetched_at = iso(now)
    today = now.date()
    records: list[dict] = []

    for day_offset in range(MAX_DAY_OFFSET + 1):
        target = today + timedelta(days=day_offset)
        try:
            png = http_get(_map_url(target), timeout=60, retries=2)
            _validate_png(png)
        except Exception as exc:  # noqa: BLE001 — onvolledige bronset faalt als geheel
            return result.fail(f"EFFIS D+{day_offset} ophalen/valideren mislukt: {exc}")

        stem = f"danger/eu/effis/fwi-{target.isoformat()}"
        meta = {
            "name": f"EFFIS FWI {target.isoformat()}",
            "provider": "EFFIS",
            "bounds": BBOX,
            "projected_bounds": PROJECTED_BBOX,
            "width": WIDTH,
            "height": HEIGHT,
            "crs": "EPSG:3857",
            "classes": CLASSES,
            "nodata": {"handling": "transparante pixels betekenen geen modelwaarde"},
        }
        result.files[f"{stem}.png"] = png
        result.files[f"{stem}.json"] = json.dumps(
            meta, ensure_ascii=False, separators=(",", ":")
        ).encode("utf-8")
        records.append(_record(target, day_offset, fetched_at, f"{stem}.png"))

    result.records = records
    result.valid_until = iso(
        datetime.combine(today + timedelta(days=MAX_DAY_OFFSET + 1), time.min, timezone.utc)
    )
    result.status = "ok"
    result.notes.append("EFFIS FWI (Météo-France 10 km), D+0 t/m D+2")
    result.coverage = {"bbox": BBOX, "model": LAYER, "resolution_km": 10}
    return result


def _map_url(target) -> str:
    query = urlencode({
        "SERVICE": "WMS",
        "VERSION": "1.1.1",
        "REQUEST": "GetMap",
        "LAYERS": LAYER,
        "STYLES": "default",
        "FORMAT": "image/png",
        "TRANSPARENT": "true",
        "SRS": "EPSG:3857",
        "BBOX": ",".join(str(PROJECTED_BBOX[key]) for key in ("west", "south", "east", "north")),
        "WIDTH": WIDTH,
        "HEIGHT": HEIGHT,
        "TIME": target.isoformat(),
    })
    return f"{WMS_URL}?{query}"


def _validate_png(data: bytes) -> None:
    if len(data) < 33 or data[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("respons is geen PNG")
    if data[12:16] != b"IHDR":
        raise ValueError("PNG mist IHDR")
    width, height = struct.unpack(">II", data[16:24])
    if (width, height) != (WIDTH, HEIGHT):
        raise ValueError(f"onverwachte rasterafmetingen {width}x{height}")
    if b"IDAT" not in data or b"IEND" not in data:
        raise ValueError("PNG is onvolledig")


def _record(target, day_offset: int, fetched_at: str, png_path: str) -> dict:
    start = datetime.combine(target, time.min, timezone.utc)
    return make_record(
        id=f"effis-fwi-{target.isoformat()}",
        kind="danger",
        authority="Copernicus EFFIS",
        source_url=PAGE_URL,
        geometry=None,
        area_text="Europa",
        severity_source="geharmoniseerde FWI-klassen (Météo-France 10 km)",
        certainty="forecast",
        valid_from=iso(start),
        valid_to=iso(start + timedelta(days=1)),
        fetched_at=fetched_at,
        expires_policy="hide_after_valid_to",
        attribution=ATTRIBUTION,
        raw_payload_ref=f"effis:{LAYER}:{target.isoformat()}",
        source_attrs={
            "day_offset": day_offset,
            "area": "europe",
            "model": LAYER,
            "png": png_path,
            "meta": png_path.rsplit(".", 1)[0] + ".json",
        },
    )
