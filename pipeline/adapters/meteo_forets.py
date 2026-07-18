"""Météo des forêts: departementaal brandgevaar Frankrijk (J+1/J+2).

Bron: dataset "Archives de la Météo des forêts" op data.gouv.fr
(Licence Ouverte 2.0). De actuele CSV wordt via de data.gouv.fr-API
ontdekt. CSV-schema: date;num_dep;niveau_j1;niveau_j2;nom_dep.
"""

from __future__ import annotations

import csv
import gzip
import io
from datetime import date, datetime, time, timedelta, timezone

from ..common import SourceResult, http_get, http_get_json, iso, utcnow
from ..schema import make_record

DATASET_API = "https://www.data.gouv.fr/api/1/datasets/archives-de-la-meteo-des-forets/"
ATTRIBUTION = "Source : Météo-France (Météo des forêts) — Licence Ouverte 2.0"
SOURCE_URL = "https://meteofrance.com/meteo-des-forets"

LEVEL_LABELS = {1: "faible", 2: "modéré", 3: "élevé", 4: "très élevé"}
MIN_EXPECTED_DEPARTMENTS = 80


def fetch() -> SourceResult:
    result = SourceResult(source="meteo_forets", attribution=ATTRIBUTION, source_url=SOURCE_URL)
    try:
        dataset = http_get_json(DATASET_API)
        resource = _latest_csv_resource(dataset)
        if resource is None:
            return result.fail("geen CSV-resource gevonden in de dataset")
        payload = http_get(resource["url"])
        if payload[:2] == b"\x1f\x8b":  # resources zijn als csv.gz gepubliceerd
            payload = gzip.decompress(payload)
        raw = payload.decode("utf-8-sig")
    except Exception as exc:  # noqa: BLE001
        return result.fail(str(exc))
    if any((r.get("format") or "").lower() == "geojson" for r in dataset.get("resources", [])):
        result.notes.append("dataset bevat ook departements-GeoJSON voor de latere geometriekoppeling")

    fetched_at = iso(utcnow())
    rows = list(csv.DictReader(io.StringIO(raw), delimiter=";"))
    if not rows:
        return result.fail("CSV bevat geen rijen")

    # Het archief bevat alle publicaties van het seizoen; de date-kolom is een
    # volledige UTC-timestamp. Alleen de meest recente publicatie telt.
    latest_stamp = max(row["date"] for row in rows if row.get("date"))
    rows = [row for row in rows if row.get("date") == latest_stamp]
    if len(rows) < MIN_EXPECTED_DEPARTMENTS:
        return result.fail(
            f"plausibiliteit: {len(rows)} departementen voor {latest_stamp}, "
            f"verwacht minimaal {MIN_EXPECTED_DEPARTMENTS}"
        )

    publication = datetime.fromisoformat(latest_stamp.replace("Z", "+00:00")).date()
    records = []
    for row in rows:
        for offset, column in ((1, "niveau_j1"), (2, "niveau_j2")):
            try:
                level = int(row[column])
            except (KeyError, TypeError, ValueError):
                continue
            target = publication + timedelta(days=offset)
            records.append(_record(row, level, offset, target, fetched_at))

    result.records = records
    result.source_updated_at = latest_stamp
    result.valid_until = iso(
        datetime.combine(publication + timedelta(days=2), time(23, 59), tzinfo=timezone.utc)
    )
    result.status = "ok"
    # Buiten het seizoen of bij een gemiste publicatie is het archief ouder dan J-1.
    if publication < utcnow().date() - timedelta(days=1):
        result.status = "ok_stale"
        result.notes.append(f"laatste publicatie is {latest_stamp}; kaart geldt niet meer voor morgen")
    return result


def _latest_csv_resource(dataset: dict) -> dict | None:
    candidates = [
        resource
        for resource in dataset.get("resources", [])
        if (resource.get("format") or "").lower() in ("csv", "csv.gz")
        or (resource.get("url") or "").lower().endswith((".csv", ".csv.gz"))
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda r: r.get("last_modified") or r.get("created_at") or "")


def _record(row: dict, level: int, offset: int, target: date, fetched_at: str) -> dict:
    dep = row.get("num_dep", "").strip()
    return make_record(
        id=f"mdf-{target.isoformat()}-{dep}",
        kind="danger",
        authority="Météo-France",
        source_url=SOURCE_URL,
        geometry=None,  # koppeling aan departementsgrenzen volgt in de kaartbuild
        area_text=row.get("nom_dep", "").strip(),
        severity_source=f"niveau {level} ({LEVEL_LABELS.get(level, 'onbekend')})",
        severity_normalized=level,
        certainty="forecast",
        issued_at=row.get("date"),
        valid_from=f"{target.isoformat()}T00:00:00Z",
        valid_to=f"{target.isoformat()}T23:59:59Z",
        fetched_at=fetched_at,
        expires_policy="hide_after_valid_to",
        attribution=ATTRIBUTION,
        raw_payload_ref=f"meteo_forets:{row.get('date')}:{dep}:j{offset}",
        source_attrs={"num_dep": dep, "day_offset": offset},
    )
