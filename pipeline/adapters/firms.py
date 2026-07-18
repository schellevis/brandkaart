"""NASA FIRMS Area API: Europese satellietdetecties.

Vereist FIRMS_MAP_KEY in de omgeving (later: GitHub Actions Secret). De
sleutel staat in het URL-pad en mag daarom nooit worden gelogd; alle
foutpaden lopen via common.redact(). Zonder sleutel wordt de bron
overgeslagen zodat de rest van de pipeline gewoon draait.
"""

from __future__ import annotations

import csv
import io
import os
from datetime import datetime, timedelta, timezone

from ..common import SourceResult, http_get, iso, redact, utcnow
from ..schema import make_record

# West, zuid, oost, noord: Europa inclusief Canarische Eilanden.
EUROPE_BBOX = "-25,27,45,72"
# 2 dagen: de lopende UTC-dag is voor VIIRS-NRT vaak nog leeg; de interface
# filtert zelf op recente detecties.
DAY_RANGE = 2
SENSOR_SOURCES = ("VIIRS_SNPP_NRT", "VIIRS_NOAA20_NRT", "VIIRS_NOAA21_NRT", "MODIS_NRT")

ATTRIBUTION = "Fire detections courtesy of NASA FIRMS"
SOURCE_URL = "https://firms.modaps.eosdis.nasa.gov/"

# Bronattributen die we bewust behouden; al het overige valt weg.
KEPT_ATTRS = ("frp", "bright_ti4", "bright_ti5", "brightness", "bright_t31", "daynight", "scan", "track")

CONFIDENCE_LABELS = {"l": "low", "n": "nominal", "h": "high"}


def _certainty(confidence: str, sensor: str) -> str:
    if sensor.startswith("MODIS"):
        try:
            numeric = float(confidence)
        except ValueError:
            pass
        else:
            confidence = "l" if numeric < 30 else "n" if numeric < 80 else "h"
    return CONFIDENCE_LABELS.get(confidence, confidence or "unknown")


def fetch() -> SourceResult:
    result = SourceResult(
        source="firms",
        attribution=ATTRIBUTION,
        source_url=SOURCE_URL,
    )
    map_key = os.environ.get("FIRMS_MAP_KEY", "").strip()
    if not map_key:
        result.status = "skipped_no_key"
        result.notes.append(
            "FIRMS_MAP_KEY ontbreekt; vraag een gratis MAP_KEY aan via "
            "https://firms.modaps.eosdis.nasa.gov/api/map_key/ en zet die als omgevingsvariabele."
        )
        return result

    fetched_at = iso(utcnow())
    seen: set[tuple] = set()
    records: list[dict] = []
    newest: datetime | None = None
    failures: list[str] = []

    for sensor in SENSOR_SOURCES:
        url = (
            f"https://firms.modaps.eosdis.nasa.gov/api/area/csv/"
            f"{map_key}/{sensor}/{EUROPE_BBOX}/{DAY_RANGE}"
        )
        try:
            raw = http_get(url).decode("utf-8")
        except Exception as exc:  # noqa: BLE001
            failures.append(redact(f"{sensor}: {exc}"))
            continue
        for row in csv.DictReader(io.StringIO(raw)):
            record, key, observed = _normalize_row(row, sensor, fetched_at)
            if record is None or key in seen:
                continue
            seen.add(key)
            records.append(record)
            if observed and (newest is None or observed > newest):
                newest = observed

    if failures and not records:
        return result.fail("; ".join(failures))
    result.notes.extend(failures)
    result.records = records
    result.source_updated_at = iso(newest)
    result.status = "ok"
    if newest and utcnow() - newest > timedelta(hours=6):
        result.status = "ok_stale"
        result.notes.append("nieuwste detectie is ouder dan 6 uur")
    return result


def _normalize_row(row: dict, sensor: str, fetched_at: str):
    try:
        lat = float(row["latitude"])
        lon = float(row["longitude"])
    except (KeyError, TypeError, ValueError):
        return None, None, None
    acq_date = row.get("acq_date", "")
    acq_time = (row.get("acq_time") or "0").zfill(4)
    observed = None
    try:
        observed = datetime.strptime(f"{acq_date} {acq_time}", "%Y-%m-%d %H%M").replace(
            tzinfo=timezone.utc
        )
    except ValueError:
        pass
    satellite = row.get("satellite", "")
    confidence = (row.get("confidence") or "").strip().lower()
    key = (satellite, acq_date, acq_time, round(lat, 4), round(lon, 4))

    source_attrs = {"satellite": satellite, "instrument": row.get("instrument", "")}
    for name in KEPT_ATTRS:
        if row.get(name):
            source_attrs[name] = row[name]

    record = make_record(
        id=f"firms-{satellite}-{acq_date}-{acq_time}-{lat:.4f}-{lon:.4f}",
        source_id=None,
        kind="detection",
        authority="NASA FIRMS",
        source_url=SOURCE_URL,
        geometry={"type": "Point", "coordinates": [lon, lat]},
        severity_source=f"confidence={confidence or 'unknown'}",
        certainty=_certainty(confidence, sensor),
        observed_at=iso(observed),
        fetched_at=fetched_at,
        expires_policy="hide_after_48h",
        attribution=ATTRIBUTION,
        raw_payload_ref=f"firms:{sensor}",
        source_attrs=source_attrs,
    )
    return record, key, observed
