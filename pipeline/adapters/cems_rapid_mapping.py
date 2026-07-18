"""CEMS Rapid Mapping: officieel geactiveerde wildfire-rampen (EU).

Publieke, sleutelvrije JSON-API. Alleen activaties met een brandcategorie
worden meegenomen; een activatie is een officiële bevestiging door een
lidstaat, geen satellietinterpretatie.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from ..common import SourceResult, http_get_json, iso, parse_wkt_point, utcnow
from ..schema import make_record

API_URL = "https://mapping.emergency.copernicus.eu/activations/api/activations/"
ATTRIBUTION = "© European Union, Copernicus Emergency Management Service"
SOURCE_URL = "https://mapping.emergency.copernicus.eu/"

MAX_PAGES = 10
CLOSED_WINDOW = timedelta(days=30)


def fetch() -> SourceResult:
    result = SourceResult(source="cems_rapid_mapping", attribution=ATTRIBUTION, source_url=SOURCE_URL)
    fetched_at = iso(utcnow())
    closed_cutoff = utcnow() - CLOSED_WINDOW
    records: list[dict] = []
    newest: str | None = None

    url = API_URL
    try:
        for _ in range(MAX_PAGES):
            page = http_get_json(url)
            activations = page if isinstance(page, list) else page.get("results", [])
            for activation in activations:
                activated = _parse_time(activation.get("activationTime"))
                if activated and activated < closed_cutoff and activation.get("closed"):
                    continue
                if not _is_fire(activation):
                    continue
                record = _normalize(activation, fetched_at)
                if record is not None:
                    records.append(record)
                    last_update = record.get("issued_at")
                    if last_update and (newest is None or last_update > newest):
                        newest = last_update
            url = page.get("next") if isinstance(page, dict) else None
            if url is None:
                break
    except Exception as exc:  # noqa: BLE001
        return result.fail(str(exc))

    result.records = records
    result.source_updated_at = newest
    result.status = "ok"
    result.notes.append(
        f"{len(records)} Rapid Mapping-brandactivaties; gesloten maximaal "
        f"{CLOSED_WINDOW.days} dagen oud"
    )
    return result


def _is_fire(activation: dict) -> bool:
    code = str(activation.get("code") or "").upper()
    category = str(activation.get("category") or "").lower()
    return code.startswith("EMSR") and ("fire" in category or "wildfire" in category)


def _parse_time(value):
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed
    except ValueError:
        return None


def _normalize(activation: dict, fetched_at: str) -> dict | None:
    code = activation.get("code")
    if not code:
        return None
    geometry = parse_wkt_point(str(activation.get("centroid") or ""))
    if geometry is None:
        return None
    title = str(activation.get("name") or activation.get("title") or "").strip()[:200]
    activated = _parse_time(activation.get("activationTime"))
    return make_record(
        id=f"cems-{code}",
        source_id=str(code),
        kind="confirmed_incident",
        authority="Copernicus Emergency Management Service",
        source_url=f"https://mapping.emergency.copernicus.eu/activations/{code}/",
        geometry=geometry,
        area_text=title or None,
        severity_source=str(activation.get("drmPhase") or "unknown"),
        certainty="official_activation",
        issued_at=iso(activated),
        fetched_at=fetched_at,
        expires_policy="hide_when_closed_30d",
        attribution=ATTRIBUTION,
        raw_payload_ref=f"cems:{code}",
        source_attrs={
            "closed": bool(activation.get("closed")),
            "n_products": activation.get("n_products"),
            "category": activation.get("category"),
        },
    )
