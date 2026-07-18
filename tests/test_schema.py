"""Schema: allowlist-afdwinging op genormaliseerde records."""

import pytest

from pipeline.schema import make_record, to_feature_collection


def _base(**overrides):
    fields = {
        "id": "test-1",
        "kind": "detection",
        "authority": "Testinstantie",
        "attribution": "Testbron",
        "fetched_at": "2026-07-15T12:00:00Z",
    }
    fields.update(overrides)
    return fields


def test_record_binnen_allowlist():
    record = make_record(**_base(severity_source="niveau 2"))
    assert record["id"] == "test-1"
    assert "severity_source" in record


def test_veld_buiten_allowlist_geweigerd():
    with pytest.raises(ValueError, match="allowlist"):
        make_record(**_base(contact_email="niet@toegestaan.example"))


def test_onbekend_kind_geweigerd():
    with pytest.raises(ValueError, match="kind"):
        make_record(**_base(kind="brandmelding"))


def test_verplicht_veld_afgedwongen():
    fields = _base()
    del fields["attribution"]
    with pytest.raises(ValueError, match="attribution"):
        make_record(**fields)


def test_none_velden_vallen_weg():
    record = make_record(**_base(area_text=None))
    assert "area_text" not in record


def test_feature_collection_scheidt_geometrie():
    record = make_record(
        **_base(geometry={"type": "Point", "coordinates": [4.9, 52.4]})
    )
    collection = to_feature_collection([record])
    feature = collection["features"][0]
    assert feature["geometry"]["type"] == "Point"
    assert "geometry" not in feature["properties"]
