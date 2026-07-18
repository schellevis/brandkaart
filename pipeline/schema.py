"""Gemeenschappelijk gegevensmodel met veld-allowlist.

Ieder genormaliseerd record mag uitsluitend de velden uit ALLOWED_FIELDS
bevatten. `source_attrs` is een
per-adapter beperkte set bronattributen (bv. frp/confidence bij FIRMS);
vrije-tekstvelden en contactgegevens uit bronnen komen nooit mee.
"""

from __future__ import annotations

ALLOWED_FIELDS = frozenset(
    {
        "id",
        "source_id",
        "kind",
        "authority",
        "source_url",
        "geometry",
        "area_text",
        "severity_source",
        "severity_normalized",
        "certainty",
        "issued_at",
        "valid_from",
        "valid_to",
        "observed_at",
        "fetched_at",
        "expires_policy",
        "restrictions_text",
        "attribution",
        "raw_payload_ref",
        "source_attrs",
    }
)

ALLOWED_KINDS = frozenset(
    {"detection", "confirmed_incident", "danger", "warning", "measure", "burned_area"}
)

REQUIRED_FIELDS = ("id", "kind", "authority", "attribution", "fetched_at")


def make_record(**fields) -> dict:
    """Bouw een genormaliseerd record en dwing de allowlist af."""
    unknown = set(fields) - ALLOWED_FIELDS
    if unknown:
        raise ValueError(f"velden buiten allowlist: {sorted(unknown)}")
    for name in REQUIRED_FIELDS:
        if not fields.get(name):
            raise ValueError(f"verplicht veld ontbreekt: {name}")
    if fields["kind"] not in ALLOWED_KINDS:
        raise ValueError(f"onbekend kind: {fields['kind']}")
    source_attrs = fields.get("source_attrs")
    if source_attrs is not None and not isinstance(source_attrs, dict):
        raise ValueError("source_attrs moet een dict zijn")
    return {name: value for name, value in fields.items() if value is not None}


def to_feature_collection(records: list[dict]) -> dict:
    """Zet records om naar GeoJSON; geometry mag None zijn (join volgt later)."""
    features = []
    for record in records:
        properties = {k: v for k, v in record.items() if k != "geometry"}
        features.append(
            {
                "type": "Feature",
                "geometry": record.get("geometry"),
                "properties": properties,
            }
        )
    return {"type": "FeatureCollection", "features": features}
