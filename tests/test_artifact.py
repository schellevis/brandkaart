"""Artefactbouw: staging, manifest en stale_reused-fallback.

Alle fixtures zijn synthetisch en onmiskenbaar fictief.
"""

import gzip
import json

from pipeline import restore
from pipeline.artifact import _reuse_previous, build
from pipeline.common import SourceResult
from pipeline.schema import make_record


def _ok_result(source="cems_rapid_mapping", valid_until=None):
    record = make_record(
        id="test-1",
        kind="confirmed_incident",
        authority="Testinstantie",
        attribution="Testbron",
        fetched_at="2026-07-15T12:00:00Z",
        geometry={"type": "Point", "coordinates": [2.7, 48.4]},
    )
    result = SourceResult(source=source, status="ok", records=[record], attribution="Testbron")
    result.valid_until = valid_until
    return result


def _failed_result(source="cems_rapid_mapping"):
    return SourceResult(source=source).fail("bron onbereikbaar (test)")


def _manifest(output_dir):
    return json.loads((output_dir / "manifest.json").read_text("utf-8"))


def test_ok_bron_wordt_gepubliceerd(tmp_path):
    output = tmp_path / "data"
    report = build([_ok_result()], output)
    assert "incidents.eu.latest.geojson.gz" in report
    manifest = _manifest(output)
    assert manifest["sources"]["cems_rapid_mapping"]["record_count"] == 1


def test_fallback_hergebruikt_geldige_vorige_laag(tmp_path):
    output = tmp_path / "data"
    build([_ok_result(valid_until="2099-01-01T00:00:00Z")], output)

    build([_failed_result()], output, previous_dir=output)
    entry = _manifest(output)["sources"]["cems_rapid_mapping"]
    assert entry["status"] == "stale_reused"
    assert entry["record_count"] == 1
    assert entry["error"]  # de actuele fout blijft zichtbaar
    layer = json.loads(gzip.decompress((output / "incidents.eu.latest.geojson.gz").read_bytes()))
    assert len(layer["features"]) == 1


def test_fallback_weigert_verlopen_laag(tmp_path):
    output = tmp_path / "data"
    build([_ok_result(valid_until="2020-01-01T00:00:00Z")], output)

    build([_failed_result()], output, previous_dir=output)
    entry = _manifest(output)["sources"]["cems_rapid_mapping"]
    assert entry["status"] == "failed"
    assert not (output / "incidents.eu.latest.geojson.gz").exists()


def test_fallback_zonder_valid_until_gebruikt_maximumleeftijd(tmp_path):
    output = tmp_path / "data"
    build([_ok_result()], output)  # geen valid_until; last_success_at = nu

    build([_failed_result()], output, previous_dir=output)
    assert _manifest(output)["sources"]["cems_rapid_mapping"]["status"] == "stale_reused"

    # Een kunstmatig verouderde last_success_at wordt geweigerd.
    manifest = _manifest(output)
    manifest["sources"]["cems_rapid_mapping"]["status"] = "ok"
    manifest["sources"]["cems_rapid_mapping"]["last_success_at"] = "2020-01-01T00:00:00Z"
    (output / "manifest.json").write_text(json.dumps(manifest), "utf-8")
    build([_failed_result()], output, previous_dir=output)
    assert _manifest(output)["sources"]["cems_rapid_mapping"]["status"] == "failed"


def test_fallback_vergelijkt_iso_offsets_als_utc(tmp_path):
    previous = tmp_path / "previous"
    previous.mkdir()
    payload = b'{"type":"FeatureCollection","features":[]}'
    (previous / "incidents.eu.latest.geojson.gz").write_bytes(gzip.compress(payload))
    (previous / "manifest.json").write_text(json.dumps({
        "sources": {"cems_rapid_mapping": {
            "status": "ok",
            "valid_until": "2026-07-18T00:00:00+02:00",
            "last_success_at": "2026-07-17T20:00:00Z",
        }}
    }), "utf-8")
    reused = _reuse_previous(
        "cems_rapid_mapping", "incidents.eu.latest.geojson", previous,
        "2026-07-17T23:00:00Z",
    )
    assert reused is None


def test_fallback_en_restore_nemen_extra_bestanden_mee(monkeypatch, tmp_path):
    original = tmp_path / "original"
    result = _ok_result(source="aemet_danger", valid_until="2099-01-01T00:00:00Z")
    result.files = {
        "danger/es/aemet/test.png": b"png-fixture",
        "danger/es/aemet/test.json": b'{"fixture":true}',
    }
    build([result], original)
    entry = _manifest(original)["sources"]["aemet_danger"]
    assert entry["files"] == [
        "danger/es/aemet/test.json.gz", "danger/es/aemet/test.png"
    ]

    def fake_get(url, **kwargs):
        relative = url.split("/data/", 1)[1]
        return (original / relative).read_bytes()

    monkeypatch.setattr(restore, "http_get", fake_get)
    restored = tmp_path / "restored"
    assert restore.restore("https://fixture.invalid/data", restored) == 3

    output = tmp_path / "new"
    build([_failed_result(source="aemet_danger")], output, previous_dir=restored)
    reused_entry = _manifest(output)["sources"]["aemet_danger"]
    assert reused_entry["status"] == "stale_reused"
    assert (output / "danger/es/aemet/test.png").read_bytes() == b"png-fixture"
    assert gzip.decompress(
        (output / "danger/es/aemet/test.json.gz").read_bytes()
    ) == b'{"fixture":true}'
