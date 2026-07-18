"""Controles: PII- en secretdetectie op artefactinhoud.

Alle fixtures zijn synthetisch en onmiskenbaar fictief.
"""

from pipeline import checks
from pipeline.common import parse_wkt_point


def test_email_wordt_gedetecteerd():
    violations = checks.scan_text('{"contact": "iemand@voorbeeld.example"}', "test.json")
    assert violations, "synthetisch e-mailadres had gedetecteerd moeten worden"


def test_telefoonnummer_wordt_gedetecteerd():
    violations = checks.scan_text("bel +31 6 12 34 56 78 voor info", "test.json")
    assert violations


def test_coordinaten_geen_valse_treffer(monkeypatch):
    monkeypatch.delenv("FIRMS_MAP_KEY", raising=False)
    clean = (
        b'{"type":"Polygon","coordinates":[[[0.0067801,40.41678],[-3.70379,0.0024681357,'
        b'0.00553211]]],"acq_time":"1342"}'
    )
    assert checks.scan_json_strings(clean, "test.geojson") == []
    assert checks.scan_artifact_files({"test.geojson": clean}) == []


def test_pii_in_json_string_wel_gedetecteerd():
    data = b'{"properties": {"contact": "bel +31 6 12 34 56 78"}}'
    assert checks.scan_json_strings(data, "test.geojson")
    assert checks.scan_json_strings(b'{"tel": "0034 612 345 678"}', "test.geojson")


def test_record_ids_met_cijferreeksen_geen_valse_treffer():
    data = (
        b'{"id": "firms-N20-2026-07-15-0058-48.1234--3.5678",'
        b' "waarde": "0.0058999114", "stamp": "20260715110717"}'
    )
    assert checks.scan_json_strings(data, "test.geojson") == []


def test_secret_uit_omgeving_gedetecteerd(monkeypatch):
    monkeypatch.setenv("FIRMS_MAP_KEY", "fictievesleutel1234")
    data = b'{"url": "https://example.invalid/fictievesleutel1234/area"}'
    assert checks.scan_secrets(data, "test.json")
    assert checks.scan_secrets(b'{"ok": true}', "test.json") == []


def test_artifact_scan_slaat_binaries_over_voor_pii(monkeypatch):
    monkeypatch.delenv("FIRMS_MAP_KEY", raising=False)
    files = {"danger/es/aemet/p_20260715_d0.tif": b"II*\x00binaire-inhoud"}
    assert checks.scan_artifact_files(files) == []


def test_wkt_punt_parsen():
    geometry = parse_wkt_point("POINT (2.7075 48.4047)")
    assert geometry == {"type": "Point", "coordinates": [2.7075, 48.4047]}
    assert parse_wkt_point("LINESTRING (0 0, 1 1)") is None
